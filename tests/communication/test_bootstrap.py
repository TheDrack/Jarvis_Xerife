from app.communication import create_default_communication_registry


def test_default_registry_registers_chatgpt_adapter_without_authentication():
    registry = create_default_communication_registry(
        oauth_factory=lambda: (_ for _ in ()).throw(AssertionError("must be lazy"))
    )
    assert registry.list_adapters() == ("openai.chatgpt_plan",)
    adapter = registry.resolve("openai.chatgpt_plan")
    assert adapter.protocol == "https"
