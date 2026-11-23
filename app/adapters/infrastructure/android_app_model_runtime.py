"""Text-only model runtime backed by explicitly installed Android LLM apps.

Local-device only: drives the user's authenticated app session through Jarvis
Accessibility; never exports app credentials or UI tokens.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from app.adapters.edge.android_accessibility_client import (
    ANDROID_LLM_APPS,
    accessibility_request,
    build_accessibility_app_launch,
)
from app.application.ports.model_runtime import (
    ModelInvocationRequest,
    ModelInvocationResult,
    ModelRuntimeError,
    ModelUsage,
)

_SEND_LABELS = frozenset({"send", "enviar", "send message", "enviar mensagem", "submit"})
_BUSY_LABELS = frozenset({
    "stop", "stop generating", "stop response", "parar", "parar geração",
    "parar de gerar", "cancel response", "cancelar resposta",
})
_DEVICE_UI_LOCK = threading.Lock()


class AndroidAppLLMRuntimeAdapter:
    """Invoke one allowlisted consumer LLM app through Android accessibility UI."""

    supports_cancellation = False

    def __init__(
        self, app_id: str, *,
        accessibility: Callable[..., dict[str, Any]] = accessibility_request,
        timeout_seconds: float = 90.0, poll_interval_seconds: float = 0.8,
        stable_polls: int = 2, sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        normalized = app_id.strip().lower() if isinstance(app_id, str) else ""
        if normalized not in ANDROID_LLM_APPS:
            raise ValueError(f"unsupported Android LLM app: {app_id!r}")
        if timeout_seconds <= 0 or poll_interval_seconds <= 0 or stable_polls < 2:
            raise ValueError("timeout, poll interval and stable poll count must be positive")
        self.app_id = normalized
        self.package_name = ANDROID_LLM_APPS[normalized]
        self.provider_id = f"android_app:{normalized}"
        self.model_id = f"android-app/{normalized}"
        self.accessibility = accessibility
        self.timeout_seconds = float(timeout_seconds)
        self.poll_interval_seconds = float(poll_interval_seconds)
        self.stable_polls = int(stable_polls)
        self._sleep = sleep
        self._monotonic = monotonic

    def invoke(self, request: ModelInvocationRequest) -> ModelInvocationResult:
        if not isinstance(request, ModelInvocationRequest):
            raise TypeError("request must be a ModelInvocationRequest")
        prompt = self._compose_prompt(request)
        timeout = min(self.timeout_seconds, float(request.timeout_seconds) if request.timeout_seconds else self.timeout_seconds)
        if not _DEVICE_UI_LOCK.acquire(timeout=timeout):
            raise self._error("device_ui_busy", "Android LLM UI is busy with another agent.", True)
        try:
            return self._invoke_locked(prompt, timeout)
        finally:
            _DEVICE_UI_LOCK.release()

    def _invoke_locked(self, prompt: str, timeout: float) -> ModelInvocationResult:
        deadline = self._monotonic() + timeout
        try:
            health = self.accessibility("/healthz")
            if health.get("status") != "ready":
                raise self._error("accessibility_unavailable", "Android accessibility bridge is not ready.", True)
            launch = self.accessibility("/v1/apps/launch", build_accessibility_app_launch(self.app_id))
            if launch.get("success") is not True:
                raise self._error("app_launch_failed", "The selected Android LLM app could not be opened.", True)

            snapshot = self._wait_for_app(deadline)
            nodes = self._nodes(snapshot)
            baseline = {self._node_text(node) for node in nodes if self._node_text(node)}
            editor = self._find_editor(nodes)
            if editor is None:
                raise self._error("composer_not_found", "No safe editable prompt field was found in the selected app.", True)
            edit_result = self.accessibility("/v1/action", {
                "action": "set_text_index", "index": editor["index"], "text": prompt,
            })
            if edit_result.get("success") is not True:
                raise self._error("prompt_entry_failed", "The Android LLM app rejected prompt entry.", True)

            refreshed = self._wait_for_app(deadline)
            send_node = self._find_send_button(self._nodes(refreshed))
            if send_node is None:
                raise self._error("send_control_not_found", "No accessible send control was found; the prompt was not submitted.", True)
            send_result = self.accessibility("/v1/action", {
                "action": "click_index", "index": send_node["index"],
            })
            if send_result.get("success") is not True:
                raise self._error("prompt_submit_failed", "The Android LLM app did not confirm prompt submission.", True)

            content = self._wait_for_response(prompt, baseline, deadline)
            return ModelInvocationResult(
                provider_id=self.provider_id, model_id=self.model_id, content=content,
                usage=ModelUsage(), routed_via="android_accessibility_ui", fallback_attempts=0,
            )
        except ModelRuntimeError:
            raise
        except Exception as exc:  # noqa: BLE001 - sanitize UI/transport boundary
            raise self._error("android_app_runtime_error", f"Android LLM app invocation failed ({type(exc).__name__}).", True) from None

    def _wait_for_app(self, deadline: float) -> dict[str, Any]:
        while self._monotonic() < deadline:
            snapshot = self.accessibility("/v1/snapshot")
            if snapshot.get("available") and snapshot.get("window_package") == self.package_name:
                return snapshot
            self._sleep(self.poll_interval_seconds)
        raise self._error("foreground_app_timeout", "Selected LLM app did not become the foreground window.", True)

    def _wait_for_response(self, prompt: str, baseline: set[str], deadline: float) -> str:
        previous = None
        stable_count = 0
        while self._monotonic() < deadline:
            snapshot = self._wait_for_app(deadline)
            texts = [self._node_text(node) for node in self._nodes(snapshot)]
            normalized = [value for value in texts if value]
            busy = any(value.strip().lower() in _BUSY_LABELS for value in normalized)
            candidates = self._extract_response_text(normalized, baseline, prompt)
            fingerprint = "\n".join(candidates)
            if fingerprint and not busy and fingerprint == previous:
                stable_count += 1
            elif fingerprint and not busy:
                stable_count = 1
            else:
                stable_count = 0
            if stable_count >= self.stable_polls:
                return fingerprint
            previous = fingerprint
            self._sleep(self.poll_interval_seconds)
        raise self._error("response_timeout", "The selected Android LLM app did not expose a stable completed response before timeout.", True)

    @staticmethod
    def _nodes(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        nodes = snapshot.get("nodes")
        return [node for node in nodes if isinstance(node, dict)] if isinstance(nodes, list) else []

    @staticmethod
    def _node_text(node: dict[str, Any]) -> str:
        if node.get("password") is True:
            return ""
        value = node.get("text") or node.get("content_description") or ""
        return value.strip() if isinstance(value, str) else ""

    @classmethod
    def _find_editor(cls, nodes: list[dict[str, Any]]) -> dict[str, Any] | None:
        # Never type into a sign-in form. A visible password field is a hard stop.
        if any(node.get("password") is True for node in nodes):
            return None
        candidates = []
        semantic_hints = ("message", "prompt", "ask", "chat", "composer", "perguntar", "mensagem")
        for node in nodes:
            if (
                node.get("editable") is not True
                or node.get("enabled", True) is not True
                or node.get("password") is True
                or not isinstance(node.get("index"), int)
            ):
                continue
            hint = " ".join(str(node.get(field) or "") for field in (
                "content_description", "view_id", "text"
            )).lower()
            if any(token in hint for token in semantic_hints):
                candidates.append(node)
        if not candidates:
            return None
        return max(candidates, key=lambda node: (
            int(bool(node.get("content_description")))
            + int("message" in str(node.get("content_description", "")).lower())
            + int("prompt" in str(node.get("view_id", "")).lower())
        ))

    @classmethod
    def _find_send_button(cls, nodes: list[dict[str, Any]]) -> dict[str, Any] | None:
        for node in nodes:
            if node.get("enabled", True) is not True or not isinstance(node.get("index"), int):
                continue
            label = cls._node_text(node).lower()
            class_name = node.get("class_name", "")
            if label in _SEND_LABELS and (node.get("clickable") is True or class_name.endswith("Button")):
                return node
        return None

    @staticmethod
    def _extract_response_text(texts: list[str], baseline: set[str], prompt: str) -> list[str]:
        candidates = []
        for value in texts:
            cleaned = value.replace(prompt, "").strip()
            if not cleaned or cleaned in baseline or cleaned.lower() in _SEND_LABELS | _BUSY_LABELS:
                continue
            if cleaned not in candidates:
                candidates.append(cleaned)
        return candidates[-8:]

    @staticmethod
    def _compose_prompt(request: ModelInvocationRequest) -> str:
        prompt = "\n\n".join(
            f"[{message.role.upper()}]\n{message.content.strip()}"
            for message in request.messages
        )
        if len(prompt) > 12000:
            raise ModelRuntimeError(
                "Android app prompt exceeds the local UI safety limit.",
                code="prompt_too_large", provider_id="android_app", retryable=False,
            )
        return prompt

    def _error(self, code: str, message: str, retryable: bool) -> ModelRuntimeError:
        return ModelRuntimeError(message, code=code, provider_id=self.provider_id, retryable=retryable)

    def cancel(self, request_id: str) -> bool:
        return False
