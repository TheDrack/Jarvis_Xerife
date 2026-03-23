import os
from app.ports.voice_port import VoicePort
from app.core.nexus_exceptions import CloudMock # Reutilizando sua lógica de Mock

class VoiceAdapter(VoicePort):
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("VOICE_API_KEY")
        self.enabled = True if self.api_key else False

    async def stt(self, audio_bytes: bytes) -> str:
        if not self.enabled:
            return "Modo voz desativado. Configure a API Key."
        
        # Simulação de integração (Seguindo seu padrão de segurança)
        # Aqui você chamaria a API do Whisper
        print("[JARVIS] Processando áudio via STT...")
        return "Texto transcrito pelo Jarvis"

    async def tts(self, text: str) -> bytes:
        print(f"[JARVIS] Sintetizando voz para: {text[:20]}...")
        # Retornaria os bytes do arquivo de áudio (MP3/WAV)
        return b"fake_audio_content"
