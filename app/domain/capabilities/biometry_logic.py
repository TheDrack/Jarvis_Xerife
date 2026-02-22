import torch

class BiometryCapability:
    """Validação, Identificação e Gestão de Memória Vocal."""
    def __init__(self, storage_path="memoria_vozes.pt"):
        self.storage_path = storage_path
        self.conhecidos = self._load_memory() # {nome: embedding}
        self.em_estudo = {} # {temp_id: [embeddings]}
        self.threshold = 0.75

    def identify_speaker(self, current_embedding):
        for nome, master_emb in self.conhecidos.items():
            sim = torch.nn.functional.cosine_similarity(current_embedding, master_emb).item()
            if sim > self.threshold:
                return nome, sim
        return None, 0.0

    def learn_silently(self, embedding, user_logado=None):
        if user_logado:
            # Vincula a voz ao login ativo se for a primeira vez
            self.conhecidos[user_logado] = embedding
            return f"Perfil criado para {user_logado}"
        
        # Lógica de visitantes recorrentes (Curiosidade)
        # ... (implementação de agrupamento conforme discutimos antes)
        return "Amostra processada"

    def _load_memory(self):
        try: return torch.load(self.storage_path)
        except: return {}
