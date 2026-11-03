import pytest

from app.multiagent.model_registry import ModelProfile, ModelRegistry, ModelRuntimeBindings
from app.application.ports.model_runtime import ModelInvocationResult, ModelRuntimeError, ModelUsage


def make_profile(model_id, provider_id):
    return ModelProfile(
        model_id=model_id,
        provider_id=provider_id,
        runtime_kind="remote_api",
        capabilities=frozenset({"chat", "tools"}),
        modalities=frozenset({"text"}),
    )


def test_multiple_providers_can_be_registered_together():
    registry = ModelRegistry([make_profile("a", "api-a"), make_profile("b", "local")])
    assert {item.provider_id for item in registry.list_profiles()} == {"api-a", "local"}


def test_eligibility_uses_capabilities_and_modalities():
    text = make_profile("text", "api-a")
    vision = ModelProfile(
        model_id="vision",
        provider_id="api-b",
        runtime_kind="local_runtime",
        capabilities=frozenset({"chat", "vision"}),
        modalities=frozenset({"text", "image"}),
    )
    registry = ModelRegistry([text, vision])
    assert [item.model_id for item in registry.eligible(
        required_capabilities={"vision"}, required_modalities={"text", "image"}
    )] == ["vision"]


def test_provider_filter_is_optional():
    registry = ModelRegistry([make_profile("a", "api-a"), make_profile("b", "api-b")])
    assert [item.model_id for item in registry.eligible()] == ["a", "b"]
    assert [item.model_id for item in registry.eligible(provider_ids={"api-b"})] == ["b"]
    assert [item.model_id for item in registry.eligible(provider_ids=[])] == ["a", "b"]


def test_unavailable_models_are_excluded():
    unavailable = ModelProfile(
        model_id="offline", provider_id="local", runtime_kind="local_runtime",
        available=False,
    )
    assert ModelRegistry([unavailable]).eligible() == ()


def test_duplicate_requires_explicit_replacement():
    registry = ModelRegistry([make_profile("a", "api-a")])
    with pytest.raises(ValueError, match="already registered"):
        registry.register(make_profile("a", "api-b"))
    registry.register(make_profile("a", "api-b"), replace=True)
    assert registry.get("a").provider_id == "api-b"


def test_unregister_is_idempotent():
    registry = ModelRegistry([make_profile("a", "api-a")])
    assert registry.unregister("a") is True
    assert registry.unregister("a") is False


def test_profile_snapshots_mutable_capabilities_and_metadata():
    capabilities = {"chat"}
    modalities = {"text"}
    metadata = {"region": "local"}
    profile = ModelProfile(
        model_id="snapshot",
        provider_id="provider",
        runtime_kind="local_runtime",
        capabilities=capabilities,
        modalities=modalities,
        metadata=metadata,
    )

    capabilities.add("admin")
    modalities.add("image")
    metadata["region"] = "remote"

    assert profile.capabilities == frozenset({"chat"})
    assert profile.modalities == frozenset({"text"})
    assert profile.metadata["region"] == "local"
    with pytest.raises(TypeError):
        profile.metadata["region"] = "changed"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"capabilities": {"chat", 42}},
        {"capabilities": "tools"},
        {"modalities": "text"},
        {"modalities": {"text", ""}},
        {"metadata": {"": "value"}},
        {"metadata": {"key": 42}},
        {"max_concurrency": True},
        {"available": 1},
        {"estimated_latency_ms": float("nan")},
        {"estimated_cost_per_1k_tokens": float("inf")},
    ],
)
def test_profile_rejects_invalid_metadata_and_operational_values(kwargs):
    with pytest.raises((TypeError, ValueError)):
        ModelProfile(
            model_id="invalid",
            provider_id="provider",
            runtime_kind="local_runtime",
            **kwargs,
        )


@pytest.mark.parametrize(
    "filters",
    [
        {"required_capabilities": "vision"},
        {"required_modalities": "text"},
        {"provider_ids": "api-a"},
    ],
)
def test_eligibility_rejects_scalar_string_filters(filters):
    registry = ModelRegistry([make_profile("a", "api-a")])

    with pytest.raises(TypeError):
        registry.eligible(**filters)



class FakeRuntime:
    supports_cancellation = False

    def __init__(self, provider_id="provider"):
        self.provider_id = provider_id
        self.calls = []

    def invoke(self, request):
        self.calls.append(request)
        return ModelInvocationResult(
            provider_id=self.provider_id,
            model_id=request.model_id or "default",
            content="ok",
            usage=ModelUsage(),
        )

    def cancel(self, request_id):
        return False


def test_runtime_bindings_resolve_exact_provider_for_registered_profile():
    profile = make_profile("model-a", "provider-a")
    runtime = FakeRuntime("provider-a")
    bindings = ModelRuntimeBindings({"provider-a": runtime})

    assert bindings.resolve(profile) is runtime
    assert bindings.list_provider_ids() == ("provider-a",)


def test_runtime_bindings_reject_missing_provider_adapter():
    bindings = ModelRuntimeBindings()

    with pytest.raises(ModelRuntimeError, match="No runtime adapter"):
        bindings.resolve(make_profile("model-a", "provider-missing"))


def test_runtime_bindings_reject_unavailable_model_before_dispatch():
    profile = ModelProfile(
        model_id="offline", provider_id="provider-a",
        runtime_kind="remote_api", available=False,
    )
    bindings = ModelRuntimeBindings({"provider-a": FakeRuntime("provider-a")})

    with pytest.raises(ModelRuntimeError, match="marked unavailable"):
        bindings.resolve(profile)


def test_runtime_bindings_reject_provider_identity_mismatch():
    with pytest.raises(ValueError, match="does not match"):
        ModelRuntimeBindings({"provider-a": FakeRuntime("provider-b")})


def test_runtime_bindings_require_explicit_replacement():
    first = FakeRuntime("provider-a")
    second = FakeRuntime("provider-a")
    bindings = ModelRuntimeBindings({"provider-a": first})

    with pytest.raises(ValueError, match="already bound"):
        bindings.register("provider-a", second)
    bindings.register("provider-a", second, replace=True)
    assert bindings.resolve(make_profile("model-a", "provider-a")) is second
