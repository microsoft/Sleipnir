# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Code to parse enums and structs from DWARF format."""

# ruff: noqa: ANN401 # Value can be any type for setattr and getattr methods.
# ruff: noqa: SLF001 # "_" prepended to all fields to avoid conflict with field names in datatypes.

import collections
import ctypes
import logging
import math
import pathlib
from typing import Any

import vsc
from ruamel.yaml.representer import HexInt

import slp_dwarfclasses as dc
import slp_extract_dwarf as extract_dwarf


class BfEnums:
    """Given a name, returns the enum value if it exists as an enum in the elf.

    Returns None if no value was found.
    """

    def __init__(self: "BfEnums", all_enums: dict) -> None:
        """Store reference to the enum dict parsed from DWARF."""
        self.all_enums = all_enums
        self.lookup = {}

    def __getattr__(self: "BfEnums", name: str) -> int:
        """Allow enums to be accessed as an attribute."""
        if name in self.lookup:
            return self.lookup[name]

        for enum_dict in self.all_enums.values():
            if name in enum_dict:
                self.lookup[name] = enum_dict[name]
                return self.lookup[name]

        raise AttributeError(name)


enm = None
"""Global variable holding an instance of BfEnums once populated by parse_dwarf_from_elf"""

types = None
"""Global variable holding all dwarf types once populated by parse_dwarf_from_elf"""

id2obj = {}
"""Global dictionary to hold references to the parent since vsc does not allow direct ref"""


class BfType:
    """Generic object to hold a Sleipnir datatype."""

    def __init__(self: "BfType", parent: "BfType" = None) -> None:
        """Store a reference to the id of the parent and backannotate in the id2obj."""
        self._parent = id(parent) if parent is not None else None
        self._value = 0
        id2obj[id(parent)] = parent

    def get_val(self: "BfType") -> int:
        """Return the value of this type."""
        return self._value

    """Each child class that inherits from BfType has to implement 3 methods:
    1. def update_from_member(self: "BfType", updater: "BfType") -> None:
       This method is called by member instances when their value is updated.
       It should handle how the member value update impact the value of this instance.
       Can be skipped for leaf instances (not expected to have members).

    2. @property
       def _size(self: "BfType") -> int:
           return xyz

    3. def set_val(self: "BfDtype", val: int, *, from_parent: bool = False) -> None:
       This method updates the value of the instance. It also propagates it to
       the parent instance if the update did not come from the parent itself (indicated
       by boolean from_parent)
    """


@vsc.randobj
class BfStruct(BfType):
    """Holds a C struct defined in Sleipnir."""

    def __init__(self: "BfStruct", dwarf_type: dc.Struct, parent: "BfType" = None) -> None:
        """Populate members based on data of the struct parsed from DWARF."""
        super().__init__(parent)

        offsets = collections.OrderedDict()
        _e = collections.OrderedDict()
        for key, value in dwarf_type.members.items():
            if key.startswith("_"):
                msg = f"Invalid field name: {key}"
                raise KeyError(msg)
            if not isinstance(value, dc.BitField):
                msg = f"Struct member {key} is an instance of {value.__class__} and not BitField"
                raise TypeError(msg)

            member = vsc.rand_attr(create_type_instance(value["type"], parent=self))
            # If size is not given in BitField, get it from the struct definiton itself
            if isinstance(member, BfDtype) and ((e_size := value["size"]) is not None):
                member._size = e_size

            _e[key] = member
            offsets[key] = value["bit_offset"]

        # Set the fields as attributes
        for name, field in _e.items():
            BfType.__setattr__(self, name, field)

        self._offsets = offsets

        # Size should be precomputed from DWARF itself
        if dwarf_type.size is None:
            msg = f"{self!r} does not have its size defined."
            raise ValueError(msg)

        self._size = dwarf_type.size

    def pre_rand(self: "BfStruct") -> None:
        """Set is_rand only for some fields if they are a union.

        For a struct, just call this on all member fields, nothing to do otherwise.
        """
        for attr_name in self._offsets:
            member = object.__getattribute__(self, attr_name)
            if isinstance(member, BfStruct | BfArray | BfUnion) and member._int_field_info.is_rand:
                member.pre_rand()

    def post_rand(self: "BfStruct") -> None:
        """Update values after randomization."""
        for attr_name in self._offsets:
            member = object.__getattribute__(self, attr_name)
            if isinstance(member, BfStruct | BfArray | BfUnion) and member._int_field_info.is_rand:
                member.post_rand()

        new_value = 0
        # Now all values are available, compute self value
        for attr_name, offset in self._offsets.items():
            member = object.__getattribute__(self, attr_name)
            value = member.get_val()
            new_value |= value << offset

        # Get the value from that member and fan it out to everyone else.
        self.set_val(new_value, from_parent=True)

    def set_val(self: "BfStruct", val: int, *, from_parent: bool = False) -> None:
        """Update the value of this struct and its members."""
        if hasattr(self, "_size") and val >= 2**self._size:
            msg = f"value of {val} exceeds size of {self._size} for member {self!r}."
            raise ValueError(msg)
        self._value = val

        # Need to update all member variables to the new value.
        for name, offset in self._offsets.items():
            member = object.__getattribute__(self, name)
            mask = (1 << member._size) - 1
            member_val = (val >> offset) & mask
            member.set_val(member_val, from_parent=True)

        if self._parent and not from_parent:
            parent = id2obj[self._parent]
            parent.update_from_member(self)

    def update_from_member(self: "BfStruct", updater: "BfType") -> None:
        """Hook for members to call when their value is updated."""
        value = updater.get_val()

        def is_updater_name(attr_name: str) -> bool:
            return object.__getattribute__(self, attr_name) is updater

        name = next(filter(is_updater_name, self._offsets))

        offset = self._offsets[name]
        # Create a mask with 1s in the bits to be replaced
        mask = ((1 << updater._size) - 1) << offset
        # Clear the bits to be replaced in the original number
        new_value = self._value & ~mask
        # Shift the replacement bits to the correct position and combine with the original number
        new_value |= (value << offset) & mask

        self.set_val(new_value)

    @classmethod
    def to_yaml(cls, representer, node):  # noqa: ANN001, ANN206 # Boilerplate code.
        """Let YAML serializer know what to take."""
        repr_fields = collections.OrderedDict(
            (k, object.__getattribute__(node, k)) for k in node._offsets
        )
        return representer.represent_dict(repr_fields)


