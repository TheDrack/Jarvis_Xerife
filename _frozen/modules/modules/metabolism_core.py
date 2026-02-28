from app.core.nexuscomponent import NexusComponent
# -*- coding: utf-8 -*-
import os
import json
import requests
import re

class MetabolismCore(NexusComponent):
    def execute(self, context: dict):
        raise NotImplementedError("Implementação automática via Cristalizador")

    def __init__(self):
        self.url = "https://api.groq.com/openai/v1/chat/completions"
        self.api_key = os.getenv('GROQ_API_KEY')
        self.model = "llama-3.3-70b-versatile"

    def ask_jarvis(self, system_prompt, user_prompt):
        if not self.api_key:
            raise ValueError("GROQ_API_KEY não encontrada no ambiente.")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1
        }

        try:
            resp = requests.post(self.url, headers=headers, json=payload, timeout=60)
            
            if resp.status_code != 200:
                if "json_validate_failed" in resp.text:
                    payload.pop("response_format", None)
                    resp = requests.post(self.url, headers=headers, json=payload, timeout=60)
                else:
                    raise Exception(f"Erro na API Groq: {resp.text}")

            full_content = resp.json()['choices'][0]['message']['content']
            return self._safe_json_decode(full_content)

        except Exception as e:
            raise Exception(f"Falha na comunicação com o Cérebro: {str(e)}")

    def _safe_json_decode(self, content):
        """Extrai e limpa o JSON de strings sujas ou blocos markdown."""
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # Tenta encontrar o padrão {...}
            match = re.search(r'(\{.*\})', content, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except Exception:
                    # Se falhar o load do match, segue para sanitização manual
                    pass
            
            # Limpeza agressiva de quebras de linha que quebram o JSON
            sanitized = content.replace('\n', '\\n').replace('\r', '\\r')
            try:
                return json.loads(sanitized)
            except Exception as e:
                raise Exception(f"DNA corrompido para decodificação: {str(e)}")
