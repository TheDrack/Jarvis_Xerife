# -*- coding: utf-8 -*-
import os
import yaml
import logging
import sys

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
from app.core.nexus import nexus, CloudMock

def run_pipeline(pipeline_name: str, global_strict: bool = False):
    logging.info(f"🚀 INICIANDO RUNNER: {pipeline_name}")

    config_path = os.path.join("config", "pipelines", f"{pipeline_name}.yml")
    if not os.path.exists(config_path):
        logging.error(f"❌ Pipeline {pipeline_name} não encontrado em {config_path}")
        return

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    context = {
        "artifacts": {}, 
        "metadata": {"pipeline": pipeline_name}, 
        "env": dict(os.environ), 
        "result": {}
    }
    components = config.get("components", {})

    for name, meta in components.items():
        t_id = meta.get("id")
        # Define se este passo específico é obrigatório (prioriza o YAML, depois o global)
        component_config = meta.get("config", {})
        is_strict = component_config.get("strict_mode", global_strict)

        logging.info(f"🔍 Resolvendo componente: {name} (ID: {t_id})")
        instance = nexus.resolve(target_id=t_id, hint_path=meta.get("hint_path"))

        if not instance:
            msg = f"❌ Falha crítica: Instância de {t_id} não encontrada."
            if is_strict: raise RuntimeError(msg)
            logging.error(msg)
            continue

        # Detect Circuit Breaker fallback: do not silently treat a CloudMock as success
        if getattr(instance, "__is_cloud_mock__", False):
            msg = (
                f"⚠️ Componente '{t_id}' indisponível (Circuit Breaker ativo). "
                "Execução real foi substituída por CloudMock – verifique o componente."
            )
            logging.error(msg)
            if is_strict:
                raise RuntimeError(f"❌ Falha crítica: '{t_id}' retornou CloudMock em strict mode.")
            context["result"] = {"error": "component_unavailable", "source": t_id}
            continue

        try:
            if hasattr(instance, "configure"):
                instance.configure(component_config)

            logging.info(f"⚙️ Executando: {name}...")
            
            # Execução do componente
            updated_context = instance.execute(context)

            # Validação do retorno para não corromper o pipeline
            if isinstance(updated_context, dict):
                context = updated_context
                logging.info(f"✅ {name} finalizado.")
            else:
                logging.warning(f"⚠️ {name} retornou tipo {type(updated_context)}. Mantendo contexto anterior.")

        except Exception as e:
            logging.error(f"💥 ERRO NA EXECUÇÃO DE {name}: {e}")
            if is_strict:
                logging.error("🛑 Strict Mode Ativo: Interrompendo pipeline.")
                raise e
            
            # Se não for strict, limpa o result para o próximo componente não tentar ler lixo
            context["result"] = {"error": str(e), "source": name}
            logging.warning(f"⚠️ {name} falhou, mas o pipeline continua (Strict: False).")

    logging.info("🏁 PIPELINE FINALIZADO")

if __name__ == "__main__":
    p_name = os.getenv("PIPELINE")
    g_strict = os.getenv("PIPELINE_STRICT", "false").lower() == "true"
    run_pipeline(p_name, g_strict)
