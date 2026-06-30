"""Typed command grammar — a tiny human DSL that compiles to edit-op dicts.

This is the *non-LLM* command surface for the Stage-2 harness (S2-T12). The
LLM compiler in Stage 3 is the other surface; both emit the same op dicts that
:func:`envgen.edit.op_from_dict` turns into :class:`~envgen.edit.base.EditOp`s.

A *line* is one verb plus its arguments, e.g.::

    add door at 6,3 locked
    add key at 2,5 opens door1
    add table at 4,4
    move player to 1,1
    remove table1
    carve 2,5 floor
    fill 1,1 3,3 wall
    goal reach exit
    setprop door1 locked false

:func:`parse_command` returns exactly one op dict; :func:`parse_script` parses a
multi-line block (skipping blanks and ``#`` comments) into a list of op dicts.
Unparseable input or an unknown verb raises :class:`CommandError` (a
:class:`ValueError`) with a specific message.

Parsing is intentionally shallow: it produces *well-shaped* op dicts but does not
re-implement op validation (bounds, overlaps, unknown ids). Those are enforced by
the ops themselves at apply time, keeping this layer small and deterministic.
"""
from __future__ import annotations

from typing import Any, Callable

__all__ = ["CommandError", "parse_command", "parse_script"]


class CommandError(ValueError):
    """Raised when a DSL line cannot be parsed (bad syntax or unknown verb).

    Subclasses :class:`ValueError` so callers can catch either; the message is
    specific so the harness can echo it back to the user.
    """


# Map the friendly entity word to the canonical ``EntityType`` value.
_ENTITY_WORDS = {
    "player": "Player",
    "table": "Table",
    "key": "Key",
    "door": "Door",
    "exit": "Exit",
}

# Tile words accepted by carve/fill.
_TILE_WORDS = {"floor": 0, "wall": 1}


def _coord(token: str) -> list[int]:
    """Parse ``"x,y"`` into ``[x, y]`` ints, or raise CommandError."""
    parts = token.split(",")
    if len(parts) != 2:
        raise CommandError(f"expected a coordinate 'x,y', got {token!r}")
    try:
        return [int(parts[0]), int(parts[1])]
    except ValueError:
        raise CommandError(f"coordinate must be integers 'x,y', got {token!r}")


def _scalar(token: str) -> Any:
    """Coerce a bare token to bool/None/int, else leave it as a string."""
    low = token.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if low in ("null", "none"):
        return None
    try:
        return int(token)
    except ValueError:
        return token


# --- per-verb handlers --------------------------------------------------------
# Each takes the argument tokens (verb already stripped) and returns one op dict.


def _parse_add(args: list[str]) -> dict[str, Any]:
    """``add <kind> at x,y [locked] [opens <id>] [id <id>]``."""
    if len(args) < 3 or args[1] != "at":
        raise CommandError("usage: add <kind> at x,y [locked] [opens <id>] [id <id>]")
    kind = args[0].lower()
    if kind not in _ENTITY_WORDS:
        valid = ", ".join(sorted(_ENTITY_WORDS))
        raise CommandError(f"unknown object kind {args[0]!r}; valid: {valid}")
    op: dict[str, Any] = {"op": "AddObject", "type": _ENTITY_WORDS[kind], "pos": _coord(args[2])}
    rest = args[3:]
    i = 0
    while i < len(rest):
        word = rest[i].lower()
        if word == "locked":
            op["locked"] = True
            i += 1
        elif word in ("opens", "id"):
            if i + 1 >= len(rest):
                raise CommandError(f"{word!r} needs a value")
            op[word] = rest[i + 1]
            i += 2
        else:
            raise CommandError(f"unexpected token {rest[i]!r} in add command")
    return op


def _parse_move(args: list[str]) -> dict[str, Any]:
    """``move <id> to x,y``."""
    if len(args) != 3 or args[1] != "to":
        raise CommandError("usage: move <id> to x,y")
    return {"op": "MoveObject", "id": args[0], "to": _coord(args[2])}


def _parse_remove(args: list[str]) -> dict[str, Any]:
    """``remove <id>``."""
    if len(args) != 1:
        raise CommandError("usage: remove <id>")
    return {"op": "RemoveObject", "id": args[0]}


def _parse_carve(args: list[str]) -> dict[str, Any]:
    """``carve x,y floor|wall``."""
    if len(args) != 2:
        raise CommandError("usage: carve x,y floor|wall")
    tile = args[1].lower()
    if tile not in _TILE_WORDS:
        raise CommandError(f"carve tile must be 'floor' or 'wall', got {args[1]!r}")
    return {"op": "Carve", "cells": [_coord(args[0])], "tile": _TILE_WORDS[tile]}


def _parse_fill(args: list[str]) -> dict[str, Any]:
    """``fill x0,y0 x1,y1 floor|wall``."""
    if len(args) != 3:
        raise CommandError("usage: fill x0,y0 x1,y1 floor|wall")
    tile = args[2].lower()
    if tile not in _TILE_WORDS:
        raise CommandError(f"fill tile must be 'floor' or 'wall', got {args[2]!r}")
    (x0, y0), (x1, y1) = _coord(args[0]), _coord(args[1])
    return {"op": "FillRegion", "x0": x0, "y0": y0, "x1": x1, "y1": y1, "value": _TILE_WORDS[tile]}


def _parse_goal(args: list[str]) -> dict[str, Any]:
    """``goal <free text...>`` — the rest of the line is the goal string."""
    if not args:
        raise CommandError("usage: goal <text>")
    return {"op": "SetGoal", "goal": " ".join(args)}


def _parse_setprop(args: list[str]) -> dict[str, Any]:
    """``setprop <id> <prop> <value>`` (value coerced to bool/None/int/str)."""
    if len(args) != 3:
        raise CommandError("usage: setprop <id> <prop> <value>")
    return {"op": "SetProp", "id": args[0], "prop": args[1], "value": _scalar(args[2])}


_DISPATCH: dict[str, Callable[[list[str]], dict[str, Any]]] = {
    "add": _parse_add,
    "move": _parse_move,
    "remove": _parse_remove,
    "carve": _parse_carve,
    "fill": _parse_fill,
    "goal": _parse_goal,
    "setprop": _parse_setprop,
}


def parse_command(line: str) -> dict[str, Any]:
    """Parse one DSL ``line`` into a single edit-op dict.

    Raises :class:`CommandError` on an empty line, unknown verb, or malformed
    arguments. The returned dict is shaped for :func:`envgen.edit.op_from_dict`.
    """
    tokens = line.strip().split()
    if not tokens:
        raise CommandError("empty command")
    verb = tokens[0].lower()
    handler = _DISPATCH.get(verb)
    if handler is None:
        valid = ", ".join(sorted(_DISPATCH))
        raise CommandError(f"unknown command verb {tokens[0]!r}; valid verbs: {valid}")
    return handler(tokens[1:])


def parse_script(text: str) -> list[dict[str, Any]]:
    """Parse a multi-line block into a list of op dicts.

    Blank lines and ``#`` comment lines are skipped. Each remaining line is one
    command; the first bad line raises :class:`CommandError`.
    """
    ops: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        ops.append(parse_command(line))
    return ops
