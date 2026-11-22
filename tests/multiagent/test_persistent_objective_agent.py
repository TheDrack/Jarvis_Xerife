from __future__ import annotations

import pytest

from app.multiagent.objective_journal import ObjectiveJournal
from app.multiagent.persistent_objective_agent import (
    PersistentObjectiveHandler,
    objective_journal_enabled,
    wrap_handler_with_objective_journal,
)
from app.multiagent.transport import AgentMessage


def _message(attempt_id: str = "00000000-0000-0000-0000-000000000001", context: str = ""):
    return AgentMessage.create(
        task_id="task-1",
        sender_id="jarvis-leader",
        recipient_id="jarvis-termux-mini-1",
        kind="request",
        payload={
            "attempt_id": attempt_id,
            "objective": "Prepare the weekly AI curation",
            "task_type": "research",
            "context": context,
            "constraints": ["text only"],
            "acceptance_criteria": ["sources cited"],
        },
    )


def test_handler_persists_progress_and_completes_the_objective(tmp_path):
    journal = ObjectiveJournal(tmp_path / "journal.sqlite3")
    calls: list[AgentMessage] = []

    def delegate(message):
        calls.append(message)
        return {"success": True, "output": "curation ready"}

    handler = PersistentObjectiveHandler(delegate, journal)
    result = handler(_message())

    assert result == {"success": True, "output": "curation ready"}
    assert len(calls) == 1
    summary = journal.summary()
    assert summary["total"] == 1
    assert summary["by_status"] == {"completed": 1}


def test_retry_receives_persisted_progress_and_completed_objective_is_replayed(tmp_path):
    journal = ObjectiveJournal(tmp_path / "journal.sqlite3")
    first_attempt = "00000000-0000-0000-0000-000000000001"
    journal.begin_attempt(
        task_id="task-1", agent_id="jarvis-termux-mini-1",
        objective="Prepare the weekly AI curation", attempt_id=first_attempt,
    )
    step = journal.start_step(task_id="task-1", attempt_id=first_attempt)
    journal.finish_step(
        task_id="task-1", attempt_id=first_attempt, step_index=step,
        output="outline drafted: three sections",
    )

    seen: list[AgentMessage] = []

    def delegate(message):
        seen.append(message)
        return {"success": True, "output": "curation ready"}

    handler = PersistentObjectiveHandler(delegate, journal)
    handler(_message(attempt_id="00000000-0000-0000-0000-000000000002", context="remote note"))

    assert "outline drafted: three sections" in seen[0].payload["context"]
    assert "remote note" in seen[0].payload["context"]

    replay = handler(_message(attempt_id="00000000-0000-0000-0000-000000000003"))

    assert len(seen) == 1, "a completed objective must not invoke the model again"
    assert replay["output"] == "curation ready"
    assert replay["replayed_from_journal"] is True


def test_failed_inference_keeps_the_objective_resumable(tmp_path):
    journal = ObjectiveJournal(tmp_path / "journal.sqlite3")

    def delegate(message):
        raise RuntimeError("provider-token-must-not-be-stored")

    handler = PersistentObjectiveHandler(delegate, journal)
    with pytest.raises(RuntimeError):
        handler(_message())

    summary = journal.summary()
    assert summary["by_status"] == {"active": 1}
    assert summary["active"][0]["last_error_type"] == "RuntimeError"
    raw = (tmp_path / "journal.sqlite3").read_bytes().decode("utf-8", "ignore")
    assert "provider-token-must-not-be-stored" not in raw

    resumed = journal.begin_attempt(
        task_id="task-1", agent_id="jarvis-termux-mini-1",
        objective="Prepare the weekly AI curation",
        attempt_id="00000000-0000-0000-0000-000000000009",
    )
    assert resumed.is_resumed is True
    assert [record.status for record in resumed.prior_steps] == ["interrupted"]


def test_unsuccessful_result_records_only_the_failure_class(tmp_path):
    journal = ObjectiveJournal(tmp_path / "journal.sqlite3")

    handler = PersistentObjectiveHandler(
        lambda message: {"success": False, "error": "provider-token-must-not-be-stored"},
        journal,
    )
    result = handler(_message())

    assert result["success"] is False
    summary = journal.summary()
    assert summary["by_status"] == {"active": 1}
    assert summary["active"][0]["last_error_type"] == "objective_incomplete"
    raw = (tmp_path / "journal.sqlite3").read_bytes().decode("utf-8", "ignore")
    assert "provider-token-must-not-be-stored" not in raw


