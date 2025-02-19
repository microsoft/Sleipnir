# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Code to randomize frames."""

import logging
from collections.abc import Generator
from collections.abc import Iterator

import slp_composer as composer
import slp_dwarf_parser as dp
import slp_frame_constraint as frame_cnstr


def randomize_frames(
    frames: Generator,
    rnd_cfg: dict,
) -> Iterator[dp.BfStruct]:
    """Randomize the frames."""
    rand_desc = composer.get_frame_obj()
    rand_desc.pre_rand()
    frame_cnstr.add_cnstr(rand_desc, rnd_cfg)

    for cmd_idx, frame in enumerate(frames):
        with rand_desc.randomize_with() as it:
            # Add the per cmd constraints here for this index
            if hasattr(it, frame_cnstr.IDX_CONSTR_NAME.format(cmd_idx)):
                getattr(it, frame_cnstr.IDX_CONSTR_NAME.format(cmd_idx))()

        rand_desc.post_rand()

        frame.set_val(rand_desc.get_val())
        frame.id = cmd_idx & 0xFFFF_FFFF

        log_shape_access(frame)

        yield frame


def log_shape_access(desc: dp.BfUnion) -> None:
    """Utility function for logging a frame's attributes.

    Args:
        desc (Bf.Union): Frame object to log.
    """
    msg = f"Frame Id: {desc.fields.id}: (FrameType){desc.fields.type}, Dim: {desc.fields.width}x{desc.fields.height}x{desc.fields.depth}, Count: {desc.fields.count}"  # noqa: E501 Cannot compress further
    logging.debug(msg)
