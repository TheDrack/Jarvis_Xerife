"""Shared composition of model profiles, runtime bindings, and mini-agent handler."""

from __future__ import annotations

from app.adapters.infrastructure.freellmapi_model_runtime import FreeLLMAPIModelRuntimeAdapter
from app.multiagent.freellmapi_client import FreeLLMAPIClient
from app.multiagent.freellmapi_handler import FreeLLMAgentHandler
from app.multiagent.model_registry import ModelProfile, ModelRegistry, ModelRuntimeBindings


def create_registered_model_handler(
    client: FreeLLMAPIClient,
    *,
    provider_id: str,
    max_tokens: int = 1200,
    temperature: float = 0.2,
) -> FreeLLMAgentHandler:
    """Bind the configured model profile to its provider adapter.

    Task-level model overrides remain supported by the OpenAI-compatible
    gateway adapter. The registry profile describes the configured default
    model; it is not a claim that every upstream model alias was discovered.
    """
    if not isinstance(client, FreeLLMAPIClient):
        raise TypeError("client must be a FreeLLMAPIClient")
    if not isinstance(provider_id, str) or not provider_id.strip():
        raise ValueError("provider_id must be a non-empty string")

    provider = provider_id.strip().lower()
    profile = ModelProfile(
        model_id=client.model,
        provider_id=provider,
        runtime_kind="remote_api",
        capabilities=frozenset({"chat", "text_reasoning"}),
        modalities=frozenset({"text"}),
    )
    profiles = ModelRegistry((profile,))
    adapter = FreeLLMAPIModelRuntimeAdapter(client, provider_id=provider)
    bindings = ModelRuntimeBindings({provider: adapter})
    selected_profile = profiles.get(client.model)
    if selected_profile is None:  # defensive: constructor should guarantee this
        raise RuntimeError("configured model profile was not registered")
    runtime = bindings.resolve(selected_profile)
    return FreeLLMAgentHandler(
        runtime,
        max_tokens=max_tokens,
        temperature=temperature,
    )
