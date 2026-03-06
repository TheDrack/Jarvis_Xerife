import socketio
from app.core.nexus import NexusComponent

class SocketClient(NexusComponent):
    """
    Setor: Infrastructure/Network
    Responsabilidade: Manter a pulsação da conexão Cloud-Edge.
    """
    def __init__(self):
        self.sio = socketio.Client()
        self.is_connected = False

    def execute(self, context: dict) -> dict:
        action = context.get("action")
        params = context.get("params", {})
        if action == "connect":
            success = self.connect_to_server(params.get("url"), params.get("key"))
            return {"success": success}
        if action == "send":
            self.emit_message(params.get("event"), params.get("data"))
            return {"success": True}
        return {"success": False, "error": "action inválida — use 'connect' ou 'send'"}

    def connect_to_server(self, url: str, key: str):
        try:
            self.sio.connect(url, headers={"Authorization": key})
            self.is_connected = True
            return True
        except Exception:
            return False

    def emit_message(self, event: str, data: any):
        if self.is_connected:
            self.sio.emit(event, data)
