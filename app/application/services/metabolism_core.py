# -*- coding: utf-8 -*-
import os
import json
import requests
import re

class MetabolismCore:
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
            
            # Tratamento para erro de validação de JSON da própria Groq
            if resp.status_code != 200:
                if "json_validate_failed" in resp.text:
                    # Tira a exigência de json_object e tenta de novo como texto puro
                    payload.pop("response_format", None)
                    resp = requests.post(self.url, headers=headers, json=payload, timeout=60)
                else:
                    raise Exception(f"Erro na API Groq: {resp.text}")

            full_content = resp.json()['choices'][0]['message']['content']
            
            # --- LIMPADOR DE DNA (REGEX) ---
            # Tenta encontrar o bloco JSON mesmo que a IA tenha enviado texto extra
            return self._safe_json_decode(full_content)

        except Exception as e:
            raise Exception(f"Falha na comunicação com o Cérebro: {str(e)}")

    def _safe_json_decode(self, content):
        """
        Extrai e limpa o JSON de strings sujas ou blocos markdown.
        """
        try:
            # Tentativa 1: Decodificação direta
            return json.loads(content)
        except json.JSONDecodeError:
            # Tent
