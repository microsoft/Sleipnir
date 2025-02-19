# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Code to compose one or more BfType objects."""

import collections
import logging
from collections.abc import Generator

import slp_dwarf_parser as dp


def get_frame_obj() -> dp.BfUnion:
    """Generate a frame object in python format."""
    frame_t = dp.get_type_obj(dp.types, "Frame")
    frame_t._int_field_info.model = None  # noqa: SLF001 Force vsc to regenerate
    return frame_t


def gen_frames(num_frames: int) -> Generator[dp.BfStruct]:
    """Generate num_frames number of frames."""
    for _ in range(num_frames):
        yield get_frame_obj()


def fqn2field(field: dp.BfType, fqn: str) -> dp.BfType:
    """Convert a fully qualified name to a BfType object."""
    logging.debug("Converting %s to a BfType object", fqn)

    # Ignore the first one as it is the object itself
    for attr_name in fqn.split(".")[1:]:
        field = object.__getattribute__(field, attr_name)
    return field


def change_rand_field(field: dp.BfUnion, rand_member_name: str) -> None:
    """Change the randomized member within a union to the given member."""
    if not isinstance(field, dp.BfUnion):
        msg = f"field must be a BfUnion type, is: {type(field)}"
        raise TypeError(msg)

    members = collections.OrderedDict()
    for attr_name in dir(field):
        if isinstance(member := object.__getattribute__(field, attr_name), dp.BfType):
            members[attr_name] = member

    rand_member = members.get(rand_member_name)
    logging.debug("Setting member %s for randomization", rand_member_name)

    for member_name, member in members.items():
        if member is not rand_member:
            # Since object is already created, need to access private member directly
            member._int_field_info.set_is_rand(False) # noqa: SLF001
            logging.debug(
                "Only one union member (%s) enabled for randomization, so disabling on %s",
                rand_member_name,
                member_name,
            )
        else:
            # Since object is already created, need to access private member directly
            member._int_field_info.set_is_rand(True) # noqa: SLF001
            logging.debug("Enabled randomization on %s", member_name)
