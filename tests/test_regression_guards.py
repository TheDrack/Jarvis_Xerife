# -*- coding: utf-8 -*-
"""Regression guards.

These tests exist to make sure the specific defect classes fixed in this
repository never come back:

1. Broken Python files (indentation / joined lines) that cannot even be parsed.
2. Undefined names (NameError at runtime) left behind by refactors.
3. The JarvisNexus public API (methods silently dropped by a rewrite).
4. Public adapter contracts (telegram / github / gateway) that tests and
   production code depend on.
5. Naive ``datetime`` values persisted into timezone-aware SQLModel columns.
6. Runtime dependencies that are imported but not declared.

They are deliberately cheap (static analysis + imports) so they can run on
every change.
"""

import ast
import importlib
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Directories that never contain shippable source.
_EXCLUDED_DIRS = {".git", ".venv", "venv", "__pycache__", ".backups", "backups",
                  "node_modules", ".pytest_cache", ".mypy_cache", "htmlcov"}


def _iter_project_python_files():
    for path in PROJECT_ROOT.rglob("*.py"):
        if any(part in _EXCLUDED_DIRS for part in path.parts):
            continue
        yield path


# ---------------------------------------------------------------------------
# 1. Syntax integrity — every source file must parse.
# ---------------------------------------------------------------------------

class TestSourceSyntax:
    def test_every_python_file_parses(self):
        broken = []
        for path in _iter_project_python_files():
            try:
                ast.parse(path.read_text(encoding="utf-8", errors="replace"))
            except SyntaxError as exc:
                broken.append(f"{path.relative_to(PROJECT_ROOT)}:{exc.lineno}: {exc.msg}")
        assert broken == [], "Arquivos com erro de sintaxe:\n" + "\n".join(broken)

    def test_no_conflict_markers_left_behind(self):
        offenders = []
        for path in _iter_project_python_files():
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                if line.startswith(("<<<<<<<", ">>>>>>>")) or line.rstrip() == "=======":
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}:{lineno}")
        assert offenders == [], "Marcadores de conflito encontrados:\n" + "\n".join(offenders)


# ---------------------------------------------------------------------------
# 2. Undefined names — the defect class behind several NameError bugs.
# ---------------------------------------------------------------------------

