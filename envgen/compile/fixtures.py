"""Canned fixtures + golden transcripts for the NL→edit-ops compiler (S3-T10).

A reusable, model-free test rig shared by the other ``envgen.compile`` tests and the
compiler eval harness (S3-T12). It provides:

* :func:`canned` — turn a ``{prompt-substring: model-text}`` mapping into a
  deterministic :data:`~envgen.compile.base.Complete` function, so a test can inject
  exactly the model output it wants with no live model / API key.
* :data:`FIXTURES` — a small library of golden
  ``(scene, command, completion, expected_ops)`` transcripts covering common edits
  (add a door, move the player, carve a wall). Each ``expected_ops`` entry is an op
  dict that :func:`envgen.edit.op_from_dict` accepts.

Everything here is pure and deterministic; importing it has no side effects beyond
the dataclass / function definitions. See ``tickets/README.md`` and the S3-T10 ticket.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from envgen.compile.base import Complete
from envgen.schema import SceneGraph

# Default model text when no mapping key matches: an empty op list (a no-op diff).
DEFAULT_COMPLETION = "[]"


def canned(mapping: dict[str, str], *, default: str = DEFAULT_COMPLETION) -> Complete:
    """Return a deterministic :data:`Complete` that replays canned model text.

    The returned function ignores the ``system`` prompt and looks up a response by
    finding the first ``mapping`` key contained in the ``user`` prompt (insertion
    order), returning its text. If no key matches it returns ``default``. This lets a
    test feed precise model output keyed by the command it expects to see.
    """

    def complete(system: str, user: str) -> str:  # noqa: ARG001 - seam signature
        for key, text in mapping.items():
            if key in user:
                return text
        return default

    return complete


@dataclass(frozen=True)
class Fixture:
    """One golden transcript: a command compiled against a scene → expected ops.

    ``scene_dict`` is the input world (a :class:`SceneGraph`-parseable dict so the
    fixture is self-contained and round-trips through JSON). ``command`` is the NL
    edit. ``completion`` is the canned model text a compiler would receive.
    ``expected_ops`` are the op dicts that should be extracted — each
    :func:`envgen.edit.op_from_dict`-parseable.
    """

    name: str
    scene_dict: dict[str, Any]
    command: str
    completion: str
    expected_ops: list[dict[str, Any]] = field(default_factory=list)

    def scene(self) -> SceneGraph:
        """Build a fresh :class:`SceneGraph` from this fixture's scene dict."""
        return SceneGraph.from_dict(self.scene_dict)


def base_scene_dict() -> dict[str, Any]:
    """A small, solvable 8x6 room (wall border, interior floor) for the fixtures.

    Player at (1,1), Exit at (6,4); every other interior cell is floor, so the
    fixtures' edits all land on valid targets.
    """
    w, h = 8, 6
    tiles = [
        [1 if (x == 0 or x == w - 1 or y == 0 or y == h - 1) else 0 for x in range(w)]
        for y in range(h)
    ]
    return {
        "grid": {"w": w, "h": h, "tiles": tiles},
        "objects": [
            {"id": "player", "type": "Player", "pos": [1, 1]},
            {"id": "exit", "type": "Exit", "pos": [6, 4]},
        ],
        "goal": "reach exit",
    }


# --- golden transcripts -------------------------------------------------------
# Each fixture pairs a command with the model text a compiler would receive and the
# op dicts that should be extracted from it. The completions deliberately use
# different shapes (bare array, ```json fence, lone object) to exercise extraction.

FIXTURES: list[Fixture] = [
    Fixture(
        name="add_door",
        scene_dict=base_scene_dict(),
        command="add a locked door at 3,2",
        completion='[{"op": "AddObject", "type": "Door", "pos": [3, 2], '
        '"locked": true}]',
        expected_ops=[
            {"op": "AddObject", "type": "Door", "pos": [3, 2], "locked": True}
        ],
    ),
    Fixture(
        name="move_player",
        scene_dict=base_scene_dict(),
        command="move the player to 2,3",
        completion=(
            "Sure — relocating the player:\n"
            "```json\n"
            '[{"op": "MoveObject", "id": "player", "to": [2, 3]}]\n'
            "```"
        ),
        expected_ops=[{"op": "MoveObject", "id": "player", "to": [2, 3]}],
    ),
    Fixture(
        name="carve_wall",
        scene_dict=base_scene_dict(),
        command="carve a wall across the middle at 2,2 and 2,3",
        # A lone op object — extract_ops promotes this to a 1-element list.
        completion='{"op": "Carve", "cells": [[2, 2], [2, 3]], "tile": 1}',
        expected_ops=[{"op": "Carve", "cells": [[2, 2], [2, 3]], "tile": 1}],
    ),
]


def fixtures_canned() -> Complete:
    """A single :data:`Complete` replaying every fixture's completion by command."""
    return canned({fx.command: fx.completion for fx in FIXTURES})
