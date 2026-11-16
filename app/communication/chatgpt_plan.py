"""Communication adapter for the locally authorized ChatGPT plan provider."""

from __future__ import annotations

from typing import Any


class ChatGPTPlanCommunicationAdapter:
    """Expose one-shot ChatGPT prompt submission as a communication operation.

    The adapter uses the existing local OAuth credential store and public
    Responses API client. It does not automate the ChatGPT UI or persist tokens.
    """

    adapter_id = "openai.chatgpt_plan"
    protocol = "https"
    operations = ("send_prompt",)
    _OPERATIONS = frozenset(operations)

    def __init__(self, *, oauth_factory=None, client_factory=None) -> None:
        if oauth_factory is None:
            from app.adapters.infrastructure.chatgpt_plan_auth import ChatGPTPlanOAuth

            oauth_factory = ChatGPTPlanOAuth
        if client_factory is None:
            from app.adapters.infrastructure.chatgpt_plan_runtime import (
                ChatGPTPlanClient,
            )

            client_factory = ChatGPTPlanClient
        self._oauth_factory = oauth_factory
        self._client_factory = client_factory

    def send_prompt(
        self,
        prompt: str,
        model: str | None = None,
        max_output_tokens: int = 1200,
        timeout_seconds: int = 90,
    ) -> dict[str, Any]:
        """Expose the manifest operation shape expected by ToolDispatcher."""
        from app.adapters.infrastructure.chatgpt_plan_runtime import ChatGPTPlanError

        try:
            return self.execute(
                "send_prompt",
                {
                    "prompt": prompt,
                    "model": model,
                    "max_output_tokens": max_output_tokens,
                    "timeout_seconds": timeout_seconds,
                },
                context={"source": "tool_dispatcher"},
            )
        except ChatGPTPlanError as exc:
            return {"success": False, "error_code": exc.code}

    def execute(
        self, operation: str, payload: dict[str, Any], *, context: dict[str, Any]
    ) -> dict[str, Any]:
        if operation not in self._OPERATIONS:
            raise ValueError(
                f"unsupported ChatGPT communication operation: {operation}"
            )
        if not isinstance(payload, dict):
            raise ValueError("ChatGPT payload must be an object")
        prompt = payload.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 100_000:
            raise ValueError("prompt must contain 1-100000 characters")
        max_output_tokens = payload.get("max_output_tokens", 1200)
        timeout_seconds = payload.get("timeout_seconds", 90)
        model = payload.get("model")
        if (
            isinstance(max_output_tokens, bool)
            or not isinstance(max_output_tokens, int)
            or not 1 <= max_output_tokens <= 8192
        ):
            raise ValueError("max_output_tokens must be between 1 and 8192")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, int)
            or not 5 <= timeout_seconds <= 300
        ):
            raise ValueError("timeout_seconds must be between 5 and 300")
        if model is not None and (not isinstance(model, str) or not model.strip()):
            raise ValueError("model must be a non-empty string")

        oauth = self._oauth_factory()
        client = None
        try:
            token = oauth.get_access_token()
            client = self._client_factory(
                access_token=token,
                model=model.strip() if model else None,
                timeout_seconds=float(timeout_seconds),
            )
            result = client.generate(
                ({"role": "user", "content": prompt.strip()},),
                max_output_tokens=max_output_tokens,
                timeout_seconds=float(timeout_seconds),
            )
            return {
                "success": True,
                "response": result["content"],
                "model": result["model"],
                "request_id": result.get("request_id"),
                "usage": result.get("usage", {}),
            }
        finally:
            try:
                if client is not None:
                    client.close()
            finally:
                oauth.close()
