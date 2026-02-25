import yaml
import logging
from app.core.nexus import nexus


def run_pipeline(config_path: str, strict: bool = False):
    """
    Pipeline AUXILIAR:
    - Não quebra se um componente não existir
    - Executa apenas se puder
    - Compartilha contexto
    """

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    context = {
        "artifacts": {},
        "metadata": {},
        "env": {},
    }

    for name, meta in config.get("components", {}).items():
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
            instance.configure(meta["config"])

        # Verificação opcional
        if hasattr(instance, "can_execute"):
            if not instance.can_execute():
                logging.info(f"[PIPELINE] Skipping '{name}' (can_execute=False)")
                continue

        # Execução segura
        try:
            logging.info(f"[PIPELINE] Executing '{name}'")
            result = instance.execute(context)

            if result is not None:
                context["artifacts"][name] = result

        except Exception as e:
            logging.error(f"[PIPELINE] Error in '{name}': {e}")
            if strict:
                raise

    return context


if __name__ == "__main__":
    run_pipeline("config/pipeline.yml")