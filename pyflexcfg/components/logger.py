import logging
import sys


def create_logger(log_level: str) -> logging.Logger:
    logger = logging.getLogger('pyflexcfg')
    logger.setLevel(log_level)
    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s')
    console = logging.StreamHandler(stream=sys.stdout)
    console.setFormatter(formatter)
    logger.addHandler(console)
    return logger
