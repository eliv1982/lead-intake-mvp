import logging
import os
from pathlib import Path


LOG_PATH = Path("logs/events.log")


def get_event_logger() -> logging.Logger:
    """Configure and return logger for app events."""
    os.makedirs(LOG_PATH.parent, exist_ok=True)

    logger = logging.getLogger("lead_intake_events")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
