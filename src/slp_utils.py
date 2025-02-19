# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Contains utility functions called from sleipnir.py."""

import logging
import pathlib

import slp_composer as composer
import slp_data_packer as dp
import slp_data_randomizer as data_randomizer
import slp_frame_randomizer as frame_randomizer


def gen_frames(test: dict) -> None:
    """Generate frames and related collaterals for the given test."""
    files, params, test_id = test["files"], test["params"], test["id"]

    if not (frame_params := params["sleipnir"].get("frame", {})):
        logging.info(
            "params for 'frame' not set for core %s, skipping generating frames", test["id"]
        )
        return

    if not (num_cmds := frame_params.get("num_cmds", False)):
        logging.info(
            "'num_cmds' for 'frame' not set for core %s, skipping generating frames",
            test["id"],
        )
        return

    if not (rnd_cfg := frame_params.get("rnd_cfg", {})):
        logging.info(
            "'rnd_cfg' for 'frame' not set for core %s, no user constraints will be applied.",
            test["id"],
        )

    file_prefix = dp.PREFIX_DEF + dp.PREFIX_DEF_TEST.format(test_id)

    """
    Steps:
    1. Create N frame cmds and N meta cmds.
    2. Randomize frame cmds according to user cfg (rnd_cfg)
    3. Randomize meta cmds based on the final frames.
    """

    frames = composer.gen_frames(num_cmds)
    frames = list(
        frame_randomizer.randomize_frames(
            frames,
            rnd_cfg,
        )
    )

    bin_name_frame, _ = dp.gen_bin_yaml_output_frame(file_prefix, frames)

    # Add the binary files to the suite.yml
    dp.add_file_to_yml(bin_name_frame, files)

    # Add the cmds filename to the params
    dp.add_file_to_params(bin_name_frame, dp.VARNAME_FILE_FRAME, params)

    # Write params that are read by the C library
    params[dp.VARNAME_NUM_CMDS_FRAME] = num_cmds


def gen_data(test: dict) -> None:
    """Generate random data for the given test."""
    files, params, test_id = test["files"], test["params"], test["id"]

    if (custom_file := params["sleipnir"].get("custom_data_file", None)) is not None:
        logging.info(
            "using data from custom_data_file %s for %s",
            custom_file,
            test["id"],
        )
        custom_file = pathlib.Path(custom_file)

    if custom_file and not custom_file.is_file():
        msg = f"{custom_file} is set as custom_data_file but the file does not exist."
        raise FileNotFoundError(msg)

    if (data_size := params["sleipnir"].get("data_file_size", None)) is None:
        logging.info(
            "'data_file_size' not set for core %s, using default",
            test["id"],
        )

    if (pattern := params["sleipnir"].get("data_pattern", None)) is None:
        logging.info(
            "'data_pattern' not set for core %s, using default",
            test["id"],
        )

    data_prefix = dp.PREFIX_DEF + dp.PREFIX_DEF_TEST.format(test_id)
    bin_name_data, data_size = data_randomizer.randomize_data(
        data_prefix, pattern, data_size, custom_file
    )

    # Add the binary file to the suite.yml
    dp.add_file_to_yml(bin_name_data, files)

    # Add the file name to the params
    dp.add_file_to_params(
        filename=bin_name_data,
        varname=dp.VARNAME_FILE_DATA,
        params=params,
    )

    # Add the file size to the params
    params[dp.VARNAME_SIZE_DATA] = data_size
