# -*- coding: utf-8 -*-
"""Nexus Discovery — Mecanismo de descoberta automática de componentes.
CORREÇÃO CRÍTICA: Sintaxe corrigida para CI/CD.
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
    
    Returns:
        Lista de tuplas (caminho_arquivo, nome_classe)
    """
    if not search_root or search_root == "/":
        return []
    
    # Encontra o root do projeto
    potential_root = search_root
    while not os.path.exists(os.path.join(potential_root, "app")) and potential_root != "/":
        potential_root = os.path.dirname(potential_root)
    
    search_root = os.path.join(potential_root, "app")
    matches: List[Tuple[str, str]] = []
    
    # Normalização case-insensitive
    norm_target = target_id.lower().replace("_", "")
    
    for root, _, files in os.walk(search_root):
        # Ignora diretórios de cache
        if "__pycache__" in root or ".git" in root or ".pytest_cache" in root:
            continue
        
        for fname in files:
            if fname.endswith(".py") and not fname.startswith("__"):
                # Match no nome do arquivo (case-insensitive)
                file_norm = fname.lower().replace("_", "").replace(".py", "")
                
                # Match 1: Nome do arquivo contém o target
                if norm_target in file_norm or file_norm in norm_target:
                    file_path = os.path.join(root, fname)                    try:
                        content = Path(file_path).read_text(encoding="utf-8")
                        
                        # Match 2 - Busca classe com nome similar
                        class_patterns = [
                            rf"class\s+(\w*{target_id}\w*)\s*\(",
                            rf"class\s+(\w*{target_id.capitalize()}\w*)\s*\(",
                            rf"class\s+(\w*{target_id.upper()}\w*)\s*\(",
                            rf"class\s+({target_id.capitalize()})\s*\(",
                        ]
                        
                        for pattern in class_patterns:
                            class_matches = re.findall(pattern, content, re.IGNORECASE)
                            if class_matches:
                                matches.append((file_path, class_matches[0]))
                                logger.debug(f"[Discovery] Match: {fname} → {class_matches[0]}")
                                break
                    
                    except Exception as e:
                        logger.debug(f"[Discovery] Erro ao ler {fname}: {e}")
    
    return matches


def find_component_file(target_id: str, hint_path: Optional[str] = None) -> Optional[str]:
    """
    Encontra arquivo do componente por ID ou hint_path.
    
    Returns:
        Caminho do arquivo ou None se não encontrado
    """
    # Estratégia 1: hint_path direta
    if hint_path:
        possible_paths = [
            f"{hint_path}.py",
            f"{hint_path}/__init__.py",
        ]
        for path in possible_paths:
            if os.path.exists(path):
                logger.debug(f"[Discovery] Encontrado via hint_path: {path}")
                return path
    
    # Estratégia 2: Busca no filesystem
    search_root = os.getcwd()
    matches = search_component_in_files(target_id, search_root)
    
    if matches:
        logger.debug(f"[Discovery] {len(matches)} matches para '{target_id}'")
        return matches[0][0]
        # Estratégia 3: Busca em app/ diretamente
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