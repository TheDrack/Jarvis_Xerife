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

    # Contexto genérico conforme sua implementação original
    context = {"artifacts": {}, "metadata": {"pipeline": pipeline_name}, "env": dict(os.environ)}
    components = config.get("components", {})

    for name, meta in components.items():
        # Usa o ID definido no meta do YAML para resolver no Nexus
        target_id = meta.get("id")
        logging.info(f"🔍 Tentando resolver: {name} (ID: {target_id})")

        instance = nexus.resolve(
            target_id=target_id,
            hint_path=meta.get("hint_path"),
            singleton=meta.get("singleton", True),
        )

        if not instance:
            msg = f"❌ Falha crítica: Componente {name} (ID: {target_id}) não resolvido pelo Nexus!"
            if strict: raise RuntimeError(msg)
            logging.error(msg)
            continue

        logging.info(f"⚙️ Executando: {name}...")
        try:
            # 1. Configuração (Se houver bloco 'config' no YAML para este componente)
            if hasattr(instance, "configure"):
                instance.configure(meta.get("config", {}))

            # 2. Execução (Interface NexusComponent)
            if hasattr(instance, "execute"):
                result = instance.execute(context)
                logging.info(f"✅ {name} finalizado. Resultado: {result}")
                
                if result:
                    context["artifacts"][name] = result
                    # Atualiza o contexto para o próximo componente (opcional, dependendo do uso)
                    context["result"] = result 
            else:
                logging.warning(f"⚠️ {name} instanciado, mas não possui método execute().")

        except Exception as e:
            logging.error(f"💥 ERRO EM {name}: {e}")
            if strict: raise e

    logging.info("🏁 PIPELINE FINALIZADO")

if __name__ == "__main__":
    p_name = os.getenv("PIPELINE")
    if not p_name:
        logging.error("❌ Variável de ambiente PIPELINE não definida.")
        sys.exit(1)
        
    s_mode = os.getenv("PIPELINE_STRICT", "false").lower() == "true"
    run_pipeline(p_name, s_mode)
