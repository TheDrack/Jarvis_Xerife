import google.generativeai as genai
from app.core.interfaces import NexusComponent

class GeminiService(NexusComponent):
    """
    Setor: Domain/AI
    Responsabilidade: Interface pura com o modelo Gemini.
    """
    def __init__(self):
        # Aqui ele poderia pegar a chave do ambiente via Config
        self.model = genai.GenerativeModel('gemini-pro')

    def execute(self, prompt: str, **kwargs) -> str:
        """
        O Nexus sempre chamará este método. 
        O prompt vem como argumento principal.
        """
        response = self.model.generate_content(prompt)
        return response.text

    def stream_response(self, prompt: str):
        # Funcionalidade extra específica de IA
        return self.model.generate_content(prompt, stream=True)
