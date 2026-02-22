import torch
import torchaudio
from speechbrain.inference.speaker import SpeakerRecognition
from pyannote.audio import Pipeline
import numpy as np

# --- CONFIGURAÇÕES ---
# Nota: Você precisará de um token do HuggingFace para o Pyannote 3.1
HF_TOKEN = "SEU_TOKEN_AQUI" 

class JarvisVocalEngine:
    def __init__(self):
        print("🤖 [JARVIS] Inicializando motores biométricos...")
        
        # 1. Carrega o modelo de Biometria (SpeechBrain)
        self.encoder = SpeakerRecognition.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb", 
            savedir="pretrained_models/spkrec-ecapa"
        )
        
        # 2. Carrega o Pipeline de Diarização (Pyannote)
        self.pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1", 
            use_auth_token=HF_TOKEN
        )

        # 3. Bancos de Memória
        self.conhecidos = {}  # { "Nome": Embedding }
        self.em_estudo = {}    # { "Temp_ID": [Lista de Embeddings] }
        self.threshold = 0.75  # Sensibilidade para reconhecer a mesma pessoa

    def processar_audio(self, path_audio, user_logado=None):
        """
        Analisa o áudio, separa vozes e decide o que fazer.
        """
        print(f"🔍 Analisando ambiente: {path_audio}")
        
        # Executa Diarização
        diarization = self.pipeline(path_audio)
        waveform, sample_rate = torchaudio.load(path_audio)

        for turn, _, speaker_id in diarization.itertracks(yield_label=True):
            # Extrair trecho do áudio deste locutor específico
            start_sample = int(turn.start * sample_rate)
            end_sample = int(turn.end * sample_rate)
            segmento = waveform[:, start_sample:end_sample]

            # Gerar Assinatura (Embedding)
            embedding = self.encoder.encode_batch(segmento)

            # Lógica de Reconhecimento
            identificado = self._identificar_pessoa(embedding)

            if identificado:
                print(f"✅ Voz reconhecida: {identificado}")
                # Se for o dono, pode atualizar o perfil com a nova amostra (ajuste fino)
            else:
                self._lidar_com_desconhecido(embedding, user_logado)

    def _identificar_pessoa(self, embedding):
        for nome, emb_mestre in self.conhecidos.items():
            # Cálculo de similaridade de cosseno
            similarity = torch.nn.functional.cosine_similarity(embedding, emb_mestre).item()
            if similarity > self.threshold:
                return nome
        return None

    def _lidar_com_desconhecido(self, embedding, user_logado):
        # Se o usuário está logado com senha, o Jarvis assume que a voz principal é dele
        if user_logado and user_logado not in self.conhecidos:
            print(f"📥 Coletando amostra silenciosa para o perfil de {user_logado}...")
            self.conhecidos[user_logado] = embedding
            return

        # Caso contrário, trata como um visitante recorrente
        for temp_id, amostras in self.em_estudo.items():
            similarity = torch.nn.functional.cosine_similarity(embedding, amostras[0]).item()
            if similarity > self.threshold:
                amostras.append(embedding)
                print(f"🕵️ Monitorando visitante recorrente ({temp_id}). Amostras: {len(amostras)}")
                
                if len(amostras) == 5:
                    print(f"💡 [ALERTA JARVIS]: Identifiquei uma pessoa frequente. Sugestão: Perguntar o nome.")
                return

        # Nova voz nunca vista antes
        novo_id = f"Visitante_{len(self.em_estudo) + 1}"
        self.em_estudo[novo_id] = [embedding]
        print(f"👂 Nova assinatura vocal detectada e armazenada como {novo_id}.")

    def salvar_memoria(self):
        # Lógica para salvar os tensores em disco para não perder após reiniciar
        torch.save(self.conhecidos, "memoria_vozes_conhecidas.pt")
        print("💾 Memória vocal salva em disco.")

# --- MODO DE USO NO ORQUESTRADOR ---
# jarvis = JarvisVocalEngine()
# No primeiro login:
# jarvis.processar_audio("comando_01.wav", user_logado="SeuNome")
# Nas próximas vezes ele já saberá quem é sem o 'user_logado'.
