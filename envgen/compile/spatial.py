"""Spatial-language grounding (Stage 3, S3-T08).

Map a natural-language spatial *phrase* to a concrete grid coordinate against a
scene. Pure and deterministic — no model call. The compiler uses this to turn
"north of the player" / "top-left corner" / "next to the exit" / "center" into the
``[x, y]`` an edit op needs.

Coordinate convention (from :mod:`envgen.schema`)
-------------------------------------------------
Positions are ``(x, y)``: ``x`` is the column (``0..w-1``), ``y`` is the row
(``0..h-1``), origin ``(0, 0)`` at the top-left. Therefore:

* **north** = up = ``y - 1``
* **south** = down = ``y + 1``
* **east**  = right = ``x + 1``
* **west**  = left = ``x - 1``

Out-of-grid handling
--------------------
This module **errors** rather than clamps. A directional phrase that would step
off the grid (e.g. "north of (3, 0)") raises :class:`SpatialError`. Clamping would
silently collapse distinct intents onto edge cells; erroring keeps the result
unambiguous and lets the repair loop surface the problem. (Use the returned coord
or handle the error — never a silently-wrong cell.)

Public API
----------
``ground(scene, phrase, anchor=None) -> (x, y)``
"""
from __future__ import annotations

import re
from typing import Any

from envgen.schema import SceneGraph, SceneObject


class SpatialError(ValueError):
    """Raised when a phrase is unparseable, needs a missing anchor, or grounds
    to a coordinate outside the grid. The message is specific so it can feed the
    compiler repair loop."""


# Unit step (dx, dy) per cardinal direction, in screen coordinates (y grows down).
_DIRECTIONS: dict[str, tuple[int, int]] = {
    "north": (0, -1),
    "south": (0, 1),
    "east": (1, 0),
    "west": (-1, 0),
    "up": (0, -1),
    "down": (0, 1),
    "right": (1, 0),
    "left": (-1, 0),
}

# Synonyms collapsing onto the canonical corner key.
_CORNERS: dict[str, str] = {
    "top-left": "top-left",
    "top left": "top-left",
    "upper-left": "top-left",
    "upper left": "top-left",
    "top-right": "top-right",
    "top right": "top-right",
    "upper-right": "top-right",
    "upper right": "top-right",
    "bottom-left": "bottom-left",
    "bottom left": "bottom-left",
    "lower-left": "bottom-left",
    "lower left": "bottom-left",
    "bottom-right": "bottom-right",
    "bottom right": "bottom-right",
    "lower-right": "bottom-right",
    "lower right": "bottom-right",
}

# Deterministic neighbour priority for "next to": E, S, W, N.
_ADJACENT_ORDER: tuple[tuple[int, int], ...] = ((1, 0), (0, 1), (-1, 0), (0, -1))