@vsc.randobj
class BfUnion(BfType):
    """Holds a C union defined in Sleipnir."""

    def __init__(self: "BfUnion", dwarf_type: dc.Union, parent: "BfType" = None) -> None:
        """Populate members based on data of the union parsed from DWARF."""
        super().__init__(parent)

        _e = {}
        for key, value in dwarf_type.items():
            if key.startswith("_"):
                msg = f"Invalid field name: {key}"
                raise KeyError(msg)
            _e[key] = vsc.rand_attr(create_type_instance(value, parent=self))

        # Sanity check: All member elements should have same size
        bit_sizes = {x._size for x in _e.values() if not isinstance(x, BfDtype)}
        if len(bit_sizes) != 1:
            msg = "Union's member elements have different sizes"
            raise ValueError(msg)

        # Sanity check: The basic datatypes should have a minimum size as above
        if not bit_sizes:
            # Special case: Union of only basic datatypes. Not handled for now.
            msg = "Union of only basic datatypes unsupported"
            raise ValueError(msg)

        bit_size = bit_sizes.pop()  # All are same, so just pick the first entry as the size
        basic_dtypes = filter(lambda x: isinstance(x, BfDtype), _e.values())

        # Assumption: they are all basic datatypes, no good way to check for now
        if any(x._size < bit_size for x in basic_dtypes):
            msg = "Basic data type members of this union can hold less than the other ones."
            raise ValueError(msg)

        self._size = bit_size

        # Set the fields as attributes
        for name, field in _e.items():
            BfType.__setattr__(self, name, field)

    def pre_rand(self: "BfUnion") -> None:
        """Pick only one field in the union as a randomizable one.

        This is to avoid race conditions when randomizer starts setting field values.
        """
        members = collections.OrderedDict()
        for attr_name in dir(self):
            if isinstance(member := object.__getattribute__(self, attr_name), BfType):
                members[attr_name] = member

        # Second step, filter out BfArray if others are present
        non_dtype_members = collections.OrderedDict(
            (k, v) for k, v in members.items() if not isinstance(v, BfDtype)
        )
        non_array_members = collections.OrderedDict(
            (k, v) for k, v in non_dtype_members.items() if not isinstance(v, BfArray)
        )

        # Use this as the rand_member then
        if non_array_members:
            rand_member_name, rand_member = next(iter(non_array_members.items()))
        else:
            rand_member_name, rand_member = next(iter(non_dtype_members.items()))

        # Disable randomization on all other members
        for member_name, member in members.items():
            if member is not rand_member:
                member._int_field_info.set_is_rand(False)
                logging.debug(
                    "Only one union member (%s) enabled for randomization, so disabling on %s",
                    rand_member_name,
                    member_name,
                )

        # Enable randomization on the selected member
        rand_member._int_field_info.set_is_rand(True)

        # Now do the same for rand_member.
        rand_member.pre_rand()

    def post_rand(self: "BfUnion") -> None:
        """By rule, there is only one member that underwent randomization.

        Find that member and get the value to fan it out.
        """
        for attr_name in dir(self):
            member = object.__getattribute__(self, attr_name)
            if isinstance(member, BfStruct | BfArray | BfUnion) and member._int_field_info.is_rand:
                member.post_rand()
                new_value = member.get_val()
                break
        else:
            # Random member is of type BfDtype
            for attr_name in dir(self):
                member = object.__getattribute__(self, attr_name)
                if isinstance(member, BfDtype) and member._int_field_info.is_rand:
                    new_value = member.get_val()
                    break
            else:
                msg = "No member of the union is marked for randomization."
                raise ValueError(msg)

        # Get the value from that member and fan it out to everyone else.
        self.set_val(new_value, from_parent=True)

    def set_val(self: "BfUnion", val: int, *, from_parent: bool = False) -> None:
        """Update the value of this union and its members."""
        if hasattr(self, "_size") and val >= 2**self._size:
            msg = f"value of {val} exceeds size of {self._size} for member {self!r}."
            raise ValueError(msg)
        self._value = val

        for attr_name in dir(self):
            if isinstance(member := object.__getattribute__(self, attr_name), BfType):
                member.set_val(val, from_parent=True)

        if self._parent and not from_parent:
            parent = id2obj[self._parent]
            parent.update_from_member(self)

    def update_from_member(self: "BfUnion", updater: "BfType") -> None:
        """Hook for members to call when their value is updated."""
        self.set_val(updater.get_val())

    @classmethod
    def to_yaml(cls, representer, node):  # noqa: ANN001, ANN206 # Boilerplate code.
        """Let YAML serializer know what to take.

        This is tricky for Union, as there are multple representations for the same value.
        Return all representations as this is for debug purposes.
        """
        repr_fields = {}
        for name in dir(node):
            if not isinstance(field := object.__getattribute__(node, name), BfType):
                continue
            repr_fields[name] = field
        return representer.represent_dict(repr_fields)


