import logging
import sys
from typing import Final

LOG_FORMAT: Final = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def setup_logging() -> None:
    """
    Configure application-wide logging.

    Logs are written to the console with timestamps,
    log levels, logger names, and messages.
    """

    logging.basicConfig(
        level=logging.INFO,
        format=LOG_FORMAT,
        stream=sys.stdout,
        force=True,
    )


def get_logger(name: str) -> logging.Logger:
    """
    Return a reusable logger for the given module.
    """
    return logging.getLogger(name)
