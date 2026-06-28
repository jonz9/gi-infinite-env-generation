"""Tests for the planner (build step 3).

Every test runs FULLY OFFLINE via the injectable ``complete`` seam — no network,
no ANTHROPIC_API_KEY. Each fake ``complete`` returns canned model text so we can
assert that JSON extraction and schema parsing behave correctly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from envgen.planner import extract_json, plan
from envgen.schema import EntityType, SceneGraph, SchemaError

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "room_key_door.json"


def _example_text() -> str:
    return EXAMPLE.read_text()


def _example_dict() -> dict:
    return json.loads(_example_text())


def test_plan_roundtrips_fenced_example() -> None:
    """Bare/fenced example JSON -> SceneGraph that round-trips to the same dict."""
    fenced = "```json\n" + _example_text() + "\n```"

    def complete(system_prompt: str, user_prompt: str) -> str:
        assert system_prompt  # the seam receives the loaded system prompt
        assert user_prompt == "a room with a key and a locked door"
        return fenced

    scene = plan("a room with a key and a locked door", complete=complete)

    assert isinstance(scene, SceneGraph)
    assert scene.to_dict() == _example_dict()
    types = {o.type for o in scene.objects}
    assert EntityType.PLAYER in types
    assert EntityType.EXIT in types


def test_plan_extracts_json_from_prose() -> None:
    """Prose around a fenced JSON object must not defeat extraction."""
    wrapped = (
        "Sure! Here is a solvable level for you:\n\n"
        "```json\n" + _example_text() + "\n```\n\n"
        "Let me know if you'd like it bigger."
    )

    scene = plan("anything", complete=lambda _s, _u: wrapped)

    assert scene.to_dict() == _example_dict()
    assert scene.player is not None


def test_plan_bare_object_with_prose() -> None:
    """A bare (unfenced) JSON object embedded in prose is still extracted."""
    wrapped = "Here you go: " + _example_text() + " -- enjoy!"
    scene = plan("anything", complete=lambda _s, _u: wrapped)
    assert scene.to_dict() == _example_dict()


def test_plan_invalid_json_raises_schema_error() -> None:
    """Non-JSON model output surfaces as SchemaError (via from_json)."""
    with pytest.raises(SchemaError):
        plan("anything", complete=lambda _s, _u: "I cannot do that, sorry.")


def test_plan_bad_schema_raises_schema_error() -> None:
    """Valid JSON but an unknown entity type must raise SchemaError."""
    bad = json.dumps(
        {
            "grid": {"w": 2, "h": 2, "tiles": [[0, 0], [0, 0]]},
            "objects": [{"id": "x", "type": "Dragon", "pos": [0, 0]}],
            "goal": "reach exit",
        }
    )
    with pytest.raises(SchemaError):
        plan("anything", complete=lambda _s, _u: bad)


def test_extract_json_fence_and_bare() -> None:
    """extract_json handles fenced, bare-with-prose, and brace-in-string cases."""
    obj = '{"goal": "reach exit", "note": "has a } brace in a string"}'
    assert json.loads(extract_json("```json\n" + obj + "\n```")) == json.loads(obj)
    assert json.loads(extract_json("prefix " + obj + " suffix")) == json.loads(obj)
