# -*- coding: utf-8 -*-
"""Bootstrap for Edge deployment - Local execution with hardware"""

import logging
import sys

from app.adapters.infrastructure.setup_wizard import check_env_complete, run_setup_wizard
from app.container import create_edge_container
from app.core.config import settings

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
    Initializes the assistant with hardware-dependent adapters.
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
        # Use the reloaded settings
        current_settings = config.settings
        logger.info("Setup completed successfully, starting assistant...")
    else:
        current_settings = settings
    
    logger.info("Starting Jarvis Assistant (Edge Mode)")
    logger.info(f"Wake word: {current_settings.wake_word}")
    logger.info(f"Language: {current_settings.language}")
    
    # Log user info if available
    if current_settings.assistant_name:
        logger.info(f"Assistant name: {current_settings.assistant_name}")
    if current_settings.user_id:
        logger.info(f"User ID: {current_settings.user_id}")

    # Create container with edge adapters
    container = create_edge_container(
        wake_word=current_settings.wake_word,
        language=current_settings.language,
    )

    # Get the assistant service
    assistant = container.assistant_service

    # Check adapter availability
    if not assistant.voice.is_available():
        logger.warning("Voice recognition not available - running in limited mode")

    if not assistant.action.is_available():
        logger.warning("Action automation not available - running in limited mode")

    # Start the assistant
    try:
        assistant.start()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
        assistant.stop()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
