import logging

from config import LOG_LEVEL


def setup_logger(name):
    """
    Create a logger instance with simplified formatting

    Args:
        name: The name of the logger (typically __name__)

    Returns:
        logging.Logger: Configured logger instance
    """
    logger = logging.getLogger(name)

    # Convert string level to numeric level
    numeric_level = logging.getLevelName(LOG_LEVEL.upper())
    logger.setLevel(numeric_level)

    # Only add handler if the logger doesn't already have handlers
    if not logger.handlers:
        handler = logging.StreamHandler()

        # Choose formatter based on log level - show name except for INFO
        if LOG_LEVEL.upper() != "INFO":
            formatter = logging.Formatter("%(levelname)s (%(name)s): %(message)s")
        else:
            formatter = logging.Formatter("%(levelname)s: %(message)s")

        handler.setFormatter(formatter)
        logger.addHandler(handler)

        # Prevent log propagation to avoid duplicate logs
        logger.propagate = False

    return logger
