import google.generativeai as genai
import os
from app.core.interfaces import NexusComponent

class GeminiService(NexusComponent):
    """
    Setor: Domain/AI
    Responsabilidade: Interface técnica com o modelo Gemini.
    """
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-1.5-pro')

    def execute(self, prompt: str, **kwargs) -> str:
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"Erro na geração de IA: {str(e)}"
