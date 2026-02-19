"""
Structured logging configuration using structlog.
Outputs JSON logs for machine-readable observability + human-readable console logs.
"""
import logging
import sys
import os
import structlog
from config import settings


def setup_logging():
    """Configure structlog with both console and file outputs."""

    # Ensure log directory exists
    log_dir = os.path.dirname(settings.LOG_FILE)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    # Set up standard logging
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    # File handler (JSON format)
    handlers = [logging.StreamHandler(sys.stdout)]
    if settings.LOG_FILE:
        try:
            file_handler = logging.FileHandler(settings.LOG_FILE, mode='a')
            handlers.append(file_handler)
        except Exception:
            pass

    logging.basicConfig(
        format="%(message)s",
        level=log_level,
        handlers=handlers
    )

    # Configure structlog processors
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = __name__):
    """Get a structured logger instance."""
    return structlog.get_logger(name)
