from fastapi import APIRouter, WebSocket
from app.core.nexus import Nexus
from app.ports.voice_port import VoicePort

router = APIRouter()

@router.websocket("/ws/jarvis-voice")
async def voice_stream(websocket: WebSocket):
    await websocket.accept()
    nexus = Nexus()
    voice_service = nexus.resolve(VoicePort)
    orchestrator = nexus.resolve("Orchestrator") # Reutiliza seu core

    try:
        while True:
            # Recebe áudio bruto do celular
            audio_data = await websocket.receive_bytes()
            
            # 1. Transcreve
            text_query = await voice_service.stt(audio_data)
            
            # 2. Processa no Core (Reutilização Total)
            response = await orchestrator.process(text_query)
            
            # 3. Sintetiza Resposta
            audio_response = await voice_service.tts(response.text)
            
            # 4. Envia de volta para o celular tocar
            await websocket.send_bytes(audio_response)
    except Exception as e:
        print(f"Erro na conexão de voz: {e}")
