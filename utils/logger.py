"""
utils/logger.py

Provides get_logger() - one consistently configured logger (console +
rotating file) for every module in the project.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config import config


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(config.app.log_level)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    log_file: Path = config.app.logs_dir / "app.log"
    file_handler = RotatingFileHandler(
        filename=log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    logger.propagate = False
    return logger
