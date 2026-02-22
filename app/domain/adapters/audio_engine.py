import torchaudio
from speechbrain.inference.speaker import SpeakerRecognition
from pyannote.audio import Pipeline

class AudioAdapter:
    """Ferramentas de IO e Processamento de Áudio. Sem lógica de negócio."""
    def __init__(self, hf_token):
        self.biometry_model = SpeakerRecognition.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir="pretrained_models/spkrec-ecapa"
        )
        self.diarization_pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=hf_token
        )

    def load_audio(self, path):
        return torchaudio.load(path)

    def get_embedding(self, waveform):
        # Transforma áudio bruto em vetor numérico
        return self.biometry_model.encode_batch(waveform)

    def get_diarization(self, path):
        # Identifica os turnos de fala
        return self.diarization_pipeline(path)
