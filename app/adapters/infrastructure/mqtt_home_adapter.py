# -*- coding: utf-8 -*-
"""MQTT Home Adapter - Smart Home integration for JARVIS Soldier Mesh.

Integrates JARVIS with MQTT-based Smart Home infrastructure (including
Home Assistant) so that physical commands can be executed through Soldier
devices (e.g. toggling relays, sending IR signals, switching smart plugs).

Architecture notes:
    - Uses the ``paho-mqtt`` library when available.  If the library is not
      installed the adapter operates in *dry-run* mode, logging commands
      without publishing.
    - The adapter is intentionally side-effect free when ``dry_run=True``
      (the default in tests) to avoid requiring a real broker in CI.
    - Implements ``NexusComponent`` so it can be resolved via Nexus DI.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from app.core.nexuscomponent import NexusComponent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional paho-mqtt import
# ---------------------------------------------------------------------------
try:
    import paho.mqtt.client as mqtt  # type: ignore

    _MQTT_AVAILABLE = True
except ImportError:
    _MQTT_AVAILABLE = False
    logger.warning(
        "⚠️ [MqttHome] paho-mqtt não instalado — operando em modo dry-run. "
        "Instale com: pip install paho-mqtt"
    )


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class MqttHomeAdapter(NexusComponent):
    """
    Publishes physical commands to an MQTT broker (e.g. Home Assistant via
    Mosquitto).

    Supports:
    - Publishing arbitrary payloads to MQTT topics.
    - Subscribing to state topics and firing callbacks.
    - Convenience helpers for common Home-Assistant command topics.

    Args:
        host: MQTT broker hostname or IP (default: ``"localhost"``).
        port: Broker port (default: ``1883``).
        username: Optional MQTT username.
        password: Optional MQTT password.
        client_id: MQTT client identifier (default: ``"jarvis_c2"``).
        dry_run: When ``True`` (default when paho-mqtt is absent), commands
            are logged but not published.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 1883,
        username: Optional[str] = None,
        password: Optional[str] = None,
        client_id: str = "jarvis_c2",
        dry_run: bool = False,
    ) -> None:
        self._host = host
        self._port = port
        self._client_id = client_id
        self._dry_run = dry_run or not _MQTT_AVAILABLE
        self._client: Any = None
        self._connected = False
        self._published: List[Dict[str, Any]] = []  # audit log

        if not self._dry_run:
            self._client = mqtt.Client(client_id=client_id)
            if username:
                self._client.username_pw_set(username, password)
            self._client.on_connect = self._on_connect
            self._client.on_disconnect = self._on_disconnect

    # ------------------------------------------------------------------
    # NexusComponent interface
    # ------------------------------------------------------------------

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute a physical command described in *context*.

        Context keys:
            ``topic``   (str): MQTT topic to publish to.
            ``payload`` (Any): Message payload (will be JSON-encoded if dict).
            ``qos``     (int): QoS level (default 0).
            ``connect`` (bool): If True, connect before publishing (default False).
        """
        ctx = context or {}
        topic = ctx.get("topic")
        if not topic:
            return {"success": False, "error": "Context key 'topic' is required."}

        payload = ctx.get("payload", "")
        qos = int(ctx.get("qos", 0))

        if ctx.get("connect"):
            self.connect()

        return self.publish(topic, payload, qos=qos)

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Connect to the MQTT broker (no-op in dry-run mode)."""
        if self._dry_run:
            logger.info("🔌 [MqttHome] dry-run — conexão simulada com %s:%d", self._host, self._port)
            self._connected = True
            return True

        try:
            self._client.connect(self._host, self._port, keepalive=60)
            self._client.loop_start()
            logger.info("✅ [MqttHome] Conectado ao broker %s:%d", self._host, self._port)
            return True
        except Exception as exc:
            logger.error("❌ [MqttHome] Falha na conexão: %s", exc)
            return False

    def disconnect(self) -> None:
        """Disconnect from the MQTT broker."""
        if not self._dry_run and self._client and self._connected:
            self._client.loop_stop()
            self._client.disconnect()
        self._connected = False
        logger.info("🔌 [MqttHome] Desconectado.")

    # ------------------------------------------------------------------
    # Publish / Subscribe
    # ------------------------------------------------------------------

    def publish(
        self,
        topic: str,
        payload: Any,
        qos: int = 0,
        retain: bool = False,
    ) -> Dict[str, Any]:
        """
        Publish a message to an MQTT topic.

        Args:
            topic: MQTT topic string.
            payload: Message payload.  Dicts are serialised as JSON.
            qos: Quality of Service level (0, 1, or 2).
            retain: Whether to set the MQTT retain flag.

        Returns:
            Result dict with ``success``, ``topic``, and ``payload``.
        """
        encoded = json.dumps(payload) if isinstance(payload, dict) else str(payload)
        audit_entry = {"topic": topic, "payload": encoded, "qos": qos}

        if self._dry_run:
            logger.info("📤 [MqttHome] dry-run PUBLISH → %s : %s", topic, encoded)
            self._published.append(audit_entry)
            return {"success": True, "dry_run": True, **audit_entry}

        try:
            result = self._client.publish(topic, encoded, qos=qos, retain=retain)
            result.wait_for_publish()
            self._published.append(audit_entry)
            logger.debug("📤 [MqttHome] PUBLISH → %s : %s (rc=%d)", topic, encoded, result.rc)
            return {"success": result.rc == 0, **audit_entry, "rc": result.rc}
        except Exception as exc:
            logger.error("❌ [MqttHome] Falha ao publicar em '%s': %s", topic, exc)
            return {"success": False, "error": str(exc), **audit_entry}

    def subscribe(self, topic: str, callback: Any, qos: int = 0) -> bool:
        """
        Subscribe to an MQTT topic (no-op in dry-run mode).

        Args:
            topic: MQTT topic to subscribe to.
            callback: ``fn(client, userdata, message)`` invoked on receipt.
            qos: Quality of Service level.

        Returns:
            True if subscription was registered, False on error or dry-run.
        """
        if self._dry_run:
            logger.info("👂 [MqttHome] dry-run — subscrição simulada em '%s'", topic)
            return False

        try:
            self._client.subscribe(topic, qos=qos)
            self._client.message_callback_add(topic, callback)
            logger.info("👂 [MqttHome] Subscrito em '%s'", topic)
            return True
        except Exception as exc:
            logger.error("❌ [MqttHome] Falha na subscrição de '%s': %s", topic, exc)
            return False

    # ------------------------------------------------------------------
    # Home Assistant convenience helpers
    # ------------------------------------------------------------------

    def ha_switch(self, entity_id: str, state: str) -> Dict[str, Any]:
        """
        Toggle a Home Assistant switch via MQTT discovery topic.

        Args:
            entity_id: HA entity ID (e.g. ``"switch.relay_01"``).
            state: ``"ON"`` or ``"OFF"``.

        Returns:
            Result from ``publish``.
        """
        topic = f"homeassistant/switch/{entity_id}/set"
        return self.publish(topic, state.upper())

    def ha_command(self, domain: str, entity_id: str, command: str) -> Dict[str, Any]:
        """
        Send a generic Home Assistant command via MQTT.

        Args:
            domain: HA domain (e.g. ``"light"``, ``"cover"``).
            entity_id: Entity name without domain prefix.
            command: Command payload (e.g. ``"ON"``, ``"OFF"``, ``"OPEN"``).

        Returns:
            Result from ``publish``.
        """
        topic = f"homeassistant/{domain}/{entity_id}/set"
        return self.publish(topic, command)

    # ------------------------------------------------------------------
    # Audit / diagnostics
    # ------------------------------------------------------------------

    @property
    def published_messages(self) -> List[Dict[str, Any]]:
        """Return an immutable copy of the published messages audit log."""
        return list(self._published)

    @property
    def is_connected(self) -> bool:
        """Return True if the adapter is connected to a broker."""
        return self._connected

    # ------------------------------------------------------------------
    # Internal callbacks
    # ------------------------------------------------------------------

    def _on_connect(self, client: Any, userdata: Any, flags: Any, rc: int) -> None:
        if rc == 0:
            self._connected = True
            logger.info("✅ [MqttHome] Broker confirmou conexão (rc=0).")
        else:
            logger.warning("⚠️ [MqttHome] Conexão recusada pelo broker (rc=%d).", rc)

    def _on_disconnect(self, client: Any, userdata: Any, rc: int) -> None:
        self._connected = False
        if rc != 0:
            logger.warning("⚠️ [MqttHome] Desconexão inesperada (rc=%d).", rc)
