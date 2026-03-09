# app/adapters/infrastructure/gemini_context_manager.py
import vertexai
from vertexai.generative_models import GenerativeModel, CachedContent
from datetime import datetime, timedelta

class GeminiContextManager(NexusComponent):
    def __init__(self, project_id: str, location: str = "us-central1"):
        super().__init__()
        self.project_id = project_id
        self.location = location
        vertexai.init(project=project_id, location=location)
        self.cache_name = None

    def execute(self, context: dict) -> dict:
        """Cria ou renova o cache de contexto com o arquivo consolidado."""
        consolidator_artifact = context.get("artifacts", {}).get("consolidator", {})
        file_path = consolidator_artifact.get("file_path") if isinstance(consolidator_artifact, dict) else None
        
        if not file_path:
            self.logger.execute({"level": "error", "message": "Arquivo consolidado não encontrado no contexto."})
            return context

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Define TTL para 24 horas ou até próximo commit
            expire_time = datetime.now() + timedelta(hours=24)

            cached_content = CachedContent.create(
                model_name="gemini-1.5-pro-001",
                contents=[{"role": "user", "parts": [{"text": content}]}],
                system_instruction="Você é o núcleo do JARVIS. Use este contexto como verdade absoluta da arquitetura.",
                display_name="jarvis-codebase-snapshot",
                ttl=expire_time
            )
            
            self.cache_name = cached_content.name
            self.logger.execute({"level": "info", "message": f"Cache de contexto criado: {self.cache_name}"})
            
            context["artifacts"]["context_cache"] = {"name": self.cache_name, "expires": expire_time.isoformat()}
            return context

        except Exception as e:
            self.logger.execute({"level": "error", "message": f"Falha ao criar cache: {str(e)}"})
            raise e