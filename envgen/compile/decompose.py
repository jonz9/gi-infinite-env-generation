"""Multi-step command decomposition (Stage 3, S3-T11).

A compound command ("build a maze with three keyed doors", "add a key then lock the
exit") often maps to *several* edits in sequence. This module splits such a command
into ordered sub-commands and compiles each into its own op batch, threading the
scene forward so later steps see the effects of earlier ones — the bridge from one
sentence to many edits.

The split itself goes through the injectable ``complete`` seam (a JSON array of
short sub-command strings), so it runs offline with a canned model. If the model
returns nothing usable, the whole command is treated as a single step.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from envgen.compile.compiler import compile_edit
from envgen.compile.parse import _first_balanced
from envgen.edit import EditError, apply_ops, op_from_dict
from envgen.schema import SceneGraph

#: Internal orchestration prompt for the split call (kept local: it is plumbing,
#: not one of the user-facing editor prompts in ``prompts/``).
_SPLIT_SYSTEM = (
    "You split a compound level-editing command into an ordered list of simple "
    "sub-commands. Output ONLY a JSON array of short strings, each one atomic edit, "
    "in the order they should be applied. If the command is already atomic, return a "
    "one-element array."
)


@dataclass
class Step:
    """One decomposed sub-command and the ops it compiled to."""

    command: str
    ops: list[dict] = field(default_factory=list)
    notes: str = ""


def split_command(command: str, *, complete) -> list[str]:
    """Split ``command`` into ordered sub-command strings via the ``complete`` seam.

    Falls back to ``[command]`` when the model output has no usable JSON string array.
    """
    user = (
        f"Command: {command}\n"
        "Return a JSON array of short sub-command strings, in order."
    )
    raw = complete(_SPLIT_SYSTEM, user)
    subs = _extract_str_list(raw)
    return subs or [command]


def decompose(
    scene: SceneGraph,
    command: str,
    *,
    complete,
    prompt_name: str = "editor_system",
) -> list[Step]:
    """Decompose ``command`` into steps, compiling each against the evolving scene.

    Returns one :class:`Step` per sub-command. The scene is advanced by applying each
    step's ops before compiling the next, so references like "the door you just added"
    resolve against the updated world. Ops that fail to apply are left recorded on the
    step (via its ``notes``) and simply not folded into the running scene.
    """
    steps: list[Step] = []
    current = scene
    for sub in split_command(command, complete=complete):
        result = compile_edit(current, sub, complete=complete, prompt_name=prompt_name)
        step = Step(command=sub, ops=result.ops, notes=result.notes)
        steps.append(step)
        current = _advance(current, result.ops)
    return steps


def _advance(scene: SceneGraph, op_dicts: list[dict]) -> SceneGraph:
    """Apply op dicts to ``scene``, returning the new scene (or the old one on error)."""
    try:
        ops = [op_from_dict(d) for d in op_dicts]
        return apply_ops(scene, ops)
    except EditError:
        return scene


def _extract_str_list(text: str) -> list[str]:
    """Parse the first balanced ``[...]`` in ``text`` as a JSON list of strings."""
    span = _first_balanced(text, "[", "]")
    if span is None:
        return []
    try:
        parsed = json.loads(span)
    except (json.JSONDecodeError, ValueError):
        return []
    if isinstance(parsed, list) and all(isinstance(s, str) for s in parsed):
        return [s for s in parsed if s.strip()]
    return []
