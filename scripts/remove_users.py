import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging

from models.reputation import process_pending_deletions

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        '%(levelname)s - %(message)s'
    )
    handler.setFormatter(formatter)

    logger.addHandler(handler)

if __name__ == "__main__":
    process_pending_deletions(logger)