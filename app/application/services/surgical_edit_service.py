# -*- coding: utf-8 -*-
import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class SurgicalEditService:
    """
    Serviço especializado em realizar edições precisas em arquivos de código.
    Evita a reescrita total, focando apenas nos blocos alterados.
    """

    def __init__(self, root_path: str):
        self.root_path = root_path

    def apply_surgical_edit(self, file_path: str, search_block: str, replace_block: str) -> Dict[str, Any]:
        """
        Localiza um bloco específico de código e o substitui por um novo.
        """
        full_path = os.path.join(self.root_path, file_path)
        
        if not os.path.exists(full_path):
            return {"success": False, "error": f"Arquivo não encontrado: {file_path}"}

        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Normalização simples para aumentar taxa de acerto no match
            norm_search = search_block.strip()
            if norm_search not in content:
                # Tentativa de match ignorando espaços em branco nas extremidades de cada linha
                return self._attempt_fuzzy_edit(content, full_path, search_block, replace_block)

            # Verifica ambiguidade
            if content.count(norm_search) > 1:
                return {
                    "success": False, 
                    "error": "Bloco de busca ambíguo. Múltiplas ocorrências encontradas."
                }

            # Realiza a substituição
            new_content = content.replace(search_block, replace_block)
            
            with open(full_path, 'w', encoding='utf-8') as f:
                f.read() # Garantia de ponteiro
                f.seek(0)
                f.write(new_content)
                f.truncate()

            logger.info(f"[SurgicalEdit] Edição aplicada com sucesso em {file_path}")
            return {"success": True, "file": file_path}

        except Exception as e:
            logger.error(f"[SurgicalEdit] Erro ao editar {file_path}: {e}")
            return {"success": False, "error": str(e)}

    def _attempt_fuzzy_edit(self, content: str, full_path: str, search: str, replace: str) -> Dict[str, Any]:
        """
        Tenta um match mais flexível se o exato falhar (comum com LLMs).
        """
        # Remove identação excessiva para comparar a estrutura
        lines_content = content.splitlines()
        search_lines = search.strip().splitlines()
        
        # Lógica de busca por linhas contíguas (simplificada para estabilidade)
        for i in range(len(lines_content) - len(search_lines) + 1):
            match = True
            for j in range(len(search_lines)):
                if search_lines[j].strip() != lines_content[i+j].strip():
                    match = False
                    break
            
            if match:
                # Encontrou o bloco mesmo com indentação diferente
                new_lines = lines_content[:i] + [replace] + lines_content[i+len(search_lines):]
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write("\n".join(new_lines))
                return {"success": True, "file": os.path.basename(full_path), "mode": "fuzzy"}

        return {
            "success": False, 
            "error": "Não foi possível localizar o bloco original no código. Verifique a sintaxe."
        }
