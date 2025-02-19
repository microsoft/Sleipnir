# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Code to pack required collaterals in YAML and binary formats."""

import pathlib
import struct

from ruamel.yaml import YAML

import slp_dwarf_parser as dp

# ------------------------------------------------------------------------------
# Prefixes
# ------------------------------------------------------------------------------
PREFIX_DEF = "slp"
"""Default prefix for the binary files"""

PREFIX_DEF_TEST = ".test_{0:02d}"
"""The default prefix for files to be differentiated per test."""

# ------------------------------------------------------------------------------
# Suffixes
# ------------------------------------------------------------------------------
SUFFIX_BIN_FRAME = ".frames.bin"
"""Suffix for frames bin file"""

SUFFIX_YML_FRAME = ".frames.yml"
"""Suffix for frames YAML file"""

SUFFIX_BIN_META = ".meta.bin"
"""Suffix for meta cmd bin file"""

SUFFIX_YML_META = ".meta.yml"
"""Suffix for meta cmd YAML file"""

SUFFIX_BIN_DATA = ".data.bin"
"""Suffix for data bin file"""

# ------------------------------------------------------------------------------
# Variable names in Sleipnir library
# ------------------------------------------------------------------------------
VARNAME_NUM_CMDS_FRAME = "num_frames"
VARNAME_SIZE_DATA = "size_data"

# ------------------------------------------------------------------------------
# File names in Sleipnir library
# ------------------------------------------------------------------------------
VARNAME_FILE_FRAME = "file_frames"
VARNAME_FILE_DATA = "file_data"
"""These are the variables that sleipnir handler on C side looks for"""
# ------------------------------------------------------------------------------

yaml = YAML()
yaml.register_class(dp.BfUnion)
yaml.register_class(dp.BfStruct)
yaml.register_class(dp.BfArray)
yaml.register_class(dp.BfDtype)
"""Allow YAML to dump instances of these classes."""

yaml.default_flow_style = False
yaml.indent(mapping=2, sequence=4, offset=2)
"""Add an extra indentation when emitting list items."""

yaml.representer.ignore_aliases = lambda *args: True  # noqa: ARG005 # Need to match function signature.
"""Disable aliases when dumping YAML"""


def gen_bin_yaml_output_frame(out_path: str, frames: list[dp.BfStruct]) -> tuple[str, str]:
    """Write generated frames to binary and YAML format files. Returns filenames."""
    cmds = list(frames)

    with pathlib.Path(name_yml := out_path + SUFFIX_YML_FRAME).open(mode="w") as yml_file:
        yaml.dump(cmds, yml_file)

    with pathlib.Path(name_bin := out_path + SUFFIX_BIN_FRAME).open(mode="wb") as bin_file:
        for cmd in cmds:
            for u32 in cmd.data:
                bin_file.write(struct.pack("<I", u32.get_val()))
    return name_bin, name_yml


def add_file_to_yml(filename: str, yml: dict) -> None:
    """Add the file to the yml."""
    yml.append(
        {
            "filename": filename,
            "mode": "c",
            "attr": "aligned (4)",  # align all data to 4B
        }
    )


def add_file_to_params(filename: str, varname: str, params: dict) -> None:
    """Add the filename to the params."""
    params[varname] = filename
