# -*- coding: utf-8 -*-
"""Tests for JarvisNexus.resolve_class and NexusComponent direct-instantiation warning."""

import logging
from unittest.mock import patch

import pytest

from app.core.nexus import JarvisNexus, NexusComponent
from app.core.nexuscomponent import (
    _class_to_component_id,
    _nexus_context,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Fragment of the warning message emitted on direct instantiation.
# Centralised here so tests don't break if the message wording changes.
_DIRECT_INSTANTIATION_WARNING_FRAGMENT = "instanciado diretamente"


class _ConcreteComponent(NexusComponent):
    """Minimal concrete NexusComponent used for testing."""

    def __init__(self) -> None:
        self.initialized = True

    def execute(self, context=None):
        return {"success": True}


class _ComponentNoInit(NexusComponent):
    """Concrete NexusComponent that does NOT define its own __init__."""

    def execute(self, context=None):
        return {"success": True}


# ---------------------------------------------------------------------------
# _class_to_component_id
# ---------------------------------------------------------------------------

class TestClassToComponentId:
    def test_simple_pascal_case(self):
        assert _class_to_component_id("AuditLogger") == "audit_logger"

    def test_single_word(self):
        assert _class_to_component_id("Service") == "service"

    def test_acronym_in_name(self):
        assert _class_to_component_id("LLMService") == "llm_service"

    def test_already_lower(self):
        assert _class_to_component_id("myclass") == "myclass"

    def test_multi_word(self):
        assert _class_to_component_id("CapabilityManager") == "capability_manager"


# ---------------------------------------------------------------------------
# NexusComponent direct-instantiation warning
# ---------------------------------------------------------------------------

class TestNexusComponentDirectInstantiationWarning:
    """NexusComponent subclasses must warn when created directly."""

    def test_direct_instantiation_emits_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="app.core.nexuscomponent"):
            comp = _ConcreteComponent()

        assert comp.initialized is True  # instantiation succeeds
        assert any(_DIRECT_INSTANTIATION_WARNING_FRAGMENT in msg for msg in caplog.messages), (
            "Expected a direct-instantiation warning but got none."
        )

    def test_direct_instantiation_warning_contains_component_name(self, caplog):
        with caplog.at_level(logging.WARNING, logger="app.core.nexuscomponent"):
            _ConcreteComponent()

        assert any("_ConcreteComponent" in msg for msg in caplog.messages)

    def test_direct_instantiation_warning_contains_snake_case_id(self, caplog):
        with caplog.at_level(logging.WARNING, logger="app.core.nexuscomponent"):
            _ConcreteComponent()

        assert any("_concrete_component" in msg for msg in caplog.messages)

    def test_no_warning_when_resolving_flag_is_set(self, caplog):
        """When _nexus_context.resolving is True, no warning should be emitted."""
        _nexus_context.resolving = True
        try:
            with caplog.at_level(logging.WARNING, logger="app.core.nexuscomponent"):
                comp = _ConcreteComponent()
        finally:
            _nexus_context.resolving = False

        assert comp.initialized is True
        assert not any(_DIRECT_INSTANTIATION_WARNING_FRAGMENT in msg for msg in caplog.messages), (
            "No warning should be emitted when Nexus context flag is set."
        )

    def test_class_without_init_is_not_wrapped(self, caplog):
        """Subclasses that don't define __init__ should not get the wrapper."""
        with caplog.at_level(logging.WARNING, logger="app.core.nexuscomponent"):
            comp = _ComponentNoInit()

        assert isinstance(comp, _ComponentNoInit)
        # No warning because the class has no custom __init__ to wrap
        assert not any(_DIRECT_INSTANTIATION_WARNING_FRAGMENT in msg for msg in caplog.messages)

    def test_warning_does_not_block_execution(self):
        """Direct instantiation must never raise an exception."""
        comp = _ConcreteComponent()  # must not raise
        assert comp.execute() == {"success": True}


# ---------------------------------------------------------------------------
# JarvisNexus.resolve_class
# ---------------------------------------------------------------------------

