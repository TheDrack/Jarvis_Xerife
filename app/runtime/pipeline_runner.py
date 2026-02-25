from app.core.nexuscomponent import NexusComponent

class PipelineRunner(NexusComponent):
    def execute(self, context: dict):
        import os
        import yaml
        import logging
        from typing import Dict, Any

        from app.core.nexus import nexus


        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
        )


        def load_pipeline_config(pipeline_name: str) -> Dict[str, Any]:
            """
            Resolve o caminho do YAML do pipeline a partir do nome lógico.
            """
            config_path = os.path.join("config", "pipelines", f"{pipeline_name}.yml")

            if not os.path.exists(config_path):
                raise FileNotFoundError(f"Pipeline config not found: {config_path}")

            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)


        def build_initial_context(pipeline_name: str) -> Dict[str, Any]:
            """
            Cria o contexto inicial compartilhado entre os componentes.
            """
            return {
                "artifacts": {},
                "metadata": {
                    "pipeline": pipeline_name,
                    "intent": pipeline_name,
                },
                "env": dict(os.environ),
            }


        def run_pipeline(
            pipeline_name: str,
            strict: bool = False,
        ) -> Dict[str, Any]:
            """
            Pipeline Runner (Supervisor):

            - Executa componentes declarados no YAML
            - Tolerante a falhas (modo não-strict)
            - Compartilha contexto entre workers
            """

            logging.info(f"[PIPELINE] Starting pipeline: {pipeline_name}")

            config = load_pipeline_config(pipeline_name)
            context = build_initial_context(pipeline_name)

            components = config.get("components", {})
            if not components:
                logging.warning("[PIPELINE] No components declared")
                return context

            for name, meta in components.items():
                logging.info(f"[PIPELINE] Resolving component: {name}")

                instance = nexus.resolve(
                    target_id=meta["id"],
                    hint_path=meta.get("hint_path"),
                    singleton=meta.get("singleton", True),
                )

                if not instance:
                    msg = f"[PIPELINE] Component '{name}' not found"
                    if strict:
                        raise RuntimeError(msg)
                    logging.warning(msg)
                    continue

                # Configuração opcional
                if hasattr(instance, "configure") and "config" in meta:
                    logging.info(f"[PIPELINE] Configuring '{name}'")
                    instance.configure(meta["config"])

                # Guarda opcional de execução
                if hasattr(instance, "can_execute"):
                    try:
                        if not instance.can_execute(context):
                            logging.info(
                                f"[PIPELINE] Skipping '{name}' (can_execute=False)"
                            )
                            continue
                    except TypeError:
                        # Compatibilidade com can_execute() sem argumentos
                        if not instance.can_execute():
                            logging.info(
                                f"[PIPELINE] Skipping '{name}' (can_execute=False)"
                            )
                            continue

                # Execução protegida
                try:
                    logging.info(f"[PIPELINE] Executing '{name}'")
                    result = instance.execute(context)

                    if result is not None:
                        context["artifacts"][name] = result

                except Exception as e:
                    logging.exception(f"[PIPELINE] Error in '{name}': {e}")
                    if strict:
                        raise

            logging.info(f"[PIPELINE] Finished pipeline: {pipeline_name}")
            return context


        if __name__ == "__main__":
            pipeline_name = os.getenv("PIPELINE")

            if not pipeline_name:
                raise RuntimeError(
                    "Environment variable PIPELINE not set. "
                    "Example: PIPELINE=sync_drive"
                )

            strict_mode = os.getenv("PIPELINE_STRICT", "false").lower() == "true"

            run_pipeline(
                pipeline_name=pipeline_name,
                strict=strict_mode,
            )
