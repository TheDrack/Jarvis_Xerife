# -*- coding: utf-8 -*-
"""Nexus Discovery — Mecanismo de descoberta automática de componentes.
CORREÇÃO: Tipagem ajustada, identação corrigida e regex otimizada.
"""
import os
import re
import logging
from pathlib import Path
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)


def search_component_in_files(
    target_id: str,
    search_root: str,
) -> List[Tuple[str, str]]:
    """
    Busca componente por nome em todos os arquivos Python.
    Retorna uma lista de tuplas (caminho_do_arquivo, nome_da_classe).
    """
    if not search_root or search_root == "/":
        return []
    
    # Encontra o root do projeto (evita loop infinito na raiz)
    potential_root = os.path.abspath(search_root)
    while not os.path.exists(os.path.join(potential_root, "app")):
        parent = os.path.dirname(potential_root)
        if parent == potential_root: # Chegou na raiz do SO
            break
        potential_root = parent
    
    # Define o diretório de busca efetivo
    effective_search_root = os.path.join(potential_root, "app")
    if not os.path.exists(effective_search_root):
        effective_search_root = potential_root

    matches: List[Tuple[str, str]] = []
    
    # Normalização para comparação de nomes de arquivos
    norm_target = target_id.lower().replace("_", "")
    
    for root, _, files in os.walk(effective_search_root):
        # Ignora diretórios de cache e controle de versão
        if any(x in root for x in ["__pycache__", ".git", ".pytest_cache", ".venv"]):
            continue
        
        for fname in files:
            if fname.endswith(".py") and not fname.startswith("__"):
                file_norm = fname.lower().replace("_", "").replace(".py", "")
                
                # Match 1: Nome do arquivo contém o target ou vice-versa
                if norm_target in file_norm or file_norm in norm_target:
                    file_path = os.path.join(root, fname)
                    try:
                        content = Path(file_path).read_text(encoding="utf-8")
                        
                        # CORREÇÃO: Regex simplificada com IGNORECASE
                        # Busca por 'class NomeDaClasse(' ou 'class NomeDaClasse:'
                        class_patterns = [
                            rf"class\s+(\w*{re.escape(target_id)}\w*)\s*[\(:]",
                        ]
                        
                        for pattern in class_patterns:
                            class_matches = re.findall(pattern, content, re.IGNORECASE)
                            if class_matches:
                                # class_matches[0] é o nome da classe encontrada
                                matches.append((file_path, class_matches[0]))
                                logger.debug(f"[Discovery] Match: {fname} → {class_matches[0]}")
                                break
                    
                    except Exception as e:
                        logger.debug(f"[Discovery] Erro ao ler {fname}: {e}")
    
    return matches


def find_component_file(target_id: str, hint_path: Optional[str] = None) -> Optional[str]:
    """
    Encontra arquivo do componente por ID ou hint_path.
    Tenta múltiplas estratégias de busca.
    """
    # Estratégia 1: hint_path direta
    if hint_path:
        possible_paths = [
            f"{hint_path}.py",
            os.path.join(hint_path, "__init__.py"),
        ]
        for path in possible_paths:
            if os.path.exists(path):
                logger.debug(f"[Discovery] Encontrado via hint_path: {path}")
                return path
    
    # Estratégia 2: Busca dinâmica no filesystem
    search_root = os.getcwd()
    matches = search_component_in_files(target_id, search_root)
    
    if matches:
        logger.debug(f"[Discovery] {len(matches)} matches para '{target_id}'")
        return matches[0][0]  # Retorna o caminho do primeiro match
    
    # Estratégia 3: Busca direta em app/ como fallback
    app_dir = os.path.join(search_root, "app")
    if os.path.exists(app_dir):
        for root, _, files in os.walk(app_dir):
            if "__pycache__" in root:
                continue
            for fname in files:
                if fname.endswith(".py"):
                    if target_id.lower() in fname.lower():
                        return os.path.join(root, fname)
    
    return None
