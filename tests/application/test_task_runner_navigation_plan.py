"""Integration tests for declarative plans reusing the existing desktop navigation adapter."""
from app.application.services import task_runner as task_runner_module
from app.application.services.task_runner import TaskRunner


class FakeAuthorizer:
    _allowlist = {"visual_navigation_adapter"}
    _sensitive = set()

    def __init__(self):
        self.calls = []

    def authorize(self, user, tool, payload):
        self.calls.append((user, tool, payload))


class FakeNavigationAdapter:
    def __init__(self):
        self.calls = []

    def execute(self, payload):
        self.calls.append(payload)
        return {"status": "completed", "success": True}


def make_plan(tool, args):
    return {"version": "1", "execution_id": "navigation-plan-test", "steps": [
        {"step_id": "navigate", "tool": tool, "args": args}
    ]}


def test_plan_routes_visual_recipe_to_existing_adapter(monkeypatch, tmp_path):
    authorizer = FakeAuthorizer()
    adapter = FakeNavigationAdapter()

    def resolve(name):
        if name == "capability_authorizer":
            return authorizer
        if name == "visual_navigation_adapter":
            return adapter
        return None

    monkeypatch.setattr(task_runner_module.nexus, "resolve", resolve)
    runner = TaskRunner(cache_dir=tmp_path, plan_event_sink=lambda _event: None)
    recipe = [{"template_id": "settings", "verify_template_id": "settings_open", "action": "click"}]

    result = runner.execute_plan({"user": "test-user", "plan": make_plan("run_visual_recipe", {"steps": recipe})})

    assert result["status"] == "completed"
    assert adapter.calls == [{"action": "run_visual_recipe", "params": {"steps": recipe}}]
    assert authorizer.calls == [("test-user", "visual_navigation_adapter", {
        "action": "run_visual_recipe", "params": {"steps": recipe}
    })]


def test_plan_can_observe_through_existing_navigation_adapter(monkeypatch, tmp_path):
    authorizer = FakeAuthorizer()
    adapter = FakeNavigationAdapter()

    def resolve(name):
        return {"capability_authorizer": authorizer,
                "visual_navigation_adapter": adapter}.get(name)

    monkeypatch.setattr(task_runner_module.nexus, "resolve", resolve)
    runner = TaskRunner(cache_dir=tmp_path, plan_event_sink=lambda _event: None)
    result = runner.execute_plan({"user": "test-user", "plan": make_plan("observe_screen", {})})

    assert result["status"] == "completed"
    assert adapter.calls == [{"action": "observe_screen", "params": {}}]


def test_navigation_alias_is_not_registered_without_allowlisted_adapter(monkeypatch, tmp_path):
    authorizer = FakeAuthorizer()
    authorizer._allowlist = set()
    calls = []

    def resolve(name):
        if name == "capability_authorizer":
            return authorizer
        if name == "visual_navigation_adapter":
            calls.append(name)
            return FakeNavigationAdapter()
        return None

    monkeypatch.setattr(task_runner_module.nexus, "resolve", resolve)
    runner = TaskRunner(cache_dir=tmp_path, plan_event_sink=lambda _event: None)
    result = runner.execute_plan({"user": "test-user", "plan": make_plan("observe_screen", {})})

    assert result["status"] == "blocked"
    assert result["steps"][0]["error"] == "tool_not_allowlisted"
    assert calls == []


def test_visual_recipe_rejects_missing_steps_before_dispatch(monkeypatch, tmp_path):
    authorizer = FakeAuthorizer()
    adapter = FakeNavigationAdapter()

    def resolve(name):
        return {"capability_authorizer": authorizer,
                "visual_navigation_adapter": adapter}.get(name)

    monkeypatch.setattr(task_runner_module.nexus, "resolve", resolve)
    runner = TaskRunner(cache_dir=tmp_path, plan_event_sink=lambda _event: None)
    result = runner.execute_plan({"user": "test-user", "plan": make_plan("run_visual_recipe", {})})

    assert result["status"] == "blocked"
    assert result["steps"][0]["error"] == "policy_denied"
    assert adapter.calls == []
