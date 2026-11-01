from app.multiagent.model_registry import ModelProfile, ModelRegistry


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


def test_unavailable_models_are_excluded():
    unavailable = ModelProfile(
        model_id="offline", provider_id="local", runtime_kind="local_runtime",
        available=False,
    )
    assert ModelRegistry([unavailable]).eligible() == ()


def test_duplicate_requires_explicit_replacement():
    registry = ModelRegistry([make_profile("a", "api-a")])
    try:
        registry.register(make_profile("a", "api-b"))
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate model registration must fail")
    registry.register(make_profile("a", "api-b"), replace=True)
    assert registry.get("a").provider_id == "api-b"


def test_unregister_is_idempotent():
    registry = ModelRegistry([make_profile("a", "api-a")])
    assert registry.unregister("a") is True
    assert registry.unregister("a") is False
