from pathlib import Path


def test_heartbeat_reconciliation_migration_rejects_stale_agents_safely():
    migration = (
        Path(__file__).resolve().parents[2]
        / "supabase"
        / "migrations"
        / "20261028100000_agent_heartbeat_reconciliation.sql"
    )
    sql = migration.read_text(encoding="utf-8").lower()

    assert "create or replace function public.mark_stale_jarvis_agents_offline" in sql
    assert "last_seen_at is null" in sql
    assert "for update skip locked" in sql
    assert "v_agent.last_seen_at <= now() - make_interval" in sql
    assert "perform public.mark_stale_jarvis_agents_offline(v_heartbeat_timeout)" in sql
    assert "revoke all on function public.mark_stale_jarvis_agents_offline(integer)" in sql
    assert "grant execute on function public.mark_stale_jarvis_agents_offline(integer)" in sql
    assert "to service_role" in sql
