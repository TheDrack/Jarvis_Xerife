from app.adapters.infrastructure.supabase_plan_journal import SupabasePlanEventJournal


class FakeResponse:
    error = None


class FakeTable:
    def __init__(self, rows):
        self.rows = rows
        self.row = None

    def insert(self, row):
        self.row = row
        return self

    def execute(self):
        self.rows.append(self.row)
        return FakeResponse()


class FakeClient:
    def __init__(self):
        self.rows = []
        self.table_names = []

    def table(self, name):
        self.table_names.append(name)
        return FakeTableProxy(self, name)


class FakeTableProxy:
    def __init__(self, client, name):
        self.client = client
        self.name = name

    def insert(self, row):
        assert self.name == "execution_plan_events"
        return FakeTable(self.client.rows).insert(row)


def test_journal_persists_only_allowlisted_metadata():
    client = FakeClient()
    journal = SupabasePlanEventJournal(client)
    journal.append({
        "event": "step_started",
        "execution_id": "exec-1",
        "step_id": "step-1",
        "tool": "lookup",
        "argument_keys": ["query"],
        "args": {"query": "private input"},
        "result": {"secret": "must not persist"},
    })

    assert client.table_names == ["execution_plan_events"]
    assert client.rows == [{
        "execution_id": "exec-1",
        "event_type": "step_started",
        "step_id": "step-1",
        "tool_name": "lookup",
        "status": None,
        "error_code": None,
        "duration_ms": None,
        "metadata": {"argument_keys": ["query"]},
    }]


def test_journal_rejects_unknown_events():
    import pytest

    journal = SupabasePlanEventJournal(FakeClient())
    with pytest.raises(ValueError, match="unsupported"):
        journal.append({"event": "unknown", "execution_id": "exec-1"})
