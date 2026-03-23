import requests
from app.core.nexus_exceptions import CloudMock

class MacroDroidAdapter:
    def __init__(self, device_id: str, api_key: str):
        self.device_id = device_id
        self.api_key = api_key
        # URL base do Webhook do MacroDroid
        self.base_url = f"https://trigger.macrodroid.com/{device_id}/jarvis-exec"

    async def execute(self, action_name: str, params: dict = None):
        """
        Envia um comando dinâmico para o MacroDroid.
        Ex: action_name="flash", params={"state": "on"}
        """
        payload = {"action": action_name, **(params or {})}
        try:
            # O MacroDroid recebe isso e decide o que fazer via 'If/Else' ou 'Shell'
            response = requests.get(self.base_url, params=payload, timeout=5)
            return response.status_code == 200
        except Exception as e:
            print(f"[JARVIS-Xerife] Erro ao comandar MacroDroid: {e}")
            return False
