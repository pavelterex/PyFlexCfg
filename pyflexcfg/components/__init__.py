import os

from .constants import LOG_LEVEL
from .logger import create_logger

log = create_logger(os.getenv(LOG_LEVEL, 'INFO'))
