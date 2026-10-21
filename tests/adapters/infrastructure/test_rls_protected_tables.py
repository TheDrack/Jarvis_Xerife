# -*- coding: utf-8 -*-
"""Guard tests for the dynamically discovered RLS_PROTECTED_TABLES list.

These tests keep ``RLS_PROTECTED_TABLES`` honest: every migration that enables
Row Level Security must be picked up automatically, and the health-check guard
must actually query for the resulting tables.
"""

import re
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from app.adapters.infrastructure import api_server
from app.adapters.infrastructure.api_server import (
    RLS_PROTECTED_TABLES,
    _discover_rls_protected_tables,
    create_api_server,
)
from app.application.services import AssistantService

REPO_ROOT = Path(api_server.__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "migrations"


@pytest.fixture
def mock_assistant_service():
    service = Mock(spec=AssistantService)
    service.wake_word = "xerife"
    service.is_running = False
    service._command_history = []
    service.interpreter = Mock()
    return service


class TestRlsTableDiscovery:
    """Discovery must mirror what the SQL migrations actually protect."""

    def test_discovery_returns_expected_tables(self):
        assert RLS_PROTECTED_TABLES == _discover_rls_protected_tables()

    def test_every_migration_with_rls_is_covered(self):
        """Any migration enabling RLS must appear in the protected list.

        This is the regression guard: adding a new table with
        ``ENABLE ROW LEVEL SECURITY`` requires no manual update of
        ``RLS_PROTECTED_TABLES`` anymore.
        """
        rls_re = re.compile(
            r"ALTER\s+TABLE\s+[\"']?(\w+)[\"']?\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY",
            re.IGNORECASE,
        )
        expected = set()
        for sql_file in MIGRATIONS_DIR.glob("*.sql"):
            expected.update(m.lower() for m in rls_re.findall(sql_file.read_text(encoding="utf-8")))

        missing = expected - set(RLS_PROTECTED_TABLES)
        assert not missing, f"Migrations enable RLS but health check ignores them: {missing}"

    def test_list_is_non_empty(self):
        assert len(RLS_PROTECTED_TABLES) > 0

    def test_fallback_when_migrations_missing(self, tmp_path):
        """If no migrations are shipped, the static fallback keeps the guard alive."""
        import app.adapters.infrastructure.api_server as mod

        # Discovery resolves ``migrations/`` from ``Path(__file__).parents[3]``.
        # Patch only the constructor call (``Path(__file__)``) so that
        # ``.resolve().parents[3]`` lands in an empty temporary directory.
        anchor = tmp_path / "pkg" / "sub" / "deep" / "file.py"
        anchor.parent.mkdir(parents=True, exist_ok=True)
        anchor.touch()
        # parents[3] of anchor == tmp_path (empty -> no *.sql files)

        with patch.object(mod, "Path", side_effect=lambda *_a, **_kw: anchor):
            result = mod._discover_rls_protected_tables()

        assert result == sorted(mod._RLS_STATIC_FALLBACK_TABLES)
        assert len(result) > 0

    def test_static_fallback_matches_known_protected_tables(self):
        assert set(api_server._RLS_STATIC_FALLBACK_TABLES).issubset(set(RLS_PROTECTED_TABLES))


class TestHealthCheckUsesDynamicList:
    """The /health RLS query must include every dynamically discovered table."""

    def test_health_query_includes_all_protected_tables(self, mock_assistant_service):
        app = create_api_server(mock_assistant_service)
        client = TestClient(app)

        captured = {}

        class MockSession:
            def __init__(self, engine):
                self.engine = engine

            def exec(self, query):
                captured["sql"] = str(query)
                result = Mock()
                result.fetchall.return_value = [
                    ("public", table, True) for table in RLS_PROTECTED_TABLES
                ]
                return result

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

        with patch("app.core.config.settings.database_url",
                   "postgresql://user:pass@localhost/jarvis"), \
             patch("sqlmodel.Session", MockSession):
            response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["security"]["rls_enabled"] is True
        # Every protected table appears both in the SQL IN clause and the report
        for table in RLS_PROTECTED_TABLES:
            assert f"'{table}'" in captured["sql"]
            assert table in data["security"]["tables_checked"]
