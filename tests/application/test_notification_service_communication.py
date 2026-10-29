from unittest.mock import patch

from app.application.services.notification_service import NotificationService
from app.application.services.user_communication_service import CommunicationPriority


def test_notification_service_exposes_presence_aware_user_communication():
    service = NotificationService()
    with patch("app.application.services.notification_service.nexus.resolve", return_value=None), patch(
        "app.application.services.notification_service.dispatch_to_mobile"
    ) as dispatch:
        result = service.communicate_user("event-1", "Resumo", CommunicationPriority.NORMAL)
    assert result["status"] == "deferred"
    dispatch.assert_not_called()


def test_notification_service_routes_urgent_message_when_presence_unknown():
    service = NotificationService()
    with patch("app.application.services.notification_service.nexus.resolve", return_value=None), patch(
        "app.application.services.notification_service.dispatch_to_mobile", return_value={"transport": "websocket"}
    ) as dispatch:
        result = service.communicate_user("critical-1", "Alerta crítico", CommunicationPriority.CRITICAL)
    assert result["status"] == "sent"
    assert result["channel"] == "speak"
    dispatch.assert_called_once_with("speak", "Alerta crítico")
