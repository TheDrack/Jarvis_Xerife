import importlib
# -*- coding: utf-8 -*-
"""Nexus Discovery — Mecanismo de descoberta automática de componentes.
STATUS: Sintaxe validada e lógica de paths reforçada.
"""
import os
import re
import logging
from pathlib import Path
from typing import List, Tuple, Optional, Any

logger = logging.getLogger(__name__)

def search_component_in_files(
    target_id: str,
    search_root: str,
) -> List[Tuple[str, str]]:
    """
    Busca componente por nome em todos os arquivos Python.
    """
    if not search_root or search_root == "/":
        search_root = os.getcwd()

    # Encontra o root do projeto de forma segura
    potential_root = os.path.abspath(search_root)
    
    # Limita a subida de diretórios para evitar loops em sistemas root
    for _ in range(10): 
        if os.path.exists(os.path.join(potential_root, "app")):
            break
        parent = os.path.dirname(potential_root)
        if parent == potential_root:
            break
        potential_root = parent

    effective_search_root = os.path.join(potential_root, "app")
    if not os.path.exists(effective_search_root):
        effective_search_root = potential_root

    matches: List[Tuple[str, str]] = []
    norm_target = target_id.lower().replace("_", "")

    # Walk otimizado
    for root, dirs, files in os.walk(effective_search_root):
        # Modificar dirs in-place para o os.walk ignorar pastas pesadas/irrelevantes
        dirs[:] = [d for d in dirs if d not in ["__pycache__", ".git", ".pytest_cache", ".venv", "node_modules"]]

        for fname in files:
            if fname.endswith(".py") and not fname.startswith("__"):
                file_norm = fname.lower().replace("_", "").replace(".py", "")

                # Heurística de similaridade de nome de arquivo
                if norm_target in file_norm or file_norm in norm_target:
                    file_path = os.path.join(root, fname)
                    try:
                        # Encoding utf-8 explícito para evitar erros em diferentes OS
                        content = Path(file_path).read_text(encoding="utf-8", errors="ignore")

                        # Busca classe que contenha o ID no nome
                        pattern = rf"class\s+(\w*{re.escape(target_id)}\w*)\s*[\(:]"
                        class_matches = re.findall(pattern, content, re.IGNORECASE)
                        
                        if class_matches:
                            for c_name in class_matches:
                                matches.append((file_path, c_name))
                                logger.debug(f"[Discovery] Match encontrado: {fname} -> {c_name}")
                    
                    except Exception as e:
                        logger.error(f"[Discovery] Falha crítica ao ler {fname}: {e}")

    return matches

def find_component_file(target_id: str, hint_path: Optional[str] = None) -> Optional[str]:
    """
    Orquestrador de busca de arquivos por estratégia de prioridade.
    """
    search_root = os.getcwd()

    # 1. Estratégia de Hint (Caminho sugerido)
    if hint_path:
        # Resolve path relativo se necessário
        abs_hint = os.path.abspath(hint_path) if not os.path.isabs(hint_path) else hint_path
        possible_paths = [
            f"{abs_hint}.py",
            os.path.join(abs_hint, "__init__.py"),
        ]
        for path in possible_paths:
            if os.path.exists(path):
                return path

    # 2. Busca por Reflexão/Regex (Deep Scan)
    matches = search_component_in_files(target_id, search_root)
    if matches:
        return matches[0][0]

    # 3. Fallback: Scan Direto Simples
    app_dir = os.path.join(search_root, "app")
    if os.path.exists(app_dir):
        target_clean = target_id.lower().replace("_", "")
        for root, _, files in os.walk(app_dir):
            for fname in files:
                if fname.endswith(".py") and target_clean in fname.lower().replace("_", ""):
                    return os.path.join(root, fname)

    return None



class _NexusDiscoveryMixin:
    """
    Mixin de descoberta para JarvisNexus.

    O Nexus espera que esse mixin exporte `_resolve_internal`, usado por
    `_build_instance` para localizar e preparar o componente solicitado.
    """

    def _resolve_internal(self, target_id: str, hint_path: Optional[str]) -> Any:
        """
        Descobre e retorna o componente correspondente ao target_id.

        Retorna a classe encontrada para que o Nexus possa instanciá-la ou,
        em caso de falha, propaga a exceção para que o Nexus a trate como
        falha de resolução e abra o circuit breaker.
        """
        from pathlib import Path as _Path

        file_path = find_component_file(target_id, hint_path)
        if file_path is None:
            raise RuntimeError(f"Componente nao encontrado: {target_id}")

        module_dir = os.path.dirname(file_path)
        module_file = os.path.basename(file_path)
        module_name, _ = os.path.splitext(module_file)

        # Tenta achar a raiz do app para calcular o package
        relative_root = None
        potential_root = os.path.abspath(module_dir)
        for _ in range(10):
            if os.path.exists(os.path.join(potential_root, "app")):
                relative_root = potential_root
                break
            parent = os.path.dirname(potential_root)
            if parent == potential_root:
                break
            potential_root = parent

        try:
            if not relative_root:
                module = importlib.import_module(module_name)
            else:
                rel = os.path.relpath(module_dir, relative_root).replace(os.sep, ".")
                package = (rel + "." if rel != "." else "") + module_name
                module = importlib.import_module(package)
        except Exception as exc:
            logger.exception("[Discovery] Falha ao importar modulo para %s: %s", target_id, exc)
            raise RuntimeError(f"Falha ao importar modulo para {target_id}: {exc}") from exc

        # Tenta identificar a classe correspondente ao target_id
        candidates = search_component_in_files(target_id, module_dir or ".")
        if candidates:
            _, class_name = candidates[0]
            try:
                cls = getattr(module, class_name)
            except AttributeError as exc:
                logger.exception("[Discovery] Classe %s nao encontrada no modulo %s", class_name, module_name)
                raise RuntimeError(f"Classe nao encontrada no modulo: {class_name}") from exc
            return cls

        # Fallback: retorna o proprio modulo quando a classe nao foi identificada
        return module
