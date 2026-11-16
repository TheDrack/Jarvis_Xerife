"""MCP tools for one-shot, stateless ChatGPT plan-usage requests."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.adapters.infrastructure.chatgpt_plan_auth import ChatGPTPlanOAuth
from app.adapters.infrastructure.chatgpt_plan_runtime import (
    PLAN_USAGE_SCOPE,
    RESOURCE_INVOKE_SCOPE,
    ChatGPTPlanClient,
    ChatGPTPlanError,
)
from app.adapters.infrastructure.session_authorization import SESSION_GATEWAY
from app.communication import (
    CHATGPT_PLAN_CAPABILITY,
    CHATGPT_PLAN_TOOL_ID,
    CommunicationCapture,
    CommunicationRequest,
    create_chatgpt_plan_dispatcher,
    create_default_communication_registry,
)

STATUS_TOOL_NAME = "chatgpt_plan_status"
PROMPT_TOOL_NAME = "chatgpt_plan_prompt"
MAX_PROMPT_CHARS = 100_000
MAX_OUTPUT_TOKENS = 8192
MAX_TIMEOUT_SECONDS = 300

_SAFE_ERRORS = {
    "not_connected": "ChatGPT is not connected. Run the local sign-in flow.",
    "credential_store_error": "The local ChatGPT credential profile is unavailable or invalid.",
    "reauthorization_required": "The ChatGPT connection must be authorized again.",
    "plan_permission_missing": "ChatGPT plan-usage permission is missing.",
    "permission_denied": "The ChatGPT account has not granted the required permission.",
    "usage_limit": "The ChatGPT plan usage limit was reached or is unavailable.",
    "timeout": "ChatGPT response timed out.",
    "transport_error": "ChatGPT response transport failed.",
    "provider_unavailable": "ChatGPT is temporarily unavailable.",
    "provider_rejected": "ChatGPT rejected the request.",
    "incomplete_response": "ChatGPT ended the response before completion.",
    "incomplete_stream": "ChatGPT stream ended before completion.",
    "invalid_request": "The prompt or generation limits are invalid.",
    "session_authorization_denied": "The local communication session is not authorized.",
}


def _failure(
    code: str,
    *,
    retryable: bool = False,
    retry_after_seconds: float | None = None,
) -> dict[str, Any]:
    result = {
        "success": False,
        "code": code,
        "error": _SAFE_ERRORS.get(code, "ChatGPT request failed."),
        "retryable": retryable,
    }
    if retry_after_seconds is not None:
        result["retry_after_seconds"] = retry_after_seconds
    return result


def register_chatgpt_plan_tools(
    mcp: Any, *, registry=None, dispatcher=None, session_gateway=None, event_sink=None
) -> tuple[str, ...]:
    """Register local ChatGPT status and stateless prompt submission tools.

    OAuth credentials stay in Termux's owner-only local profile. Tool results,
    errors and audit records never include access or refresh tokens.
    """

    @mcp.tool(name=STATUS_TOOL_NAME)
    def chatgpt_plan_status() -> dict[str, Any]:
        """Return ChatGPT connection status without exposing credentials or tokens."""
        oauth = ChatGPTPlanOAuth()
        try:
            profile = oauth.store.load()
            if not profile:
                return {"connected": False, "email": None, "plan_usage_enabled": False}
            raw_scopes = profile.get("scopes", [])
            scopes = (
                set(raw_scopes) if isinstance(raw_scopes, (list, tuple, set)) else set()
            )
            return {
                "connected": True,
                "email": profile.get("email"),
                "plan_usage_enabled": {
                    PLAN_USAGE_SCOPE,
                    RESOURCE_INVOKE_SCOPE,
                }.issubset(scopes),
            }
        except (OSError, ValueError, TypeError, ChatGPTPlanError):
            return {
                "connected": False,
                "email": None,
                "plan_usage_enabled": False,
                "code": "credential_store_error",
            }
        finally:
            oauth.close()

    communication_registry = registry or create_default_communication_registry(
        oauth_factory=ChatGPTPlanOAuth,
        client_factory=ChatGPTPlanClient,
    )
    adapter = communication_registry.resolve("openai.chatgpt_plan")
    tool_dispatcher = dispatcher or create_chatgpt_plan_dispatcher(
        communication_registry,
        session_gateway=(
            session_gateway if session_gateway is not None else SESSION_GATEWAY
        ),
        event_sink=event_sink,
    )

    @mcp.tool(name=PROMPT_TOOL_NAME)
    def chatgpt_plan_prompt(
        prompt: str,
        model: str | None = None,
        max_output_tokens: int = 1200,
        timeout_seconds: int = 90,
        capture: bool = False,
    ) -> dict[str, Any]:
        """Send one stateless prompt; optionally capture it for later replay.

        Capture is disabled by default because it persists prompt and response
        content locally. Credentials are never included in the capture.
        """
        if not isinstance(capture, bool):
            return _failure("invalid_request")
        if (
            not isinstance(prompt, str)
            or not prompt.strip()
            or len(prompt) > MAX_PROMPT_CHARS
        ):
            return _failure("invalid_request")
        if (
            isinstance(max_output_tokens, bool)
            or not isinstance(max_output_tokens, int)
            or not 1 <= max_output_tokens <= MAX_OUTPUT_TOKENS
        ):
            return _failure("invalid_request")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, int)
            or not 5 <= timeout_seconds <= MAX_TIMEOUT_SECONDS
        ):
            return _failure("invalid_request")
        if model is not None and (not isinstance(model, str) or not model.strip()):
            return _failure("invalid_request")

        try:
            dispatch_result = tool_dispatcher.dispatch(
                {
                    "tool_id": CHATGPT_PLAN_TOOL_ID,
                    "tool_version": "1.0.0",
                    "capability": CHATGPT_PLAN_CAPABILITY,
                    "arguments": {
                        "prompt": prompt.strip(),
                        "model": model.strip() if model else None,
                        "max_output_tokens": max_output_tokens,
                        "timeout_seconds": timeout_seconds,
                    },
                    "caller": "android_mcp",
                    "scope": "local",
                }
            )
            if not dispatch_result.success:
                code = dispatch_result.error_code or "provider_error"
                if code == "authorization_denied":
                    code = "session_authorization_denied"
                # A dispatcher timeout can happen after the provider accepted
                # the inference request. Never advertise an uncertain POST as
                # safe to retry; only explicit rate/circuit gates are retryable.
                retryable = dispatch_result.retryable and code in {
                    "rate_limited",
                    "circuit_open",
                }
                return _failure(
                    code,
                    retryable=retryable,
                    retry_after_seconds=dispatch_result.retry_after_seconds,
                )
            result = dispatch_result.output
            if capture:
                capture_path = Path(
                    os.getenv(
                        "JARVIS_COMMUNICATION_CAPTURE_FILE",
                        str(
                            Path.home()
                            / ".local"
                            / "share"
                            / "jarvis"
                            / "communication"
                            / "captures.jsonl"
                        ),
                    )
                ).expanduser()
                try:
                    record = CommunicationCapture(capture_path).record(
                        CommunicationRequest(
                            adapter_id=adapter.adapter_id,
                            protocol=adapter.protocol,
                            operation="send_prompt",
                            payload={
                                "prompt": prompt.strip(),
                                "model": model.strip() if model else None,
                                "max_output_tokens": max_output_tokens,
                                "timeout_seconds": timeout_seconds,
                            },
                            metadata={"provider": "OpenAI Responses API"},
                        ),
                        result,
                    )
                    result["capture_id"] = record.capture_id
                except (OSError, ValueError):
                    result["capture"] = {
                        "saved": False,
                        "error": "capture_persistence_failed",
                    }
            return result
        except ChatGPTPlanError as exc:
            return _failure(exc.code, retryable=exc.retryable)
        except (OSError, ValueError, TypeError, PermissionError):
            return _failure("credential_store_error")
        except Exception:
            # Do not reflect provider bodies, request headers or credential data.
            return _failure("provider_error")

    return STATUS_TOOL_NAME, PROMPT_TOOL_NAME
