"""
Logging configuration for Orion Scanner.

Provides a pre-configured logger with console output and optional file handler.
"""

import logging
import sys
from pathlib import Path


def get_logger(name: str, level: int = logging.INFO, log_file: Path | None = None) -> logging.Logger:
    """
    Return a named logger with a consistent format.

    Args:
        name: Logger name, typically ``__name__`` of the calling module.
        level: Logging level (default: INFO).
        log_file: Optional path to a log file. If provided, logs are also
                  written there in addition to stdout.

    Returns:
        Configured :class:`logging.Logger` instance.
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(level)

    formatter = logging.Formatter(
        fmt="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    logger.propagate = False
    return logger