class BfDtype(vsc.rand_bit_t, BfType):
    """Holds a C datatype defined in Sleipnir."""

    def __init__(self: "BfDtype", dwarf_type: Any, parent: "BfType" = None) -> None:
        """Populate members based on datatype parsed from DWARF."""
        BfType.__init__(self, parent)
        vsc.rand_bit_t.__init__(self, w=8 * ctypes.sizeof(dwarf_type))

    def set_val(self: "BfDtype", val: int, *, from_parent: bool = False) -> None:
        """Update the value of this type."""
        if val >= 2**self._size:
            msg = f"value of {val} exceeds size of {self._size} for member {self!r}."
            raise ValueError(msg)
        vsc.rand_bit_t.set_val(self, val)

        if self._parent and not from_parent:
            parent = id2obj[self._parent]
            parent.update_from_member(self)

    @property
    def _size(self: "BfDtype") -> int:
        """Return the size of this instance in bits."""
        return self.width

    @_size.setter
    def _size(self: "BfDtype", val: int) -> None:
        self.width = val

    def build_field_model(self: "BfDtype", name: str) -> vsc.FieldScalarModel:
        """Overriding this method to avoid recursive call of set_val."""
        self._int_field_info.name = name
        if self._int_field_info.model is None:
            self._int_field_info.model = vsc.FieldScalarModel(
                name, self.width, self.is_signed, self._int_field_info.is_rand
            )
            vsc.rand_bit_t.set_val(self, self._init_val)
        else:
            # Ensure the name matches superstructure
            self._int_field_info.model.name = name

        return self._int_field_info.model

    @classmethod
    def to_yaml(cls, representer, node):  # noqa: ANN001, ANN206 # Boilerplate code.
        """Controls YAML representation of this object. Return the value."""
        return representer.represent_hex_int(
            HexInt(node.get_val(), width=math.ceil(node._size / 4))
        )


