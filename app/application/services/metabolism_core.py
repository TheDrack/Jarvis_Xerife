# -*- coding: utf-8 -*-
import os, json, requests

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
        
        resp = requests.post(self.url, headers=headers, json=payload, timeout=60)
        if resp.status_code != 200:
            raise Exception(f"Erro na API Groq: {resp.text}")
            
        return json.loads(resp.json()['choices'][0]['message']['content'])
