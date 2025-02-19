# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Code to generate random data."""

import os
import pathlib
import random
import shutil
import struct
from enum import Enum

import slp_data_packer as data_packer

DEF_SIZE = 1024 * 1024  # 1MB
"""Generate 1MB data by default."""

CHUNK_SIZE = 1024  # 1KB
"""The maximum size that os.urandom can be called at once."""

STD_OFFSET = 0xCAFE0000
"""The default offset that the binary file will start with for first byte of data."""


class SlpDataPattern(Enum):
    """Enum for the data pattern to be used."""

    SLP_DATA_PATTERN_INCR_STD = 1
    SLP_DATA_PATTERN_DECR_STD = 2
    SLP_DATA_PATTERN_INCR_RND = 3
    SLP_DATA_PATTERN_DECR_RND = 4
    SLP_DATA_PATTERN_ALL_RND = 5


def randomize_data(
    out_path: str, pattern: str | int, num_bytes: int, custom_file: pathlib.Path | None
) -> tuple[str, int]:
    """Write random data according to the options to a binary file."""
    filename = out_path + data_packer.SUFFIX_BIN_DATA

    if isinstance(custom_file, pathlib.Path):
        # Just copy the custom pattern file
        shutil.copyfile(custom_file, filename)
        num_bytes = custom_file.stat().st_size
        return filename, num_bytes

    if isinstance(pattern, str):
        pattern = getattr(SlpDataPattern, pattern)

    if num_bytes is None:
        num_bytes = DEF_SIZE

    if pattern == SlpDataPattern.SLP_DATA_PATTERN_ALL_RND:
        with pathlib.Path.open(filename, "wb") as fout:
            for _ in range(num_bytes // CHUNK_SIZE):
                fout.write(os.urandom(CHUNK_SIZE))
            fout.write(os.urandom(num_bytes % CHUNK_SIZE))

        return filename, num_bytes

    # Figure out the increment for each data entry from previous one
    incr = 1
    if pattern in (
        SlpDataPattern.SLP_DATA_PATTERN_DECR_STD,
        SlpDataPattern.SLP_DATA_PATTERN_DECR_RND,
    ):
        incr = -1

    offset = random.getrandbits(32)
    if pattern in (
        SlpDataPattern.SLP_DATA_PATTERN_INCR_STD,
        SlpDataPattern.SLP_DATA_PATTERN_DECR_STD,
    ):
        offset = STD_OFFSET

    with pathlib.Path(filename).open(mode="wb") as fout:
        for x in range(num_bytes // 4):
            fout.write(struct.pack("<I", (offset + incr * x) & 0xFFFF_FFFF))

    return filename, num_bytes
