class VocalOrchestrator:
    """O Loop de Orquestração que conecta o Áudio ao Core do JARVIS."""
    def __init__(self, adapter, capability):
        self.adapter = adapter
        self.capability = capability

    def process_incoming_command(self, audio_path, session_user=None):
        # 1. Separa as vozes (Diarização)
        diarization = self.adapter.get_diarization(audio_path)
        waveform, sr = self.adapter.load_audio(audio_path)
        
        results = []
        for turn, _, _ in diarization.itertracks(yield_label=True):
            # 2. Extrai segmento e embedding via Adapter
            segment = waveform[:, int(turn.start*sr):int(turn.end*sr)]
            emb = self.adapter.get_embedding(segment)
            
            # 3. Identifica via Capability
            name, score = self.capability.identify_speaker(emb)
            
            if not name:
                # 4. Aprende em segredo se não reconhecer
                self.capability.learn_silently(emb, session_user)
                name = "Desconhecido"
            
            results.append({"speaker": name, "confidence": score, "start": turn.start})
        
        return results
