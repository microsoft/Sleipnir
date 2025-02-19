# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

# ruff: noqa
# TODO: ruff cleanup

import collections
import ctypes
import re
import sys

from elftools.elf.elffile import ELFFile

# Import custom classes for DWARF parsing
import slp_dwarfclasses as dc

OFFSET_NEG_MASK = 1 << (64 - 1)
"""The mask to check if a number is negative in 2's complement. DWARF uses 64b representation."""

OFFSET_NEG_SUB = 1 << (64)
"""The value to subtract to get a negative number. DWARF uses 64b 2's complement."""


class UnsupportedDieTagException(BaseException):
    """Exception raised when a DIE tag is not supported."""


extracted_dies = {
    "types": {},
    "enums": {},
}

already_extracted_size = {}


def process_file_with_pattern(infile):
    """Extract types or enums with names matching provided pattern."""
    global extracted_dies

    elffile = ELFFile(infile)
    if not elffile.has_dwarf_info():
        msg = "File has no DWARF info."
        raise ValueError(msg)

    # get_dwarf_info returns a DWARFInfo context object, which is the
    # starting point for all DWARF-based processing in pyelftools.
    dwarfinfo = elffile.get_dwarf_info()

    TypeProcessor = collections.namedtuple("TypeProcessor", ["dst", "callback"])
    processors = {
        "DW_TAG_structure_type": TypeProcessor("types", extract_type),
        "DW_TAG_enumeration_type": TypeProcessor("enums", extract_enum_values),
    }

    # Extract all supported types from all compile units.
    warned_unsupported_die_types = []
    supported_types = [
        "DW_TAG_typedef",
        "DW_TAG_structure_type",
        "DW_TAG_union_type",
        "DW_TAG_enumeration_type",
    ]
    extracted = {
        "types": {},
        "enums": {},
    }

    def _extract_die(die):
        parent_die = None
        if die.tag == "DW_TAG_typedef":
            if not die_has_type(die):
                # Ignore typedefs without type information
                return

            # typedef gives name to a possibly anon struct/enum.
            # We may have already extracted that anon struct
            # before reaching this typedef DIE.
            parent_die = die
            die = get_type_die(die)
            anon_name = get_anon_name(die)
            for dst in extracted.values():
                if anon_name in dst:
                    # Already extracted as anon before typedef name was known
                    dst[extracted_name] = dst.pop(anon_name)
                    return

        if die.tag in processors:
            processor = processors[die.tag]
        else:
            # Catch-all for other types like array, base
            processor = processors["DW_TAG_structure_type"]

        if die.offset in extracted_dies[processor.dst]:
            # Already extracted during recursion
            if parent_die:
                # Referenced struct extracted but not named typedef
                extracted_dies[processor.dst][parent_die.offset] = extracted_dies[processor.dst][
                    die.offset
                ]
                extracted[processor.dst][extracted_name] = extracted_dies[processor.dst][die.offset]
            return

        try:
            extracted_type = processor.callback(die)
            extracted[processor.dst][extracted_name] = extracted_type

            if parent_die:
                extracted_dies[processor.dst][parent_die.offset] = extracted_type

        except UnsupportedDieTagException as e:
            unsupported_tag = e.args[0]
            if unsupported_tag not in warned_unsupported_die_types:
                warned_unsupported_die_types.append(unsupported_tag)
                print(f"WARNING: Unsupported DIE tag={unsupported_tag}")

    # If pubtypes exists, use it for quicker type lookup
    pubtypes = dwarfinfo.get_pubtypes()
    if pubtypes:
        # Iterate over all named types in pubtypes
        for extracted_name, entry in pubtypes.items():
            die = dwarfinfo.get_DIE_from_lut_entry(entry)
            _extract_die(die)
    else:
        # Iterate over all DIEs in .debug_info
        for cu in dwarfinfo.iter_CUs():
            for die in cu.iter_DIEs():
                if die.tag not in supported_types:
                    # We dump only structs and enums
                    continue

                if die_has_name(die):
                    extracted_name = get_die_name(die)
                else:
                    # Anonymous struct/enum
                    extracted_name = get_anon_name(die)
                _extract_die(die)

    return extracted


def extract_type(die):
    global extracted_dies
    if die.offset in extracted_dies["types"]:
        return extracted_dies["types"][die.offset]

    if "DW_TAG_typedef" == die.tag:
        type_die = get_type_die(die)
        ret = extract_type(type_die)
    elif "DW_TAG_structure_type" == die.tag:
        ret = extract_structure(die)
    elif "DW_TAG_base_type" == die.tag:
        ret = extract_base_type(die)
    elif "DW_TAG_array_type" == die.tag:
        ret = extract_array(die)
    elif "DW_TAG_enumeration_type" == die.tag:
        ret = extract_enum_type(die)
    elif "DW_TAG_union_type" == die.tag:
        ret = extract_union(die)
    else:
        raise UnsupportedDieTagException(die.tag)

    extracted_dies["types"][die.offset] = ret
    return ret


