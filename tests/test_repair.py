"""Tests for the repair loop (build step 5).

Every test runs FULLY OFFLINE via the injectable ``complete`` seam — no network,
no ANTHROPIC_API_KEY. The fake ``complete`` callables return canned model text so
we can assert that plan_valid repairs invalid output, threads validator feedback
back into the planner, and gives up (RepairError) when it cannot.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from envgen.repair import Attempt, FEEDBACK_MARKER, RepairError, plan_valid
from envgen.schema import SceneGraph

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "room_key_door.json"


def _valid_text() -> str:
    """The hand-authored, solvable room_key_door scene as raw JSON text."""
    return EXAMPLE.read_text()


def _unsolvable_text() -> str:
    """A structurally well-formed scene whose Exit is walled off (unsolvable)."""
    scene = {
        "grid": {
            "w": 5,
            "h": 5,
            "tiles": [
                [1, 1, 1, 1, 1],
                [1, 0, 1, 0, 1],
                [1, 0, 1, 0, 1],
                [1, 0, 1, 0, 1],
                [1, 1, 1, 1, 1],
            ],
        },
        "objects": [
            {"id": "player", "type": "Player", "pos": [1, 1]},
            {"id": "exit", "type": "Exit", "pos": [3, 1]},
        ],
        "goal": "reach exit",
    }
    return json.dumps(scene)


def test_repairs_after_one_invalid_attempt() -> None:
    """Invalid on call 1, valid on call 2 -> returns the valid scene; log len 2."""
    calls = {"n": 0}

    def complete(system_prompt: str, user_prompt: str) -> str:
        calls["n"] += 1
        return _unsolvable_text() if calls["n"] == 1 else _valid_text()

    scene, attempts = plan_valid("a room with a key and a locked door", complete=complete)

    assert isinstance(scene, SceneGraph)
    assert scene.to_dict() == json.loads(_valid_text())
    assert len(attempts) == 2
    assert attempts[0].errors  # first attempt carried validation errors
    assert not attempts[0].ok
    assert attempts[1].ok


def test_feedback_is_fed_back_to_planner() -> None:
    """The retry's user prompt must contain the previous attempt's error text."""
    seen_prompts: list[str] = []

    def complete(system_prompt: str, user_prompt: str) -> str:
        seen_prompts.append(user_prompt)
        return _unsolvable_text() if len(seen_prompts) == 1 else _valid_text()

    scene, attempts = plan_valid("make me a level", complete=complete)

    assert isinstance(scene, SceneGraph)
    assert len(seen_prompts) == 2
    # First prompt is the bare ask; second carries the repair feedback block.
    assert FEEDBACK_MARKER not in seen_prompts[0]
    assert FEEDBACK_MARKER in seen_prompts[1]
    # Some of the actual error text is threaded through.
    assert "exit is unreachable" in seen_prompts[1]
    assert attempts[0].feedback() in seen_prompts[1]


def test_always_invalid_raises_repair_error() -> None:
    """A complete that never produces a valid scene -> RepairError after retries."""
    calls = {"n": 0}

    def complete(system_prompt: str, user_prompt: str) -> str:
        calls["n"] += 1
        return _unsolvable_text()

    with pytest.raises(RepairError) as excinfo:
        plan_valid("anything", complete=complete, max_retries=3)

    assert calls["n"] == 3  # all retries were attempted
    msg = str(excinfo.value)
    assert "3 attempt" in msg
    assert "exit is unreachable" in msg


def test_parse_failure_recorded_as_raw_error() -> None:
    """Non-JSON output on call 1 is logged as raw_error, then repaired on call 2."""
    calls = {"n": 0}

    def complete(system_prompt: str, user_prompt: str) -> str:
        calls["n"] += 1
        return "I cannot do that." if calls["n"] == 1 else _valid_text()

    scene, attempts = plan_valid("anything", complete=complete)

    assert isinstance(scene, SceneGraph)
    assert len(attempts) == 2
    assert attempts[0].scene is None
    assert attempts[0].raw_error is not None
    assert attempts[1].ok


def test_attempt_dataclass_shape() -> None:
    """Attempt exposes scene/errors/raw_error with the documented ok semantics."""
    failed = Attempt(scene=None, errors=[], raw_error="bad json")
    assert not failed.ok
    assert failed.feedback() == "bad json"