class TestNoUndefinedNames:
    def test_pyflakes_reports_no_undefined_names_in_app(self):
        pytest.importorskip("pyflakes", reason="pyflakes é uma dependência de desenvolvimento")
        result = subprocess.run(
            [sys.executable, "-m", "pyflakes", "app"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        undefined = [
            line for line in result.stdout.splitlines()
            if "undefined name" in line or "maybe undefined" in line
        ]
        assert undefined == [], "Nomes indefinidos:\n" + "\n".join(undefined)


# ---------------------------------------------------------------------------
# 3. JarvisNexus public API contract.
# ---------------------------------------------------------------------------

class TestNexusContract:
    def test_public_methods_and_attributes_exist(self):
        from app.core.nexus import JarvisNexus, Nexus, nexus

        assert Nexus is JarvisNexus
        for attr in (
            "list_loaded_ids",
            "resolve_class",
            "resolve",
            "invalidate_component",
            "register_metrics_collector",
            "load_dna",
            "_load_local_registry",
            "_update_local_registry",
            "_find_class_from_path",
            "_locate_class",
            "_global_search_with_path",
        ):
            assert hasattr(JarvisNexus, attr), f"JarvisNexus perdeu '{attr}'"

        assert hasattr(nexus, "_circuit_breaker")

    def test_nexus_re_exports(self):
        from app.core import nexus as nexus_module

        for attr in ("CloudMock", "NexusComponent", "AmbiguousComponentError",
                     "CIRCUIT_BREAKER_RESET", "_nexus_guarded_instantiate",
                     "_NEXUS_STRICT_MODE"):
            assert hasattr(nexus_module, attr), f"app.core.nexus não exporta '{attr}'"

    def test_list_loaded_ids_returns_list(self):
        from app.core.nexus import nexus

        assert isinstance(nexus.list_loaded_ids(), list)

    def test_registry_mixin_exposes_expected_helpers(self):
        from app.core.nexus import JarvisNexus
        from app.core.nexus_registry import _NexusRegistryMixin

        assert issubclass(JarvisNexus, _NexusRegistryMixin)
        for attr in ("_load_local_registry", "_update_local_registry",
                     "_load_remote_memory", "commit_memory"):
            assert hasattr(_NexusRegistryMixin, attr), f"_NexusRegistryMixin perdeu '{attr}'"


# ---------------------------------------------------------------------------
# 4. Core model / service behaviour.
# ---------------------------------------------------------------------------

class TestAdapterRegistry:
    def test_execute_handles_all_actions(self):
        from app.domain.models.adapter_registry import AdapterRegistry

        reg = AdapterRegistry()
        assert reg.execute({"action": "list"})["success"] is True
        assert reg.execute({"action": "refresh"})["success"] is True
        assert reg.execute({"action": "get", "adapter_id": "llm_router"})["adapter"] is not None
        gap = reg.execute({"action": "find_gap", "capability": "enviar fax"})
        assert gap["success"] is True
        assert gap["gap"]["missing_adapter"] is True
        assert reg.execute({"action": "nope"})["success"] is False

    def test_suggest_adapter_id_normalises(self):
        from app.domain.models.adapter_registry import AdapterRegistry

        assert AdapterRegistry()._suggest_adapter_id("Enviar Email") == "enviar_email_adapter"


class TestAgentActionFromDict:
    def test_from_dict_uses_data_argument(self):
        from app.domain.models.agent import ActionType, AgentAction

        action = AgentAction.from_dict(
            {"action_type": "run_tests", "parameters": {"x": 1},
             "reasoning": "r", "step_number": 3}
        )
        assert action.action_type is ActionType.RUN_TESTS
        assert action.parameters == {"x": 1}
        assert action.step_number == 3


class TestConsolidatorHasJson:
    def test_json_module_is_imported(self):
        import app.adapters.infrastructure.consolidator as consolidator

        assert hasattr(consolidator, "json")


# ---------------------------------------------------------------------------
# 5. Inventory of adapters/services whose API regressed before.
# ---------------------------------------------------------------------------

class TestAdapterContracts:
    def test_telegram_adapter_bidirectional_api(self):
        from app.adapters.infrastructure import telegram_adapter as mod

        assert hasattr(mod, "HttpClient"), "telegram_adapter deve expor HttpClient"
        assert hasattr(mod, "_RENDER_WAKE_TIMEOUT")
        adapter = mod.TelegramAdapter()
        for attr in ("send_message", "send_document", "get_updates",
                     "handle_update", "start_polling", "stop_polling",
                     "_is_render_available"):
            assert hasattr(adapter, attr), f"TelegramAdapter perdeu '{attr}'"
        assert hasattr(adapter, "_render_url")

        # main.py calls send_message(chat_id=..., text=...); keep it compatible.
        import inspect
        params = inspect.signature(adapter.send_message).parameters
        assert "text" in params and "chat_id" in params

    def test_gateway_llm_adapter_patchable_symbols(self):
        from app.adapters.infrastructure import gateway_llm_adapter as mod

        for attr in ("AIGateway", "LLMProvider", "LLMCommandAdapter",
                     "GitHubAdapter", "HistoryProvider"):
            assert hasattr(mod, attr), f"gateway_llm_adapter não expõe '{attr}'"

    def test_github_adapter_legacy_delegators(self):
        from app.adapters.infrastructure.github_adapter import GitHubAdapter

        for attr in ("dispatch_auto_fix", "report_for_auto_correction",
                     "create_issue", "_get_headers", "_ensure_client"):
            assert hasattr(GitHubAdapter, attr), f"GitHubAdapter perdeu '{attr}'"

    def test_jrvs_cloud_storage_client_helper(self):
        from app.adapters.infrastructure.jrvs_cloud_storage import JrvsCloudStorage

        assert hasattr(JrvsCloudStorage, "_get_client")

    def test_drive_uploader_service_helper(self):
        from app.adapters.infrastructure.drive_uploader import DriveUploader

        assert hasattr(DriveUploader, "_get_service")

    def test_reward_signal_provider_full_api(self):
        from app.domain.services import reward_signal_provider as mod

        assert hasattr(mod, "_REPLAY_BUFFER_FILE")
        assert hasattr(mod, "_ThoughtLogAudit")
        for attr in ("_calculate_legacy_reward", "calculate_penalty",
                     "record_experience", "get_replay_buffer"):
            assert hasattr(mod.RewardSignalProvider, attr), \
                f"RewardSignalProvider perdeu '{attr}'"


# ---------------------------------------------------------------------------
# 6. Timezone-aware persistence.
# ---------------------------------------------------------------------------

def _aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


class TestTimezoneAwareDefaults:
    @pytest.mark.parametrize("module_path,class_name,fields", [
        ("app.domain.models.device", "Device", ("last_seen", "created_at")),
        ("app.domain.models.capability", "JarvisCapability", ("created_at", "updated_at")),
        ("app.domain.models.evolution_reward", "EvolutionReward", ("created_at",)),
    ])
    def test_model_defaults_are_aware(self, module_path, class_name, fields):
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        fields_info = getattr(cls, "model_fields", None)
        if fields_info is None:  # pragma: no cover - older pydantic
            fields_info = cls.__fields__
        for field in fields:
            info = fields_info[field]
            factory = getattr(info, "default_factory", None)
            assert factory is not None, f"{class_name}.{field} precisa de default_factory"
            value = factory()
            assert _aware(value), f"{class_name}.{field} gera datetime naive"

    def test_sqlite_history_adapter_coerces_naive_timestamps(self):
        from app.adapters.infrastructure.sqlite_history_adapter import _ensure_aware

        naive = datetime(2024, 1, 1, 12, 0, 0)
        coerced = _ensure_aware(naive)
        assert _aware(coerced)
        assert coerced.replace(tzinfo=None) == naive
        # Already-aware values pass through unchanged and None yields "now".
        aware = datetime.now(timezone.utc)
        assert _ensure_aware(aware) is aware
        assert _aware(_ensure_aware(None))

    def test_sqlite_interaction_timestamp_default_is_aware(self):
        from app.adapters.infrastructure.sqlite_history_adapter import Interaction

        assert _aware(Interaction().timestamp)


# ---------------------------------------------------------------------------
# 7. Declared runtime dependencies.
# ---------------------------------------------------------------------------

class TestDeclaredDependencies:
    def test_requests_is_declared_and_importable(self):
        import requests  # noqa: F401  (must be installable)

        reqs = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
        assert "requests" in reqs, "requests é importado pelo runtime mas não está em requirements.txt"
