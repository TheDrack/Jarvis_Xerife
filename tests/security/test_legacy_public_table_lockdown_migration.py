from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    REPOSITORY_ROOT
    / "supabase"
    / "migrations"
    / "20261104192500_lock_down_legacy_public_tables.sql"
)
LEGACY_TABLES = {
    "capabilities",
    "command_results",
    "devices",
    "interactions",
    "jarvis_capabilities",
    "thought_logs",
    "user",
}


def test_legacy_table_lockdown_migration_covers_every_audited_table():
    sql = MIGRATION.read_text(encoding="utf-8")

    for table in LEGACY_TABLES:
        assert f"'{table}'" in sql


def test_legacy_table_lockdown_revokes_table_and_column_privileges():
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "REVOKE ALL PRIVILEGES ON TABLE" in sql
    assert "REVOKE ALL PRIVILEGES (%s) ON TABLE" in sql
    assert "FROM PUBLIC, anon, authenticated" in sql


def test_legacy_table_lockdown_removes_the_role_only_policy_idempotently():
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "DROP POLICY IF EXISTS" in sql
    assert "Enable all for authenticated users" in sql


def test_legacy_table_lockdown_does_not_revoke_service_role():
    sql = MIGRATION.read_text(encoding="utf-8")

    # The migration must preserve the server-only path used by AuthAdapter
    # and administrator recovery. It never mentions service_role in a revoke.
    revoke_statements = [
        statement
        for statement in sql.split(";")
        if "REVOKE" in statement.upper()
    ]
    assert revoke_statements
    assert all("service_role" not in statement.lower() for statement in revoke_statements)