def test_persisted_progress_survives_a_large_remote_context(tmp_path):
    journal = ObjectiveJournal(tmp_path / "journal.sqlite3")
    first_attempt = "00000000-0000-0000-0000-000000000001"
    journal.begin_attempt(
        task_id="task-1", agent_id="jarvis-termux-mini-1",
        objective="Prepare the weekly AI curation", attempt_id=first_attempt,
    )
    step = journal.start_step(task_id="task-1", attempt_id=first_attempt)
    journal.finish_step(
        task_id="task-1", attempt_id=first_attempt, step_index=step,
        output="outline drafted: three sections",
    )

    seen: list[AgentMessage] = []

    def delegate(message):
        seen.append(message)
        return {"success": True, "output": "curation ready"}

    handler = PersistentObjectiveHandler(delegate, journal)
    handler(_message(attempt_id="00000000-0000-0000-0000-000000000002", context="x" * 40000))

    context = seen[0].payload["context"]
    assert "outline drafted: three sections" in context
    assert len(context) <= 16000


def test_messages_without_an_attempt_pass_through_unchanged(tmp_path):
    journal = ObjectiveJournal(tmp_path / "journal.sqlite3")
    message = AgentMessage.create(
        task_id="task-1", sender_id="leader", recipient_id="agent", kind="request",
        payload={"objective": "Objective"},
    )

    result = PersistentObjectiveHandler(
        lambda request: {"success": True, "output": "ok"}, journal,
    )(message)

    assert result == {"success": True, "output": "ok"}
    assert journal.summary()["total"] == 0


def test_unavailable_journal_does_not_block_inference(tmp_path):
    class BrokenJournal:
        def begin_attempt(self, **kwargs):
            raise OSError("disk full")

    handler = PersistentObjectiveHandler(
        lambda message: {"success": True, "output": "still works"}, BrokenJournal(),
    )

    assert handler(_message()) == {"success": True, "output": "still works"}


def test_journal_is_opt_in_and_uses_the_configured_path(tmp_path, monkeypatch):
    monkeypatch.delenv("JARVIS_OBJECTIVE_JOURNAL_ENABLED", raising=False)
    assert objective_journal_enabled() is False

    def base(message):
        return {"success": True}

    assert wrap_handler_with_objective_journal(base) is base

    monkeypatch.setenv("JARVIS_OBJECTIVE_JOURNAL_ENABLED", "true")
    monkeypatch.setenv("JARVIS_OBJECTIVE_JOURNAL_PATH", str(tmp_path / "journal.sqlite3"))

    wrapped = wrap_handler_with_objective_journal(base)

    assert isinstance(wrapped, PersistentObjectiveHandler)
    assert wrapped.journal.path == tmp_path / "journal.sqlite3"


def test_runtime_wraps_each_worker_handler_when_enabled(tmp_path, monkeypatch):
    from app.multiagent.agent_worker_runtime import start_configured_worker

    class IdleWorker:
        def __init__(self, agent_id):
            self.agent_id = agent_id
            self.handler = lambda message: {"success": True}

        def run_once(self):
            return None

    monkeypatch.setenv("JARVIS_MINI_AGENT_ENABLED", "true")
    monkeypatch.setenv("JARVIS_AGENT_ID", "jarvis-termux-mini-1")
    monkeypatch.setenv("JARVIS_OBJECTIVE_JOURNAL_ENABLED", "true")
    monkeypatch.setenv("JARVIS_OBJECTIVE_JOURNAL_PATH", str(tmp_path / "journal.sqlite3"))
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("JARVIS_TASK_QUEUE_API_URL", raising=False)
    monkeypatch.delenv("JARVIS_TASK_QUEUE_WORKER_TOKEN", raising=False)
    built: list[IdleWorker] = []

    def build_worker(agent_id=None):
        worker = IdleWorker(agent_id)
        built.append(worker)
        return worker

    monkeypatch.setattr(
        "app.multiagent.agent_worker_runtime.PriorityQueueMiniAgent.from_env",
        build_worker,
    )

    runtime = start_configured_worker()
    assert runtime is not None
    group, stop = runtime
    stop.set()
    group.join(timeout=2)

    assert len(built) == 1
    assert isinstance(built[0].handler, PersistentObjectiveHandler)
