# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Classes to represent items parsed from DWARF. Overloaded for pyvsc compatibility."""

import collections


class Struct(dict):
    """Used to contain struct members during extraction.

    Precise byte location of members is preserved here.
    """

    def __init__(self: "Struct") -> None:
        """Store members in an OrderedDict and the size."""
        self.size = None
        self.members = collections.OrderedDict()

    def __repr__(self: "Struct") -> str:
        """Emit the member details."""
        return f"Struct(size: {self.size}, members: {self.members.__repr__()})"


class Union(dict):
    """Used to contain union members, as opposed to OrderedDict for struct members."""

    def __repr__(self: "Union") -> str:
        """Emit dict representation but with classname."""
        return f"Union({dict.__repr__(self)})"


class BitField(dict):
    """Used to contain bit fields during struct extraction."""

    def __repr__(self: "BitField") -> str:
        """Emit dict representation but with classname."""
        return f"BitField({dict.__repr__(self)})"
