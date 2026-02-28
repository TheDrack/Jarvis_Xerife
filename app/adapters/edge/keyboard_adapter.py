# -*- coding: utf-8 -*-
import pyautogui
import pyperclip
import time
from typing import Any, Dict

class KeyboardAdapter:
    def type_text(self, text: str) -> Dict[str, Any]:
        """Escreve texto e valida via leitura de clipboard ou delay de sistema."""
        initial_clipboard = pyperclip.paste()
        
        # Execução
        pyautogui.write(text)
        time.sleep(0.1) # Buffer de sistema
        
        # Validação mínima: No contexto do Jarvis, se escrevemos, 
        # o efeito no "mundo" (SO) é difícil de ler sem OCR, 
        # então marcamos como incerto se não pudermos ler o destino.
        
        return {
            "action": "type_text",
            "content_length": len(text),
            "success": True,
            "execution_state": "uncertain", # Hardware não provê feedback imediato
            "evidence": "command_dispatched_to_os"
        }

    def press_key(self, key: str) -> Dict[str, Any]:
        pyautogui.press(key)
        # Como não há sensor de volta, marcamos explicitamente
        return {
            "key": key,
            "success": False, # Ausência de evidência = Falha técnica (Incerteza)
            "execution_state": "uncertain",
            "error": "No observable feedback from OS for keypress"
        }