class TestResolveClass:
    """Tests for JarvisNexus.resolve_class."""

    def test_resolve_class_returns_class_from_hint_path(self, tmp_path):
        """resolve_class should return the class from a known hint_path."""
        nexus = JarvisNexus()

        # Patch _find_class_from_path to simulate successful discovery
        def _fake_find(module_path, target_id):
            return _ConcreteComponent

        with patch.object(nexus, "_find_class_from_path", side_effect=_fake_find):
            cls = nexus.resolve_class(
                "_concrete_component",
                hint_path="app.fake.module",
            )

        assert cls is _ConcreteComponent

    def test_resolve_class_uses_cache(self):
        """resolve_class should look up the registered path in the cache."""
        nexus = JarvisNexus()
        nexus._cache["my_comp"] = "app.some.module"

        def _fake_find(module_path, target_id):
            assert module_path == "app.some.module"
            return _ConcreteComponent

        with patch.object(nexus, "_find_class_from_path", side_effect=_fake_find):
            cls = nexus.resolve_class("my_comp")

        assert cls is _ConcreteComponent

    def test_resolve_class_returns_none_when_not_found(self):
        """resolve_class returns None for unknown components (strict mode)."""
        import os
        with patch.dict(os.environ, {"NEXUS_STRICT_MODE": "true"}):
            nexus = JarvisNexus()
            # Clear the cache so nothing is found
            nexus._cache.clear()
            nexus._path_map.clear()

            # Import-time constant was already read, so patch the module-level var
            import app.core.nexus as nexus_module
            original = nexus_module._NEXUS_STRICT_MODE
            nexus_module._NEXUS_STRICT_MODE = True
            try:
                cls = nexus.resolve_class("definitely_nonexistent_xyz")
            finally:
                nexus_module._NEXUS_STRICT_MODE = original

        assert cls is None

    def test_resolve_class_returns_type(self):
        """The returned object from resolve_class must be a class (type)."""
        nexus = JarvisNexus()
        nexus._cache["concrete_component"] = "app.fake.path"

        with patch.object(nexus, "_find_class_from_path", return_value=_ConcreteComponent):
            cls = nexus.resolve_class("concrete_component")

        assert isinstance(cls, type)

    def test_resolve_class_can_be_instantiated(self, caplog):
        """A class returned by resolve_class can be instantiated without warning."""
        nexus = JarvisNexus()
        nexus._cache["concrete_component"] = "app.fake.path"

        with patch.object(nexus, "_find_class_from_path", return_value=_ConcreteComponent):
            cls = nexus.resolve_class("concrete_component")

        assert cls is not None

        # Simulate Nexus-controlled instantiation (flag set by _nexus_guarded_instantiate)
        _nexus_context.resolving = True
        try:
            with caplog.at_level(logging.WARNING, logger="app.core.nexuscomponent"):
                instance = cls()
        finally:
            _nexus_context.resolving = False

        assert instance.initialized is True
        assert not any(_DIRECT_INSTANTIATION_WARNING_FRAGMENT in msg for msg in caplog.messages)


# ---------------------------------------------------------------------------
# _nexus_guarded_instantiate integration
# ---------------------------------------------------------------------------

class TestNexusGuardedInstantiate:
    """Ensure the thread-pool instantiation path suppresses the warning."""

    def test_nexus_resolve_suppresses_warning(self, caplog):
        """When resolve() instantiates a component, no warning should be emitted."""
        from app.core.nexus import _nexus_guarded_instantiate

        with caplog.at_level(logging.WARNING, logger="app.core.nexuscomponent"):
            instance = _nexus_guarded_instantiate(_ConcreteComponent)

        assert instance.initialized is True
        assert not any(_DIRECT_INSTANTIATION_WARNING_FRAGMENT in msg for msg in caplog.messages)

    def test_nexus_context_flag_cleared_after_instantiation(self):
        """The resolving flag must be False after _nexus_guarded_instantiate returns."""
        from app.core.nexus import _nexus_guarded_instantiate

        _nexus_guarded_instantiate(_ConcreteComponent)
        # Flag must be cleared even after successful return
        assert not getattr(_nexus_context, "resolving", False)

    def test_nexus_context_flag_cleared_on_exception(self):
        """The resolving flag must be False even if the constructor raises."""
        from app.core.nexus import _nexus_guarded_instantiate

        class _BrokenComponent:
            def __init__(self):
                raise RuntimeError("constructor failure")

        with pytest.raises(RuntimeError):
            _nexus_guarded_instantiate(_BrokenComponent)

        assert not getattr(_nexus_context, "resolving", False)
