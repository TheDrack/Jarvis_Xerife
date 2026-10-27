from types import SimpleNamespace

from app.application.services.orchestrator_service import OrchestratorService


class FakeAssistant:
    def __init__(self, response):
        self.response = response

    def process_command(self, text):
        return self.response


class FakeRunner:
    def __init__(self):
        self.calls = []

    def execute(self, context):
        self.calls.append(context)
        return {"success": True, "status": "completed"}


def make_service(response):
    service = OrchestratorService.__new__(OrchestratorService)
    service.assistant = FakeAssistant(response)
    service.task_runner = FakeRunner()
    service.logger = None
    return service


def test_structured_plan_is_dispatched_without_interpreting_free_text():
    plan = {"version": 1, "execution_id": "exec-1", "steps": []}
    service = make_service(SimpleNamespace(
        success=True, error=None, message="ready",
        data={"intent": "workflow", "result": {"plan": plan}},
    ))

    result = service.coordinate_flow("run the workflow", {"authenticated_user_id": "user-123"})

    assert result["success"] is True
    assert service.task_runner.calls == [{"plan": plan, "user": "user-123"}]


def test_legacy_tasks_path_is_preserved():
    tasks = [{"capability_id": "lookup", "params": {"q": "x"}}]
    service = make_service({
        "success": True,
        "data": {"intent": "search", "result": {"tasks": tasks}},
    })

    result = service.coordinate_flow("search")

    assert result["success"] is True
    assert service.task_runner.calls == [{"tasks": tasks}]


def test_plain_text_response_does_not_execute_anything():
    service = make_service(SimpleNamespace(success=True, error=None, data={"result": "just text"}))

    result = service.coordinate_flow("please do something")

    assert result["success"] is True
    assert service.task_runner.calls == []


def test_untrusted_user_field_does_not_become_authorized_identity():
    plan = {"version": 1, "execution_id": "exec-2", "steps": []}
    service = make_service(SimpleNamespace(success=True, error=None, data={"result": {"plan": plan}}))

    service.coordinate_flow("run", {"user": "attacker-controlled"})

    assert service.task_runner.calls == [{"plan": plan, "user": "anonymous"}]


def test_failed_assistant_response_stops_dispatch():
    service = make_service(SimpleNamespace(success=False, error="no", data={"result": {"plan": {"steps": []}}}))

    result = service.coordinate_flow("run")

    assert result["success"] is False
    assert service.task_runner.calls == []
