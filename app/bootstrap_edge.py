
# -*- coding: utf-8 -*-
"""Bootstrap for Edge deployment - Local execution with hardware"""

import logging
import sys

from app.adapters.infrastructure.setup_wizard import check_env_complete, run_setup_wizard
from app.core.config import settings
from app.core.nexus import nexus

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(settings.logs_dir / "jarvis.log"),
    ],
)

logger = logging.getLogger(__name__)


def main() -> None:
    """
    Main entry point for Edge deployment.
    Resolves services via JarvisNexus with hardware-dependent adapters.
    """
    # Check if setup is required
    if not check_env_complete():
        logger.info("Setup required - .env file is missing or incomplete")
        print("\n" + "="*60)
        print("Bem-vindo ao Jarvis Assistant!")
        print("Parece que esta é sua primeira execução.")
        print("="*60 + "\n")

        if not run_setup_wizard():
            logger.error("Setup wizard failed or was cancelled")
            sys.exit(1)

        # Reload settings after setup by reimporting the module
        import importlib
        from app.core import config
        importlib.reload(config)
        current_settings = config.settings
        logger.info("Setup completed successfully, starting assistant...")
    else:
        current_settings = settings

    logger.info("Starting Jarvis Assistant (Edge Mode)")
    logger.info(f"Wake word: {current_settings.wake_word}")
    logger.info(f"Language: {current_settings.language}")

    if current_settings.assistant_name:
        logger.info(f"Assistant name: {current_settings.assistant_name}")
    if current_settings.user_id:
        logger.info(f"User ID: {current_settings.user_id}")

    # Resolve assistant service via JarvisNexus
    assistant = nexus.resolve("assistant_service")
    if assistant is None:
        logger.error("JarvisNexus could not resolve 'assistant_service' - aborting startup")
        sys.exit(1)

    # Check adapter availability
    try:
        if hasattr(assistant, "voice") and not assistant.voice.is_available():
            logger.warning("Voice recognition not available - running in limited mode")
    except Exception as e:
        logger.warning(f"Could not check voice availability: {e}")

    try:
        if hasattr(assistant, "action") and not assistant.action.is_available():
            logger.warning("Action automation not available - running in limited mode")
    except Exception as e:
        logger.warning(f"Could not check action availability: {e}")

    # Start the assistant
    try:
        assistant.start()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
        try:
            assistant.stop()
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

