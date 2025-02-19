# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Constraints, distributions and rand_mode for frames using PyVSC."""

import logging
import types

import vsc

import slp_dwarf_parser as dp

# ruff: noqa: B015 # Ruff is wrongly flagging PyVSC constraints as meaningless

FRAME_CNSTR_PREFIX = "frame."
"""The identifier to use when referring to the frame in user constraints."""

IDX_CONSTR_NAME = "constr_idx{0}"
"""The name of the dynamic constraints that apply per command."""

FRAME_CONSTR_KEY = "constraints_frame"
"""The name of the key under which users specify constraints for frames."""

FRAME_ENABLE_KEY = "enables"
"""The name of the key under which users specify fields to enable randomization for frames."""

FRAME_CONSTR_KEY_PER_CMD = "per_cmd_" + FRAME_CONSTR_KEY
"""The name of the key under which users specify per command constraints for frames."""


@vsc.constraint
def base_constr_frame(self: dp.BfUnion) -> None:
    """Add base constraints for a frame valid for all."""
    enm = dp.enm
    vsc.soft(self.fields.count > 0)
    vsc.soft(self.fields.width > 0)
    vsc.soft(self.fields.height > 0)
    vsc.soft(self.fields.depth > 0)

    with vsc.implies(self.fields.type == enm.FRAME_SINGLE):
        vsc.soft(self.fields.count == 1)

def base_mode_frame(self: dp.BfUnion) -> None:
    """Disable randomization for some fields."""
    with vsc.raw_mode():
        self.fields.id.rand_mode = False

    # Based on knobs/iteration/other conditions
    self.fields.id = 0


def gen_user_constr(constrs: list[str]) -> vsc.constraint_t:
    """Apply user level constraints imported from yml test config."""

    # Return a clojure that can be run on the descriptor to add constraints
    @vsc.constraint
    def user_constr(self: dp.BfDtype) -> None:  # noqa: ARG001 Will be used by the expr
        enm = dp.enm  # noqa: F841 Used by the expr

        for expr in constrs:
            eval(expr)  # noqa: S307 expr is a constraint read by vsc.

    return user_constr


def gen_idx_constr(constrs: dict[str, str]) -> vsc.dynamic_constraint_t:
    """Generate a constraint block with given constraints."""
    constrs = [x.replace(FRAME_CNSTR_PREFIX, "self.") for x in constrs.values()]

    @vsc.dynamic_constraint
    def idx_constr(self: dp.BfUnion) -> None:  # noqa: ARG001 Will be used by the expr
        enm = dp.enm  # noqa: F841 Used by the expr

        for expr in constrs:
            eval(expr)  # noqa: S307 expr is a constraint read by vsc.

    return idx_constr


def parse_cfg(cfg: dict) -> tuple[list[str], list[str]]:
    """Parse user provided cfg to get variables and constraints."""
    rnd_vars = []
    if FRAME_ENABLE_KEY in cfg:
        rnd_vars = cfg[FRAME_ENABLE_KEY]

    constr_exprs = []

    # Validate and process user constraints
    for name, expr in cfg.get(FRAME_CONSTR_KEY, {}).items():
        if FRAME_CNSTR_PREFIX in expr:
            modified_expr = expr.replace(FRAME_CNSTR_PREFIX, "self.")
            logging.debug("Constraint: %s is %s", name, modified_expr)
            constr_exprs.append(modified_expr)
    return rnd_vars, constr_exprs


def add_idx_cnstr(desc: dp.BfUnion, cfg: dict) -> None:
    """Add constraints specific to the descriptor at this index."""
    if not cfg:
        return

    # Add the user constraints to the frame
    for idx, constraints in cfg.get(FRAME_CONSTR_KEY_PER_CMD, {}).items():
        logging.debug("Found per command constraints for idx %d: %s", idx, ", ".join(constraints))
        setattr(desc, IDX_CONSTR_NAME.format(idx), gen_idx_constr(constraints))


def add_cnstr(desc: dp.BfUnion, cfg: dict) -> None:
    """Add constraints to the given instance of frame."""
    # Adds default constraints valid always
    desc.base_constr_frame = base_constr_frame

    # Disable some randomization
    desc.base_mode_frame = types.MethodType(base_mode_frame, desc)
    desc.base_mode_frame()

    if not cfg:
        return

    rnd_vars, constr_exprs = parse_cfg(cfg)

    # Enable randomization for the user specified fields
    with vsc.raw_mode():
        for field_entry in rnd_vars:
            try:
                field = eval(field_entry)  # noqa: S307 Constraints from YAML: trusted source
            except Exception as e:
                msg = f"User constraint {field_entry} is not a valid one, please check again!"
                raise ValueError(msg) from e
            else:
                field.rand_mode = True

    # Add the user constraints to the frame
    desc.user_constr = gen_user_constr(constr_exprs)

    # This will add all per cmd constraints
    add_idx_cnstr(desc, cfg)
