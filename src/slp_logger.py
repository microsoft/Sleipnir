# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Contains logging setup functions called from sleipnir.py."""

import logging

SLP_LOG_NAME = "sleipnir.log"
"""The name of Sleipnir log file."""


def setup(level: str = logging.DEBUG) -> None:
    """Setup logging module according to Sleipnir's needs."""
    # Assign null list for root handlers to avoid log msgs going to std console
    logging.root.handlers = []
    logging.basicConfig(
        filename=SLP_LOG_NAME,
        format="%(asctime)s: %(levelname)s - {%(module)s:%(funcName)s:%(lineno)d} - %(message)s",
        level=level,
    )
    logging.info("Logger setup with level %s", level)


setup()