def ground(
    scene: SceneGraph,
    phrase: str,
    anchor: Any = None,
) -> tuple[int, int]:
    """Ground a spatial ``phrase`` to an ``(x, y)`` coordinate in ``scene``.

    Parameters
    ----------
    scene:
        The world; only its grid bounds (``scene.grid.w/h``) are consulted.
    phrase:
        e.g. ``"center"``, ``"top-left corner"``, ``"north of the player"``,
        ``"next to the exit"``. Case-insensitive; surrounding prose is tolerated.
    anchor:
        For relative phrases ("north of …", "next to …"): the reference point.
        Accepts a ``(x, y)`` coord, a :class:`SceneObject` (uses ``.pos``), or
        ``None`` when the phrase is self-contained (corners / center).

    Returns
    -------
    A ``(x, y)`` tuple guaranteed in-bounds.

    Raises
    ------
    SpatialError
        If the phrase is unparseable, a relative phrase lacks an anchor, or the
        result would fall outside the grid.
    """
    if not isinstance(phrase, str) or not phrase.strip():
        raise SpatialError(f"empty or non-string phrase: {phrase!r}")

    text = phrase.strip().lower()
    grid = scene.grid

    if "center" in text or "centre" in text or "middle" in text:
        return _check_bounds(grid, (grid.w // 2, grid.h // 2), phrase)

    corner = _match_corner(text)
    if corner is not None:
        return _corner_coord(grid, corner)

    direction = _match_direction(text)
    if direction is not None:
        return _directional(grid, direction, anchor, phrase)

    if "next to" in text or "beside" in text or "adjacent" in text:
        return _next_to(grid, anchor, phrase)

    raise SpatialError(f"unparseable spatial phrase: {phrase!r}")


# --- phrase matchers -------------------------------------------------------

def _match_corner(text: str) -> str | None:
    """Return the canonical corner key referenced in ``text``, or ``None``."""
    for token, canonical in _CORNERS.items():
        if token in text:
            return canonical
    return None


def _match_direction(text: str) -> str | None:
    """Return a cardinal direction word present in ``text``, or ``None``.

    Only matches when paired with "of" (e.g. "north of …") so a stray "up" in
    "upper-left" is handled by the corner matcher instead. Uses word boundaries.
    """
    for word in _DIRECTIONS:
        if re.search(rf"\b{word}\b(?:\s+of\b)?", text) and (
            f"{word} of" in text or re.search(rf"\bto the {word}\b", text)
        ):
            return word
    return None


# --- coordinate builders ---------------------------------------------------

def _corner_coord(grid: Any, corner: str) -> tuple[int, int]:
    """The exact cell for a named corner (always in-bounds for a positive grid)."""
    last_x, last_y = grid.w - 1, grid.h - 1
    return {
        "top-left": (0, 0),
        "top-right": (last_x, 0),
        "bottom-left": (0, last_y),
        "bottom-right": (last_x, last_y),
    }[corner]


def _directional(
    grid: Any, direction: str, anchor: Any, phrase: str
) -> tuple[int, int]:
    """Step one cell from ``anchor`` in ``direction``; error if off-grid."""
    ax, ay = _anchor_coord(anchor, phrase)
    dx, dy = _DIRECTIONS[direction]
    return _check_bounds(grid, (ax + dx, ay + dy), phrase)


def _next_to(grid: Any, anchor: Any, phrase: str) -> tuple[int, int]:
    """First in-bounds neighbour of ``anchor`` (priority E, S, W, N)."""
    ax, ay = _anchor_coord(anchor, phrase)
    for dx, dy in _ADJACENT_ORDER:
        cand = (ax + dx, ay + dy)
        if grid.in_bounds(*cand):
            return cand
    raise SpatialError(
        f"no in-bounds cell adjacent to {(ax, ay)} for phrase {phrase!r}"
    )


# --- helpers ---------------------------------------------------------------

def _anchor_coord(anchor: Any, phrase: str) -> tuple[int, int]:
    """Normalize ``anchor`` (coord or SceneObject) to an ``(x, y)`` tuple."""
    if anchor is None:
        raise SpatialError(f"phrase {phrase!r} needs an anchor, but none was given")
    if isinstance(anchor, SceneObject):
        return (int(anchor.pos[0]), int(anchor.pos[1]))
    if isinstance(anchor, (tuple, list)) and len(anchor) == 2:
        return (int(anchor[0]), int(anchor[1]))
    raise SpatialError(
        f"anchor must be an (x, y) coord or SceneObject, got {anchor!r}"
    )


def _check_bounds(
    grid: Any, coord: tuple[int, int], phrase: str
) -> tuple[int, int]:
    """Return ``coord`` if in-bounds, else raise (documented no-clamp policy)."""
    x, y = coord
    if not grid.in_bounds(x, y):
        raise SpatialError(
            f"phrase {phrase!r} grounds to {coord}, which is outside the "
            f"{grid.w}x{grid.h} grid"
        )
    return (x, y)
