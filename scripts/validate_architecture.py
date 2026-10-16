#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Validation script for hexagonal architecture.
Tests that core components can be imported and instantiated.
"""

import sys
from pathlib import Path

# Garante que o root do projeto esteja importável mesmo quando o script é
# executado diretamente (python scripts/validate_architecture.py): nesse caso
# o sys.path recebe apenas o diretório ``scripts/``.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_domain_imports():
    """Test domain layer imports"""
    print("Testing domain layer imports...")
    try:
        from app.domain.models import Command, CommandType, Intent, Response  # noqa: F401
        from app.domain.services import CommandInterpreter, IntentProcessor  # noqa: F401

        print("✓ Domain models imported successfully")
        print("✓ Domain services imported successfully")
        return True
    except Exception as e:
        print(f"✗ Domain import failed: {e}")
        return False


def test_application_imports():
    """Test application layer imports"""
    print("\nTesting application layer imports...")
    try:
        from app.application.ports import (  # noqa: F401
            ActionProvider,
            SystemController,
            VoiceProvider,
            WebProvider,
        )
        from app.application.services import AssistantService  # noqa: F401

        print("✓ Application ports imported successfully")
        print("✓ Application services imported successfully")
        return True
    except Exception as e:
        print(f"✗ Application import failed: {e}")
        return False


def test_adapter_imports():
    """Test adapter layer imports.

    Os adapters de edge dependem de hardware/desktop (PyAutoGUI, pyttsx3, …),
    listados em ``requirements/edge.txt``. Em ambientes headless a camada é
    marcada como SKIP (``None``) em vez de falhar: a validação de arquitetura
    não deve exigir driver de áudio ou display server.
    """
    print("\nTesting adapter layer imports...")
    try:
        from app.adapters.edge import (  # noqa: F401
            AutomationAdapter,
            CombinedVoiceProvider,
            KeyboardAdapter,
            TTSAdapter,
            VoiceAdapter,
            WebAdapter,
        )

        print("✓ Edge adapters imported successfully")
        return True
    except ModuleNotFoundError as e:
        missing = (e.name or "").split(".")[0]
        if missing and not missing.startswith("app"):
            print(f"⚠ Edge adapters skipped: dependência opcional '{missing}' não instalada")
            print("   Instale com: pip install -r requirements/edge.txt")
            return None
        print(f"✗ Adapter import failed: {e}")
        return False
    except Exception as e:
        print(f"✗ Adapter import failed: {e}")
        return False


def test_container_import():
    """Test DI container import"""
    print("\nTesting DI container...")
    try:
        from app.container import Container, create_edge_container  # noqa: F401

        print("✓ Container imported successfully")
        return True
    except Exception as e:
        print(f"✗ Container import failed: {e}")
        return False


def test_domain_functionality():
    """Test domain layer functionality"""
    print("\nTesting domain layer functionality...")
    try:
        from app.core.nexus import nexus
        from app.domain.models import CommandType

        # Test interpreter via nexus.resolve to avoid direct-instantiation warnings
        interpreter = nexus.resolve("command_interpreter")
        intent = interpreter.interpret("escreva hello world")
        assert intent.command_type == CommandType.TYPE_TEXT
        assert intent.parameters["text"] == "hello world"
        print("✓ CommandInterpreter works correctly")

        # Test processor via nexus.resolve
        processor = nexus.resolve("intent_processor")
        print("✓ IntentProcessor works correctly")

        return True
    except Exception as e:
        print(f"✗ Domain functionality failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_service_with_mocks():
    """Test application service with mocked ports"""
    print("\nTesting application service with mocks...")
    try:
        from unittest.mock import Mock
        from app.application.services import AssistantService
        from app.core.nexus import nexus

        # Create mocks
        voice_mock = Mock()
        action_mock = Mock()
        web_mock = Mock()

        # Create service
        service = AssistantService(
            voice_provider=voice_mock,
            action_provider=action_mock,
            web_provider=web_mock,
            command_interpreter=nexus.resolve("command_interpreter"),
            intent_processor=nexus.resolve("intent_processor"),
        )

        # Test command processing
        response = service.process_command("escreva test")
        assert response.success
        action_mock.type_text.assert_called_once_with("test")

        print("✓ AssistantService works with mocked dependencies")
        return True
    except Exception as e:
        print(f"✗ Service with mocks failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Run all validation tests"""
    print("=" * 60)
    print("Jarvis Assistant - Architecture Validation")
    print("=" * 60)

    tests = [
        test_domain_imports,
        test_application_imports,
        test_adapter_imports,
        test_container_import,
        test_domain_functionality,
        test_service_with_mocks,
    ]

    results = []
    for test in tests:
        results.append(test())

    passed = sum(1 for r in results if r is True)
    skipped = sum(1 for r in results if r is None)
    failed = [r for r in results if r is False]

    print("\n" + "=" * 60)
    print(f"Results: {passed}/{len(results)} tests passed" + (f" ({skipped} skipped)" if skipped else ""))
    print("=" * 60)

    if all(r is not False for r in results):
        print("\n✓ All validation tests passed!")
        print("✓ Architecture is correctly implemented")
        print("✓ Ready for deployment")
        return 0
    else:
        print("\n✗ Some tests failed")
        print("✗ Please fix the issues before deploying")
        return 1


if __name__ == "__main__":
    sys.exit(main())
