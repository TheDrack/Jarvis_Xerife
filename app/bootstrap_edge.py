# -*- coding: utf-8 -*-
"""Bootstrap for Edge deployment - Local execution with hardware"""

import logging
import sys

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
    logger.info("Starting Jarvis Assistant (Edge Mode)")
    logger.info(f"Wake word: {settings.wake_word}")
    logger.info(f"Language: {settings.language}")

    # Create container with edge adapters
    container = create_edge_container(
        wake_word=settings.wake_word,
        language=settings.language,
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
