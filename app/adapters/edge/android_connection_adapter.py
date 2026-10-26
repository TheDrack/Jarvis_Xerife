"""ADB pairing/connection helpers for an explicitly selected Android device."""
from __future__ import annotations

import ipaddress
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any


def _adb_path(adb_path: str | None = None) -> str:
    return adb_path or os.getenv("JARVIS_ADB_PATH", "adb")


def _validate_endpoint(endpoint: str) -> str:
    endpoint = endpoint.strip()
    match = re.fullmatch(r"(\d{1,3}(?:\.\d{1,3}){3}):(\d{1,5})", endpoint)
    if not match:
        raise ValueError("Use o formato IPv4:porta, por exemplo 100.95.90.5:36433.")
    address = ipaddress.ip_address(match.group(1))
    port = int(match.group(2))
    if not isinstance(address, ipaddress.IPv4Address) or not 1 <= port <= 65535:
        raise ValueError("Endereço IPv4 ou porta inválidos.")
    # Permit private LANs and Tailscale's CGNAT range; reject public IP targets.
    tailscale = ipaddress.ip_network("100.64.0.0/10")
    private = any(address in ipaddress.ip_network(n) for n in (
        "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"
    ))
    if not (private or address in tailscale):
        raise ValueError("Por segurança, ADB só pode usar IPv4 privado RFC1918 ou Tailscale (100.64.0.0/10).")
    return f"{address}:{port}"


def _config_path() -> Path:
    base = Path(os.getenv("LOCALAPPDATA") or (Path.home() / ".local" / "share"))
    return base / "Jarvis" / "android-device.json"


def selected_device() -> str:
    configured = os.getenv("JARVIS_ANDROID_DEVICE", "").strip()
    if configured:
        return configured
    try:
        data = json.loads(_config_path().read_text(encoding="utf-8"))
        endpoint = str(data.get("device_address", "")).strip()
        return _validate_endpoint(endpoint) if endpoint else ""
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return ""


def pair_and_connect(
    pairing_address: str,
    pairing_code: str,
    device_address: str,
    adb_path: str | None = None,
    timeout_seconds: int = 20,
) -> dict[str, Any]:
    """Pair via Android Wireless debugging, connect its separate connect port, and persist only the target address."""
    try:
        pairing = _validate_endpoint(pairing_address)
        device = _validate_endpoint(device_address)
    except ValueError as exc:
        return {"success": False, "status": "invalid_endpoint", "error": str(exc)}
    code = pairing_code.strip()
    if not re.fullmatch(r"\d{6}", code):
        return {"success": False, "status": "invalid_pairing_code", "error": "O código de pareamento deve ter 6 dígitos."}
    adb = _adb_path(adb_path)
    try:
        paired = subprocess.run(
            [adb, "pair", pairing, code], capture_output=True,
            text=True, timeout=max(5, min(timeout_seconds, 60)), check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"success": False, "status": "pair_transport_error", "error": str(exc)}
    paired_output = (paired.stdout + "\n" + paired.stderr).strip()[:1000]
    if paired.returncode != 0 or not re.search(r"successfully paired|already paired", paired_output, re.I):
        return {"success": False, "status": "pair_failed", "pairing_output": paired_output}
    try:
        connected = subprocess.run(
            [adb, "connect", device], capture_output=True, text=True,
            timeout=max(5, min(timeout_seconds, 60)), check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"success": False, "status": "connect_transport_error", "paired": True, "error": str(exc)}
    connect_output = (connected.stdout + "\n" + connected.stderr).strip()[:1000]
    if connected.returncode != 0 or not re.search(r"connected to|already connected to", connect_output, re.I):
        return {"success": False, "status": "connect_failed", "paired": True, "connect_output": connect_output}
    try:
        config = _config_path()
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(json.dumps({"device_address": device}, indent=2), encoding="utf-8")
    except OSError as exc:
        return {"success": False, "status": "connected_but_not_saved", "device_address": device, "error": str(exc)}
    return {
        "success": True, "status": "connected", "device_address": device,
        "pairing_address": pairing, "pairing_code_saved": False,
        "config_path": str(_config_path()),
        "note": "Código de pareamento não foi salvo. O endereço selecionado fica disponível após reiniciar o servidor MCP.",
    }


def device_status(adb_path: str | None = None) -> dict[str, Any]:
    adb = _adb_path(adb_path)
    selected = selected_device()
    reconnect_result = None
    # A paired device can be reconnected without another pairing code.
    if selected:
        try:
            reconnect = subprocess.run([adb, "connect", selected], capture_output=True,
                                       text=True, timeout=10, check=False)
            reconnect_result = (reconnect.stdout + "\\n" + reconnect.stderr).strip()[:500]
        except (OSError, subprocess.TimeoutExpired) as exc:
            reconnect_result = str(exc)
    try:
        proc = subprocess.run([adb, "devices", "-l"], capture_output=True, text=True,
                              timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"success": False, "status": "adb_unavailable", "error": str(exc)}
    devices = []
    for line in proc.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] in {"device", "offline", "unauthorized"}:
            devices.append({"serial": parts[0], "state": parts[1]})
    selected_state = next((d["state"] for d in devices if d["serial"] == selected), None)
    return {"success": proc.returncode == 0, "devices": devices,
            "selected_device": selected or None, "selected_state": selected_state,
            "reconnect_attempt": reconnect_result,
            "status": selected_state or ("no_device" if not devices else "device_not_selected")}
