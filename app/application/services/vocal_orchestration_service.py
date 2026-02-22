from app.application.containers.hub import hub
import torchaudio
import logging

class VocalOrchestrationService:
    """
    Orquestrador que conecta a captura de áudio (Adapters) à 
    inteligência de reconhecimento (Capabilities).
    """

    def __init__(self):
        self.logger = logging.getLogger("JARVIS_ORCHESTRATOR")

    def execute(self, audio_path: str, session_user: str = None):
        """
        Executa o fluxo completo de identificação e diarização.
        """
        # 1. Resolver dependências via Hub
        # Buscamos os executores nos containers específicos
        diarizer = hub.resolve("diarizer", "adapters")
        encoder = hub.resolve("audio_processor", "adapters")
        identifier = hub.resolve("identify_speaker", "capabilities")
        learner = hub.resolve("learn_voice", "capabilities")

        if not all([diarizer, encoder, identifier, learner]):
            self.logger.error("Falha ao resolver dependências no Hub.")
            return {"status": "error", "message": "Componentes incompletos"}

        try:
            # 2. Processamento de Diarização (Quem falou quando)
            # O diarizer retorna os segmentos temporais
            diarization_segments = diarizer(audio_path)
            waveform, sr = torchaudio.load(audio_path)

            final_report = []

            # 3. Loop de Processamento por Segmento
            for turn, _, _ in diarization_segments.itertracks(yield_label=True):
                # Extração do trecho de áudio bruto
                start_sample = int(turn.start * sr)
                end_sample = int(turn.end * sr)
                segment_audio = waveform[:, start_sample:end_sample]

                # Gerar Assinatura Digital (Embedding)
                embedding = encoder(segment_audio)

                # Identificar via Capability
                name, confidence = identifier(embedding)

                # 4. Lógica de Aprendizado Silencioso
                if not name:
                    # Se não reconheceu, tenta aprender ou monitorar
                    status_aprendizado = learner(embedding, session_user)
                    name = "Desconhecido"
                    self.logger.info(f"Nova voz detectada [{turn.start:.2f}s]: {status_aprendizado}")
                else:
                    self.logger.info(f"Voz reconhecida: {name} ({confidence:.2%})")

                final_report.append({
                    "speaker": name,
                    "confidence": confidence,
                    "start": turn.start,
                    "end": turn.end
                })

            return {
                "status": "success",
                "segments": final_report,
                "detected_count": len(set(seg["speaker"] for seg in final_report))
            }

        except Exception as e:
            self.logger.error(f"Erro na orquestração vocal: {e}")
            return {"status": "error", "error_details": str(e)}

# Instância para ser usada pelo Core
orchestrator = VocalOrchestrationService()
