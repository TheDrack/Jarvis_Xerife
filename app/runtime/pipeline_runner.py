# -*- coding: utf-8 -*-
import os
import yaml
import logging
import sys

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
from app.core.nexus import nexus

def run_pipeline(pipeline_name: str, strict: bool = False):
    logging.info(f"🚀 INICIANDO RUNNER: {pipeline_name}")
    
    config_path = os.path.join("config", "pipelines", f"{pipeline_name}.yml")
    if not os.path.exists(config_path): return

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    context = {"artifacts": {}, "metadata": {"pipeline": pipeline_name}, "env": dict(os.environ)}
    components = config.get("components", {})

    for name, meta in components.items():
        t_id = meta.get("id")
        logging.info(f"🔍 Resolvendo: {name} (ID: {t_id})")

        instance = nexus.resolve(target_id=t_id, hint_path=meta.get("hint_path"))

        if not instance:
            if strict: raise RuntimeError(f"Falha em {t_id}")
            continue

        try:
            if hasattr(instance, "configure") and "config" in meta:
                instance.configure(meta["config"])

            logging.info(f"⚙️ Executando: {name}...")
            result = instance.execute(context)
            
            if result:
                context["result"] = result
                context["artifacts"][name] = result
                logging.info(f"✅ {name} OK.")
        except Exception as e:
            logging.error(f"💥 ERRO EM {name}: {e}")
            if strict: raise e

    logging.info("🏁 FINALIZADO")

if __name__ == "__main__":
    run_pipeline(os.getenv("PIPELINE"), os.getenv("PIPELINE_STRICT", "false").lower() == "true")
