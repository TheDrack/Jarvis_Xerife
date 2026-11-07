from pathlib import Path


def test_task_ownership_migration_adds_nullable_provenance_and_owner_indexes():
    migration = (
        Path(__file__).resolve().parents[2]
        / "supabase"
        / "migrations"
        / "20261107210000_agent_task_ownership.sql"
    )
    sql = migration.read_text(encoding="utf-8").lower()

    assert "alter table public.jarvis_agent_tasks" in sql
    assert "add column if not exists created_by text" in sql
    assert "add column if not exists owner_id text" in sql
    assert "alter table public.jarvis_routine_definitions" in sql
    assert "jarvis_agent_tasks_owner_status_created_idx" in sql
    assert "jarvis_routine_definitions_owner_key_idx" in sql
    assert "where owner_id is not null" in sql
    assert "worker executor" in sql