def extract_type_size(die):
    if die.offset in already_extracted_size:
        return already_extracted_size[die.offset]

    ret = None
    if die.tag == "DW_TAG_typedef":
        type_die = get_type_die(die)
        ret = extract_type_size(type_die)
    elif die.tag == "DW_TAG_structure_type":
        if "DW_AT_byte_size" in die.attributes:
            ret = 8 * die.attributes["DW_AT_byte_size"].value
    already_extracted_size[die.offset] = ret
    return ret


def extract_structure(die):
    ret = dc.Struct()
    ret.size = extract_type_size(die)
    ret.members = collections.OrderedDict()

    for member_die in die.iter_children():
        if member_die.tag != "DW_TAG_member":
            continue
        if not die_has_name(member_die):
            member_name = get_anon_name(member_die)
        else:
            member_name = get_die_name(member_die)
        member_type_die = get_type_die(member_die)
        member_type = extract_type(member_type_die)
        member_type_size = extract_type_size(member_type_die)
        byte_offset = member_die.attributes["DW_AT_data_member_location"].value

        if "DW_AT_bit_size" in member_die.attributes:
            # Is bit field; record bit size and offset.
            container_size = 8 * ctypes.sizeof(member_type)

            # DWARF records field offsets in big-endian order.
            # Change to little-endian order here.
            field_size = member_die.attributes["DW_AT_bit_size"].value
            die_bit_offset = member_die.attributes["DW_AT_bit_offset"].value

            if die_bit_offset & OFFSET_NEG_MASK:
                # Negative offset; convert to positive.
                die_bit_offset -= OFFSET_NEG_SUB
            field_offset_le = container_size - field_size - die_bit_offset + 8 * byte_offset

            ret.members[member_name] = dc.BitField(
                {
                    "type": member_type,
                    "size": field_size,
                    "bit_offset": field_offset_le,
                }
            )

            assert member_type_size is None or (field_size <= member_type_size), (
                "Bit size assumption wrong!"
            )
        else:
            ret.members[member_name] = dc.BitField(
                {
                    "type": member_type,
                    "size": member_type_size,
                    "bit_offset": 8 * byte_offset,
                }
            )

    return ret


base_types = {
    1: ctypes.c_uint8,
    2: ctypes.c_uint16,
    4: ctypes.c_uint32,
    8: ctypes.c_uint64,
    16: [ctypes.c_uint64] * 2,
}


def extract_base_type(die):
    return base_types[die.attributes["DW_AT_byte_size"].value]


def extract_array(die):
    # Get member type
    member_type_die = get_type_die(die)
    member_type = extract_type(member_type_die)

    # Get member count in the next DIEs
    member_count = []
    for member_count_die in die.iter_children():
        if "DW_TAG_subrange_type" != member_count_die.tag:
            continue
        if "DW_AT_upper_bound" in member_count_die.attributes:
            upper_bound = member_count_die.attributes["DW_AT_upper_bound"].value
            # TODO find out what upper_bound==-1 means
            if upper_bound == 0xFFFFFFFFFFFFFFFF:
                upper_bound = 0

            member_count.append(upper_bound + 1)
        elif "DW_AT_count" in member_count_die.attributes:
            count = member_count_die.attributes["DW_AT_count"].value
            member_count.append(count)

    ret = member_type
    for dim in member_count[::-1]:
        ret = [ret] * dim
    return ret


def extract_enum_type(die):
    if not die_has_type(die):
        # No type definition, assume int32
        return ctypes.c_int32
    member_type_die = get_type_die(die)
    member_type = extract_type(member_type_die)
    return member_type


def extract_enum_values(die):
    global extracted_dies
    if die.offset in extracted_dies["enums"]:
        return extracted_dies["enums"][die.offset]

    ret = {}
    for member_die in die.iter_children():
        if "DW_TAG_enumerator" != member_die.tag:
            continue
        enum_name = get_die_name(member_die)
        enum_value = member_die.attributes["DW_AT_const_value"].value
        ret[enum_name] = enum_value

    extracted_dies["enums"][die.offset] = ret
    return ret


def extract_union(die):
    ret = dc.Union()
    for member_die in die.iter_children():
        if "DW_TAG_member" != member_die.tag:
            continue
        if not die_has_name(member_die):
            member_name = get_anon_name(member_die)
        else:
            member_name = get_die_name(member_die)
        member_type_die = get_type_die(member_die)
        member_type = extract_type(member_type_die)
        ret[member_name] = member_type
    return ret


def die_has_type(die):
    return "DW_AT_type" in die.attributes


def get_type_die(die):
    return get_die_at_offset(die, "DW_AT_type")


def get_die_at_offset(die, offset_attr: str):
    return die.dwarfinfo.get_DIE_from_refaddr(
        die.cu.cu_offset + die.attributes[offset_attr].value, die.cu
    )


def get_next_die(die):
    return die.dwarfinfo.get_DIE_from_refaddr(die.size + die.offset)


def die_has_name(die):
    return "DW_AT_name" in die.attributes


def get_die_name(die):
    return die.attributes["DW_AT_name"].value.decode()


def get_anon_name(die):
    return f"anon_{die.offset:x}"
