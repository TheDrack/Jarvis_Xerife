import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.application.services.assistant_service import AssistantService


def _service():
    return AssistantService(command_interpreter=Mock(), intent_processor=Mock())


def test_global_help_signal_is_ignored_without_user_scope():
    service = _service()

    service.on_event("task_blocked", {"title": "Shared task"})

    assert service._proactive_signals == {}
    assert service._proactive_active_users == {}


def test_help_signal_is_recorded_only_in_the_named_user_partition():
    service = _service()

    service.on_event(
        "task_blocked",
        {
            "user_id": "user-a",
            "title": "Memory integration",
            "evidence_ref": "task:42",
        },
    )

    assert "user-a" in service._proactive_signals
    assert service._proactive_signals["user-a"][0]["evidence_ref"] == "task:42"
    assert "user-b" not in service._proactive_signals


@pytest.mark.asyncio
async def test_pending_proactive_candidate_uses_presence_aware_owner_channel(monkeypatch):
    service = _service()
    candidate = {
        "key": "candidate-1",
        "kind": "help_opportunity",
        "message": "Posso investigar a tarefa bloqueada?",
    }
    engine = Mock()
    service._proactive_engines["user-a"] = engine
    service._proactive_pending["user-a"] = {"candidate-1": candidate}
    monkeypatch.setenv("JARVIS_MOBILE_USER_ID", "user-a")

    notifier = SimpleNamespace(
        communicate_user=Mock(return_value={"status": "sent"})
    )
    monkeypatch.setattr(
        "app.application.services.assistant_service.nexus.resolve",
        lambda component_id: notifier if component_id == "notification_service" else None,
    )

    delivered = await service.deliver_pending_proactive("user-a")

    assert delivered == 1
    notifier.communicate_user.assert_called_once()
    kwargs = notifier.communicate_user.call_args.kwargs
    assert kwargs["event_key"] == "proactive:candidate-1"
    assert kwargs["message"] == candidate["message"]
    engine.mark_proposed.assert_called_once_with("candidate-1")
    assert "user-a" not in service._proactive_pending


@pytest.mark.asyncio
async def test_proactive_delivery_never_targets_another_users_mobile(monkeypatch):
    service = _service()
    monkeypatch.setenv("JARVIS_MOBILE_USER_ID", "user-a")
    notifier = SimpleNamespace(communicate_user=Mock(return_value={"status": "sent"}))
    monkeypatch.setattr(
        "app.application.services.assistant_service.nexus.resolve",
        lambda component_id: notifier if component_id == "notification_service" else None,
    )

    delivered = await service._send_proactive_candidate(
        "user-b", {"key": "candidate-2", "message": "Private proposal"}
    )

    assert delivered is False
    notifier.communicate_user.assert_not_called()


@pytest.mark.asyncio
async def test_proactive_monitor_lifecycle_is_cancellable(monkeypatch):
    service = _service()
    monkeypatch.setenv("JARVIS_PROACTIVE_ENABLED", "true")

    assert service.start_proactive_monitor() is True
    task = service._proactive_task
    assert task is not None and not task.done()

    service.stop_proactive_monitor()
    await asyncio.sleep(0)

    assert task.cancelled()
