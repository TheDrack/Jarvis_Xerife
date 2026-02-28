from app.core.nexuscomponent import NexusComponent
# -*- coding: utf-8 -*-
import json
import logging

class StructuredLogger(NexusComponent):
    def execute(self, context: dict):
        raise NotImplementedError("Implementação automática via Cristalizador")

    """Wrapper for structured logging with context"""
    def __init__(self, logger_instance, **context):
        self.logger = logger_instance
        self.context = context

    def _log(self, level, msg, **extra):
        log_data = {**self.context, **extra, "message": msg}
        self.logger.log(level, json.dumps(log_data))

    def info(self, msg, **extra): self._log(logging.INFO, msg, **extra)
    def error(self, msg, **extra): self._log(logging.ERROR, msg, **extra)
    def warning(self, msg, **extra): self._log(logging.WARNING, msg, **extra)
    def debug(self, msg, **extra): self._log(logging.DEBUG, msg, **extra)
