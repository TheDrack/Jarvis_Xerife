# -*- coding: utf-8 -*-
import os
import yaml
import logging
import sys
from typing import Dict, Any

# Forçar log no console
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

from app.core.nexus import nexus

def run_pipeline(pipeline_name: str, strict: bool = False):
    logging.info(f"🚀 INICIANDO RUNNER: {pipeline_name} (Strict: {strict})")
    
    config_path = os.path.join("config", "pipelines", f"{pipeline_name}.yml")
    if not os.path.exists(config_path):
        logging.error(f"❌ YAML não encontrado: {config_path}")
        return

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    context = {"artifacts": {}, "metadata": {"pipeline": pipeline_name}, "env": dict(os.environ)}
    components = config.get("components", {})

    for name, meta in components.items():
        logging.info(f"🔍 Tentando resolver: {name} (ID: {meta['id']})")
        
        instance = nexus.resolve(
            target_id=meta["id"],
            hint_path=meta.get("hint_path"),
            singleton=meta.get("singleton", True),
        )

        if not instance:
            msg = f"❌ Falha crítica: Componente {name} não resolvido pelo Nexus!"
            if strict: raise RuntimeError(msg)
            continue

        logging.info(f"⚙️ Executando: {name}...")
        try:
            # Passando config do YAML para o componente
            if hasattr(instance, "configure") and "config" in meta:
                instance.configure(meta["config"])

            result = instance.execute(context)
            logging.info(f"✅ {name} finalizado. Resultado: {result}")
            
            if result:
                context["artifacts"][name] = result
        except Exception as e:
            logging.error(f"💥 ERRO EM {name}: {e}")
            if strict: raise e

    logging.info("🏁 PIPELINE FINALIZADO")

if __name__ == "__main__":
    p_name = os.getenv("PIPELINE")
    s_mode = os.getenv("PIPELINE_STRICT", "false").lower() == "true"
    run_pipeline(p_name, s_mode)
