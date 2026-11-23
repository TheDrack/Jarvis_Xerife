"""Shared composition of model profiles, runtime bindings, and mini-agent handler."""

from __future__ import annotations

from typing import Any, Protocol

from app.multiagent.freellmapi_client import FreeLLMAPIClient
from app.multiagent.freellmapi_handler import FreeLLMAgentHandler
from app.multiagent.model_registry import (
    ModelProfile,
    ModelRegistry,
    ModelRuntimeBindings,
)


class ChatGPTPlanOAuthPort(Protocol):
    """Minimal local OAuth contract required by the ChatGPT model factory."""

    def load_valid_profile(self) -> dict[str, Any]: ...

    def get_access_token(self) -> str: ...


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

    # Import at composition time to avoid a package-init cycle: the adapter
    # imports app.multiagent.freellmapi_client, whose package initializer
    # also exposes PriorityQueueMiniAgent and this factory.
    from app.adapters.infrastructure.freellmapi_model_runtime import (
        FreeLLMAPIModelRuntimeAdapter,
    )

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


def create_registered_android_app_handler(
    *,
    provider_id: str,
    max_tokens: int = 1200,
    temperature: float = 0.2,
    accessibility=None,
) -> FreeLLMAgentHandler:
    """Bind one installed Android LLM app to a local text-only mini-agent."""
    if not isinstance(provider_id, str) or not provider_id.startswith("android_app:"):
        raise ValueError("provider_id must use the android_app:<app-id> form")
    from app.adapters.infrastructure.android_app_model_runtime import (
        ANDROID_LLM_APPS,
        AndroidAppLLMRuntimeAdapter,
    )

    app_id = provider_id.partition(":")[2].strip().lower()
    if app_id not in ANDROID_LLM_APPS:
        raise ValueError("provider_id references an unsupported Android LLM app")
    kwargs = {"accessibility": accessibility} if accessibility is not None else {}
    adapter = AndroidAppLLMRuntimeAdapter(app_id, **kwargs)
    profile = ModelProfile(
        model_id=adapter.model_id,
        provider_id=adapter.provider_id,
        runtime_kind="android_accessibility_ui",
        capabilities=frozenset({"chat", "text_reasoning"}),
        modalities=frozenset({"text"}),
        max_concurrency=1,
        trust_level="user_session",
        metadata={"authentication": "installed_app_session", "execution": "local_device_only"},
    )
    profiles = ModelRegistry((profile,))
    bindings = ModelRuntimeBindings({adapter.provider_id: adapter})
    selected = profiles.get(adapter.model_id)
    if selected is None:
        raise RuntimeError("Android LLM app profile was not registered")
    runtime = bindings.resolve(selected)
    return FreeLLMAgentHandler(
        runtime, max_tokens=max_tokens, temperature=temperature, engine=adapter.provider_id
    )


def create_registered_chatgpt_plan_runtime(
    oauth: ChatGPTPlanOAuthPort,
    *,
    model_id: str,
) -> tuple[ModelProfile, ModelRuntimeBindings]:
    """Create a provider-neutral runtime binding for a locally authorized SIWC profile.

    The OAuth service refreshes credentials immediately before each invocation;
    no access token is copied into model metadata or shared task records.
    """
    if not isinstance(model_id, str) or not model_id.strip():
        raise ValueError("model_id must be a non-empty string")
    from app.adapters.infrastructure.chatgpt_plan_runtime import (
        PLAN_USAGE_SCOPE,
        RESOURCE_INVOKE_SCOPE,
        ChatGPTPlanClient,
        ChatGPTPlanModelRuntimeAdapter,
    )

    credentials = oauth.load_valid_profile()
    scopes = set(credentials.get("scopes", []))
    if not {PLAN_USAGE_SCOPE, RESOURCE_INVOKE_SCOPE}.issubset(scopes):
        raise ValueError("ChatGPT profile does not grant Responses API plan usage")
    client = ChatGPTPlanClient(
        access_token=credentials["access_token"],
        model=model_id.strip(),
    )
    adapter = ChatGPTPlanModelRuntimeAdapter(
        client, token_provider=oauth.get_access_token
    )
    profile = ModelProfile(
        model_id=model_id.strip(),
        provider_id="chatgpt_plan",
        runtime_kind="remote_api",
        capabilities=frozenset({"chat", "text_reasoning"}),
        modalities=frozenset({"text"}),
        metadata={"authentication": "sign_in_with_chatgpt", "billing": "chatgpt_plan"},
    )
    bindings = ModelRuntimeBindings({"chatgpt_plan": adapter})
    return profile, bindings


def create_registered_chatgpt_plan_handler(
    oauth: ChatGPTPlanOAuthPort,
    *,
    model_id: str,
    max_tokens: int = 1200,
    temperature: float = 0.2,
) -> FreeLLMAgentHandler:
    """Create the existing bounded text-agent handler backed by ChatGPT plan usage.

    This composes only a local runtime. It does not wire ChatGPT credentials into
    the remote Supabase/Render worker processes.
    """
    profile, bindings = create_registered_chatgpt_plan_runtime(oauth, model_id=model_id)
    runtime = bindings.resolve(profile)
    return FreeLLMAgentHandler(
        runtime, max_tokens=max_tokens, temperature=temperature, engine="chatgpt_plan"
    )
