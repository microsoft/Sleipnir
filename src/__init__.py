# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Boilerplate for relative imports to work in Python 3.6."""

import os
import pathlib
import sys

sys.path.append(str(pathlib.Path(os.path.realpath(__file__)).parent))
