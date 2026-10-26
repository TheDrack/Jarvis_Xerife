"""Integration tests for declarative plans through TaskRunner and the live Nexus seam."""
from app.application.services import task_runner as task_runner_module
from app.application.services.task_runner import TaskRunner


class FakeAuthorizer:
    _allowlist = {"lookup", "dangerous"}

    def __init__(self, deny=False, approval=False):
        self.deny = deny
        self.approval = approval

    def is_allowed(self, name):
        return name in self._allowlist

    def authorize(self, user, name, payload):
        if self.approval and name == "dangerous" and not payload.get("human_confirmed"):
            raise PermissionError("Capability sensível exige confirmação humana.")
        if self.deny or name not in self._allowlist:
            raise PermissionError("denied")
        return True


class FakeCapability:
    def __init__(self, result=None):
        self.calls = []
        self.result = result if result is not None else {"ok": True}

    def execute(self, context):
        self.calls.append(context)
        return self.result


def plan(tool="lookup", args=None):
    return {
        "version": "1",
        "execution_id": "integration-1",
        "steps": [{"step_id": "s1", "tool": tool, "args": args or {}}],
    }


def build_runner(monkeypatch, *, authorizer=None, capability=None, sink=None):
    authorizer = authorizer or FakeAuthorizer()
    capability = capability or FakeCapability()
    def resolve(name):
        if name == "capability_authorizer":
            return authorizer
        if name == "lookup":
            return capability
        if name == "dangerous":
            return capability
        return None
    monkeypatch.setattr(task_runner_module.nexus, "resolve", resolve)
    return TaskRunner(cache_dir=__import__("pathlib").Path("/tmp/jarvis-plan-integration-tests"),
                      plan_event_sink=sink), capability


def test_task_runner_executes_plan_through_nexus_capability(monkeypatch):
    events = []
    runner, capability = build_runner(monkeypatch, sink=events.append)
    result = runner.execute_plan({"plan": plan(args={"query": "safe"}), "user": "test-user"})
    assert result["success"] is True
    assert result["status"] == "completed"
    assert capability.calls == [{"query": "safe"}]
    assert any(event["event"] == "step_started" for event in events)
    assert all("args" not in event and "result" not in event for event in events)


def test_task_runner_fails_closed_without_durable_journal(monkeypatch):
    runner, capability = build_runner(monkeypatch)
    result = runner.execute_plan({"plan": plan()})
    assert result["status"] == "blocked"
    assert result["error"] == "durable_plan_journal_not_configured"
    assert capability.calls == []


def test_task_runner_applies_authorizer_before_dispatch(monkeypatch):
    runner, capability = build_runner(monkeypatch, authorizer=FakeAuthorizer(deny=True), sink=lambda event: None)
    result = runner.execute_plan({"plan": plan(), "user": "test-user"})
    assert result["status"] == "blocked"
    assert capability.calls == []


def test_sensitive_capability_requires_human_confirmation(monkeypatch):
    events = []
    authorizer = FakeAuthorizer(approval=True)
    runner, capability = build_runner(monkeypatch, authorizer=authorizer, sink=events.append)
    result = runner.execute_plan({"plan": plan("dangerous"), "user": "test-user"})
    assert result["status"] == "approval_required"
    assert capability.calls == []


def test_journal_failure_blocks_before_nexus_dispatch(monkeypatch):
    runner, capability = build_runner(
        monkeypatch, sink=lambda event: (_ for _ in ()).throw(OSError("journal down"))
    )
    result = runner.execute_plan({"plan": plan()})
    assert result["status"] == "blocked"
    assert capability.calls == []
