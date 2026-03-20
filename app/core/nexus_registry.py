# -*- coding: utf-8 -*-
"""_NexusRegistryMixin – local JRVS registry I/O and GitHub Gist sync.
CORREÇÃO: Estrutura de controle, identação e segurança contra recursão.
"""
import os
import logging
import json
from typing import Dict, Any, Optional
from pathlib import Path

try:
    from app.utils.jrvs_codec import JrvsDecodeError, read_file as _jrvs_read
except ImportError:
    class JrvsDecodeError(Exception):
        pass
    def _jrvs_read(path):
        # Fallback simples se o codec não existir
        return {}

logger = logging.getLogger(__name__)


class _NexusRegistryMixin:
    """Provides local-registry and remote Gist persistence for JarvisNexus."""
    
    @property
    def base_dir(self) -> str:
        """Garante que base_dir exista, mesmo que não definido na classe pai."""
        return getattr(self, "_base_dir", os.getcwd())

    def _process_registry_data(self, data: Dict[str, Any]) -> Dict[str, str]:
        """Extrai e normaliza os caminhos dos componentes do dicionário bruto."""
        result: Dict[str, str] = {}
        for component_id, path in data.get("components", {}).items():
            # Trata casos onde o path inclui o nome da Classe (ex: modulo.Classe)
            parts = path.rsplit(".", 1)
            if len(parts) == 2 and parts[1] and parts[1][0].isupper():
                result[component_id] = parts[0]
            else:
                result[component_id] = path
        return result

    def _load_local_registry(self) -> Dict[str, str]:
        """
        Read nexus_registry.json/.jrvs; fallback para JSON se .jrvs falhar.
        """
        registry_json = os.path.join(self.base_dir, "data", "nexus_registry.json")
        registry_jrvs = os.path.join(self.base_dir, "data", "nexus_registry.jrvs")
        
        # Estratégia 1: JSON (CI/CD friendly)
        if os.path.exists(registry_json):
            try:
                content = Path(registry_json).read_text(encoding="utf-8")
                data = json.loads(content)
                result = self._process_registry_data(data)
                logger.info(f"[NEXUS] Registry carregado: {len(result)} componentes (JSON)")
                return result
            except Exception as e:
                logger.debug(f"[NEXUS] JSON falhou: {e}")
        
        # Estratégia 2: JRVS (local)
        if os.path.exists(registry_jrvs):
            try:
                data = _jrvs_read(registry_jrvs)
                if data:
                    result = self._process_registry_data(data)
                    logger.info(f"[NEXUS] Registry carregado: {len(result)} componentes (JRVS)")
                    return result
            except (FileNotFoundError, JrvsDecodeError, OSError) as e:
                logger.debug(f"[NEXUS] JRVS falhou: {e}")
        
        # Estratégia 3: Supabase fallback
        try:
            from app.adapters.infrastructure.jrvs_cloud_storage import JrvsCloudStorage
            cloud = JrvsCloudStorage()
            raw = cloud.download("jrvs-snapshots", "data/nexus_registry.jrvs")
            if raw:
                os.makedirs(os.path.dirname(registry_jrvs), exist_ok=True)
                with open(registry_jrvs, "wb") as fh:
                    fh.write(raw)
                logger.info("[NEXUS] Registry restaurado do Supabase")
                # Tenta ler o arquivo recém-criado uma única vez
                data = _jrvs_read(registry_jrvs)
                if data:
                    return self._process_registry_data(data)
        except Exception as e:
            logger.debug(f"[NEXUS] Supabase fallback falhou: {e}")
        
        # Estratégia 4: Registry inline (hardcoded fallback)
        logger.warning("[NEXUS] Usando registry inline (fallback)")
        return self._get_inline_registry()
    
    def _get_inline_registry(self) -> Dict[str, str]:
        """
        Registry inline para CI/CD quando arquivos não estão disponíveis.
        """
        return {
            "consolidator": "app.adapters.infrastructure.consolidator",
            "consolidated_context_service": "app.application.services.consolidated_context_service",
            "drive_uploader": "app.adapters.infrastructure.drive_uploader",
            "gist_uploader": "app.adapters.infrastructure.gist_uploader",
            "telegram_adapter": "app.adapters.infrastructure.telegram_adapter",
            "working_memory": "app.domain.memory.working_memory",
            "vector_memory_adapter": "app.adapters.infrastructure.vector_memory_adapter",
            "memory_consolidation_service": "app.application.services.memory_consolidation_service",
            "overwatch_daemon": "app.adapters.infrastructure.overwatch_adapter",
            "evolution_orchestrator": "app.application.services.evolution_orchestrator",
            "evolution_gatekeeper": "app.application.services.evolution_gatekeeper",
            "assistant_service": "app.application.services.assistant_service",
        }
