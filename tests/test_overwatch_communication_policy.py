from unittest.mock import MagicMock, patch

from app.adapters.infrastructure.overwatch_adapter import OverwatchDaemon
from app.application.services.user_communication_service import CommunicationPriority


def test_overwatch_uses_intelligent_mobile_policy_when_target_is_configured():
    notifier = MagicMock()
    notifier.communicate_user.return_value = {"status": "sent"}
    with patch.dict("os.environ", {"JARVIS_MOBILE_USER_ID": "u1", "JARVIS_MOBILE_DEVICE_ID": "d1"}), patch(
        "app.adapters.infrastructure.overwatch_adapter.nexus.resolve", return_value=notifier
    ), patch.object(OverwatchDaemon, "_get_pending_calendar_tasks", return_value=[]):
        daemon = OverwatchDaemon()
        daemon._notify("Backup finalizado")
    notifier.communicate_user.assert_called_once()
    assert notifier.communicate_user.call_args.args[1] == "Backup finalizado"


def test_overwatch_respects_policy_deferral_without_voice_fallback():
    notifier = MagicMock()
    notifier.communicate_user.return_value = {"status": "deferred"}
    telegram = MagicMock()
    voice = MagicMock()
    def resolve(name):
        return {"notification_service": notifier, "telegram_adapter": telegram, "voice_provider": voice}.get(name)
    with patch.dict("os.environ", {"JARVIS_MOBILE_USER_ID": "u1", "JARVIS_MOBILE_DEVICE_ID": "d1"}), patch(
        "app.adapters.infrastructure.overwatch_adapter.nexus.resolve", side_effect=resolve
    ):
        OverwatchDaemon()._notify("Resumo não urgente")
    telegram.send_message.assert_not_called()
    voice.speak.assert_not_called()


def test_overwatch_classifies_accented_unauthorized_message_as_critical():
    notifier = MagicMock()
    notifier.communicate_user.return_value = {"status": "sent"}
    with patch.dict("os.environ", {"JARVIS_MOBILE_USER_ID": "u1", "JARVIS_MOBILE_DEVICE_ID": "d1"}), patch(
        "app.adapters.infrastructure.overwatch_adapter.nexus.resolve", return_value=notifier
    ):
        OverwatchDaemon()._notify("Acesso não autorizado detectado")

    assert notifier.communicate_user.call_args.args[2] == CommunicationPriority.CRITICAL
