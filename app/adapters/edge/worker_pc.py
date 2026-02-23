#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Jarvis Voice Assistant - Worker for Distributed Mode

This worker runs on the PC and polls the database (Supabase/PostgreSQL)
for pending commands. When found, it executes them using PyAutoGUI
and updates the status in the database.
"""

import logging
import os
import sys
import time

from app.adapters.infrastructure.sqlite_history_adapter import SQLiteHistoryAdapter
from app.application.services import AssistantService
from app.container import create_edge_container
from app.core.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(settings.logs_dir / "jarvis_worker.log"),
    ],
)

logger = logging.getLogger(__name__)


def main() -> None:
    """
    Main entry point for the worker.
    Polls the database for pending commands and executes them.
    """
    logger.info("Starting Jarvis Worker for Distributed Mode")
    logger.info(f"Database URL: {settings.database_url}")
    logger.info(f"Wake word: {settings.wake_word}")
    logger.info(f"Language: {settings.language}")

    # Create container with edge adapters (includes PyAutoGUI support)
    use_llm = os.getenv("USE_LLM", "false").lower() in ("true", "1", "yes")
    container = create_edge_container(
        wake_word=settings.wake_word,
        language=settings.language,
        use_llm=use_llm,
    )

    # Get the assistant service
    assistant = container.assistant_service
    
    # Initialize database adapter
    db_adapter = SQLiteHistoryAdapter(database_url=settings.database_url)
    
    logger.info("Worker initialized successfully")
    logger.info("Polling for pending commands...")

    # Main worker loop
    poll_interval = float(os.getenv("WORKER_POLL_INTERVAL", "2"))
    logger.info(f"Using poll interval: {poll_interval} seconds")
    
    try:
        while True:
            try:
                # Get the next pending command
                pending_command = db_adapter.get_next_pending_command()
                
                if pending_command:
                    logger.info(f"Found pending command {pending_command['id']}: {pending_command['user_input']}")
                    
                    try:
                        # Execute the command
                        response = assistant.process_command(pending_command['user_input'])
                        
                        # Update status based on execution result
                        if response.success:
                            db_adapter.update_command_status(
                                command_id=pending_command['id'],
                                status='completed',
                                success=True,
                                response_text=response.message,
                            )
                            logger.info(f"Command {pending_command['id']} completed successfully")
                        else:
                            db_adapter.update_command_status(
                                command_id=pending_command['id'],
                                status='failed',
                                success=False,
                                response_text=response.message or response.error or "Unknown error",
                            )
                            logger.warning(f"Command {pending_command['id']} failed: {response.message}")
                    
                    except Exception as e:
                        # Handle execution errors
                        error_msg = f"Error executing command: {str(e)}"
                        logger.error(error_msg, exc_info=True)
                        db_adapter.update_command_status(
                            command_id=pending_command['id'],
                            status='failed',
                            success=False,
                            response_text=error_msg,
                        )
                else:
                    # No pending commands, log less frequently
                    pass
                
                # Sleep to avoid overloading the database
                time.sleep(poll_interval)
                
            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt - shutting down worker")
                break
            except Exception as e:
                logger.error(f"Error in worker loop: {e}", exc_info=True)
                # Continue running even if there's an error
                time.sleep(2)
    
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    finally:
        logger.info("Worker shutdown complete")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
