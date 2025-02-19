# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Code to parse input files for use by other sleipnir's blocks."""

import collections
import logging
import pathlib
import random

from ruamel.yaml import YAML
from ruamel.yaml import representer

representer.RoundTripRepresenter.add_representer(
    collections.defaultdict, representer.RoundTripRepresenter.represent_dict
)
"""Treat defaultdict like a vanilla dict when dumping out to YAML."""

yaml = YAML()
yaml.default_flow_style = False
yaml.indent(mapping=2, sequence=4, offset=2)
"""Add an extra indentation when emitting list items."""

yaml.representer.ignore_aliases = lambda *args: True  # noqa: ARG005 # Need to match function signature.
"""Disable aliases when dumping YAML"""


def process_in_yaml(input_yml: str) -> dict:
    """Read input yml."""
    logging.debug("Reading input YAML %s", input_yml)
    with pathlib.Path(input_yml).open(mode="r") as input_file:
        suite = yaml.load(input_file)

    # Code below uses these keys, so check for it all at once.
    expected_keys = {"seed", "test"}

    for key in expected_keys:
        if key not in suite:
            msg = f"{key} not found in input yml of {input_yml}"
            raise KeyError(msg)

    logging.debug("Initializing seed to %d", suite["seed"])
    # Initialize random number generator with using global seed
    random.seed(suite["seed"])

    for test in suite["test"]:
        # Code below uses these keys, so check for it all at once.
        expected_keys = {"params", "id"}

        for key in expected_keys:
            if key not in test:
                msg = f"{key} not found under test {test} in input yml of {input_yml}"
                raise KeyError(msg)

        # Initialize a list for files if it does not exist. This is populated later.
        if "files" not in test:
            test["files"] = []

    return suite
