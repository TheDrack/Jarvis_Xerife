# -*- coding: utf-8 -*-
"""PipelineBuilder — Cria pipelines YAML para o Pipeline Runner."""
import logging
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional
from app.core.nexus import nexus
from app.utils.document_store import document_store

logger = logging.getLogger(__name__)

_PIPELINES_DIR = Path("config/pipelines")


class PipelineBuilder:
    """Cria pipelines YAML que o Pipeline Runner pode executar."""
    
    def __init__(self):
        self._adapter_registry = None
    
    def _get_adapter_registry(self):
        if self._adapter_registry is None:
            self._adapter_registry = nexus.resolve("adapter_registry")
        return self._adapter_registry
    
    def create_pipeline(
        self,
        name: str,
        steps: List[Dict[str, Any]],
        description: str = "",
        strict_mode: bool = False,
    ) -> Path:
        """Cria arquivo de pipeline YAML."""
        _PIPELINES_DIR.mkdir(parents=True, exist_ok=True)
        
        pipeline = {
            "description": description or f"Pipeline gerado: {name}",
            "components": {},
        }
        
        for i, step in enumerate(steps):
            adapter_id = step.get("adapter_id")
            config = step.get("config", {})
            
            registry = self._get_adapter_registry()
            adapter_info = registry.execute({
                "action": "get",
                "adapter_id": adapter_id,
            }).get("adapter")
                        if adapter_info:
                step_config = {
                    "id": adapter_id,
                    "config": {**config, "strict_mode": strict_mode}
                }
                if adapter_info.get("hint_path"):
                    step_config["hint_path"] = adapter_info["hint_path"]
                pipeline["components"][f"step_{i}_{adapter_id}"] = step_config
        
        file_path = _PIPELINES_DIR / f"{name}.yml"
        with open(file_path, "w", encoding="utf-8") as f:
            yaml.dump(pipeline, f, allow_unicode=True, default_flow_style=False)
        
        logger.info(f"📝 [PipelineBuilder] Pipeline criado: {file_path}")
        return file_path
    
    def create_pipeline_for_capability(
        self,
        capability: str,
        adapter_id: str,
        config: Dict[str, Any],
    ) -> Path:
        """Cria pipeline para executar uma capability específica."""
        name = f"auto_{adapter_id}_{capability[:20].replace(' ', '_')}"
        return self.create_pipeline(
            name=name,
            steps=[{"adapter_id": adapter_id, "config": config}],
            description=f"Pipeline para: {capability}",
        )
    
    def create_multi_step_pipeline(
        self,
        name: str,
        adapter_sequence: List[Dict[str, Any]],
    ) -> Path:
        """Cria pipeline com múltiplos passos."""
        return self.create_pipeline(
            name=name,
            steps=adapter_sequence,
            description=f"Pipeline multi-step: {name}",
        )
    
    def run_pipeline(self, pipeline_name: str) -> Dict[str, Any]:
        """Executa pipeline via Pipeline Runner."""
        try:
            from app.runtime.pipeline_runner import run_pipeline
            run_pipeline(pipeline_name)
            return {"success": True, "pipeline": pipeline_name}
        except Exception as e:
            logger.error(f"❌ [PipelineBuilder] Erro: {e}")            return {"success": False, "error": str(e)}
    
    def list_existing_pipelines(self) -> List[str]:
        """Lista pipelines existentes."""
        if not _PIPELINES_DIR.exists():
            return []
        return [f.stem for f in _PIPELINES_DIR.glob("*.yml")]