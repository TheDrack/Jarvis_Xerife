from app.application.services.user_communication_service import (
    CommunicationPriority,
    UserCommunicationService,
)


def test_nonurgent_message_uses_notification_channel():
    svc = UserCommunicationService()
    decision = svc.decide(event_key="build-1", message="Build concluído", priority=CommunicationPriority.NORMAL, presence="active")
    assert decision.status == "ready"
    assert decision.channel == "notification"


def test_urgent_message_uses_speech_channel():
    svc = UserCommunicationService()
    decision = svc.decide(event_key="security-1", message="Alerta", priority=CommunicationPriority.URGENT, presence="active")
    assert decision.channel == "speak"


def test_nonurgent_message_is_deferred_when_user_sleeping_or_presence_unknown():
    svc = UserCommunicationService()
    for presence in ("sleep", "unknown"):
        decision = svc.decide(event_key="daily-1", message="Resumo", priority=CommunicationPriority.NORMAL, presence=presence)
        assert decision.status == "deferred"


def test_urgent_message_can_interrupt_sleep():
    svc = UserCommunicationService()
    assert svc.decide(event_key="alarm-1", message="Alerta", priority=CommunicationPriority.URGENT, presence="sleep").status == "ready"


def test_duplicate_event_is_not_dispatched_twice():
    svc = UserCommunicationService()
    sent = []
    dispatch = lambda channel, text: sent.append((channel, text)) or {"success": True}
    kwargs = dict(event_key="job-42", message="Concluído", priority=CommunicationPriority.NORMAL, presence="active", dispatch=dispatch)
    assert svc.communicate(**kwargs)["status"] == "sent"
    assert svc.communicate(**kwargs)["status"] == "deduplicated"
    assert len(sent) == 1


def test_nonurgent_rate_limit_does_not_block_urgent_events():
    clock = [100.0]
    svc = UserCommunicationService(max_per_minute=1, clock=lambda: clock[0])
    dispatch = lambda channel, text: {"success": True}
    def send(key, priority):
        return svc.communicate(event_key=key, message="x", priority=priority, presence="active", dispatch=dispatch)
    assert send("info-1", CommunicationPriority.NORMAL)["status"] == "sent"
    assert send("info-2", CommunicationPriority.NORMAL)["status"] == "rate_limited"
    assert send("urgent-1", CommunicationPriority.URGENT)["status"] == "sent"


def test_failed_delivery_is_not_marked_as_sent():
    svc = UserCommunicationService()
    kwargs = dict(event_key="job-5", message="Falhou", priority=CommunicationPriority.NORMAL, presence="active", dispatch=lambda *_: {"success": False})
    assert svc.communicate(**kwargs)["status"] == "failed"
    assert svc.communicate(**kwargs)["status"] == "failed"


def test_rejects_missing_key_and_oversized_message():
    svc = UserCommunicationService()
    assert svc.decide(event_key="", message="x", priority=CommunicationPriority.NORMAL, presence="active").status == "rejected"
    assert svc.decide(event_key="key", message="x" * 1001, priority=CommunicationPriority.NORMAL, presence="active").status == "rejected"
