from pathlib import Path


def test_worker_credential_migration_is_hash_only_and_service_role_scoped():
    migration = (
        Path(__file__).resolve().parents[2]
        / "supabase"
        / "migrations"
        / "20261107183000_agent_worker_credentials.sql"
    )
    sql = migration.read_text(encoding="utf-8").lower()

    assert "create table if not exists public.jarvis_agent_credentials" in sql
    assert "token_hash text not null unique" in sql
    assert "check (token_hash ~ '^[0-9a-f]{64}$')" in sql
    assert "available_tools jsonb not null" in sql
    assert "alter table public.jarvis_agent_credentials enable row level security" in sql
    assert "revoke all on table public.jarvis_agent_credentials from public, anon, authenticated" in sql
    assert "grant select, insert, update, delete on table public.jarvis_agent_credentials to service_role" in sql
    assert "raw_token" not in sql