@vsc.randobj
class BfArray(list, BfType):
    """Holds a C array defined in Sleipnir."""

    def __init__(self: "BfArray", dwarf_type: Any, parent: "BfType" = None) -> None:
        """Populate members based on data of the array parsed from DWARF."""
        BfType.__init__(self, parent)

        for idx, element in enumerate(dwarf_type):
            member = create_type_instance(element, parent=self)
            field = vsc.rand_attr(member)
            list.append(self, field)
            list.__setattr__(self, f"idx_{idx}", field)

    @property
    def _size(self: "BfArray") -> int:
        """Return the size of this instance in bits."""
        with vsc.raw_mode():
            return self[0]._size * len(self)

    def pre_rand(self: "BfArray") -> None:
        """Set is_rand only for some fields if they are a union.

        For a struct, just call this on all member fields, nothing to do otherwise.
        """
        for member in self:
            if isinstance(member, BfStruct | BfArray | BfUnion) and member._int_field_info.is_rand:
                member.pre_rand()

    def post_rand(self: "BfArray") -> None:
        """Update values after randomization."""
        for member in self:
            if isinstance(member, BfStruct | BfArray | BfUnion) and member._int_field_info.is_rand:
                member.post_rand()

        new_value = 0
        # Now all values are available, compute self value
        for index, member in enumerate(self):
            value = member.get_val()
            offset = index * member._size
            new_value |= value << offset

        # Get the value from that member and fan it out to everyone else.
        self.set_val(new_value, from_parent=True)

    def set_val(self: "BfArray", val: int, *, from_parent: bool = False) -> None:
        """Update the value of this struct and its members."""
        if val >= 2**self._size:
            msg = f"value of {val} exceeds size of {self._size} for member {self!r}."
            raise ValueError(msg)
        self._value = val

        # Need to update all member variables to the new value.
        for index, member in enumerate(self):
            size = member._size
            offset = size * index
            mask = (1 << size) - 1
            member_value = (val >> offset) & mask
            member.set_val(member_value, from_parent=True)

        if self._parent and not from_parent:
            parent = id2obj[self._parent]
            parent.update_from_member(self)

    def update_from_member(self: "BfArray", updater: "BfType") -> None:
        """Hook for members to call when their value is updated."""
        value = updater.get_val()
        index = next(x for x in range(len(self)) if list.__getitem__(self, x) is updater)

        elem_size = updater._size

        # Create a mask with 1s in the bits to be replaced
        mask = ((1 << elem_size) - 1) << (index * elem_size)
        # Clear the bits to be replaced in the original number
        new_value = self._value & ~mask
        # Shift the replacement bits to the correct position and combine with the original number
        new_value |= (value << index * elem_size) & mask

        self.set_val(new_value)

    def __getitem__(self: "BfArray", idx: int) -> Any:
        """Support list like indexing."""
        ret = list.__getitem__(self, idx)

        if isinstance(ret, BfDtype) and not vsc.is_raw_mode():
            # We're not in an expression, so the user
            # wants the value of this field
            return ret.get_val()

        return ret

    def __setitem__(self: "BfArray", idx: int, val: int) -> None:
        """Set member variable value. Update the global value as well."""
        ret = list.__getitem__(self, idx)

        if isinstance(ret, BfType):
            if vsc.is_raw_mode():
                msg = "Attempting to use '=' in a constraint"
                raise Exception(msg)  # noqa: TRY002 Match vsc implementation
            ret.set_val(val)

    @classmethod
    def to_yaml(cls, representer, node):  # noqa: ANN001, ANN206 # Boilerplate code.
        """Let YAML serializer know what to take."""
        with vsc.raw_mode():
            return representer.represent_list(node)


def create_type_instance(type_to_create: Any, parent: BfType = None) -> BfType:
    """Return a container to hold values for an instance of the type."""
    if isinstance(type_to_create, dc.Struct):
        return BfStruct(type_to_create, parent)
    if isinstance(type_to_create, dc.Union):
        return BfUnion(type_to_create, parent)
    if type_to_create in [ctypes.c_uint8, ctypes.c_uint16, ctypes.c_uint32, ctypes.c_uint64]:
        return BfDtype(type_to_create, parent)
    if isinstance(type_to_create, list):
        # Assumption: All elements of the list are of same type
        return BfArray(type_to_create, parent)
    msg = f"Unsupported type: object {type_to_create} is of type {type(type_to_create)}"
    raise ValueError(msg)


def get_type_obj(types: dict, name: str, parent: BfType = None) -> BfType:
    """Parse the datatype definitions from DWARF and return them in python format."""
    if name not in types:
        msg = f"{name} is either not a valid type or the definition is not found in this elf."
        raise ValueError(msg)

    return create_type_instance(types[name], parent=parent)


def parse_dwarf_from_elf(elf_path: str) -> dict:
    """Parse an ELF file and return the DWARF contents in python readable format.

    Currently, it parses enums, structs, unions and typedefs.
    """
    # Clear the global containers
    extract_dwarf.extracted_dies = {
        "types": {},
        "enums": {},
    }
    extract_dwarf.already_extracted_size = {}

    with pathlib.Path(elf_path).open(mode="rb") as infile:
        return extract_dwarf.process_file_with_pattern(infile)
