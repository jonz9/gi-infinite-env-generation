"""NL→edit-ops compiler core (Stage 3, S3-T02).

The generalization of :mod:`envgen.planner` from "prompt → whole scene" to
"(current world, command) → edit-op *diff*". Host-agnostic and key-free: the caller
supplies a :data:`~envgen.compile.base.Complete` seam (the host agent, or a test's
canned function); there is no vendor SDK and no API key.

Flow: load the editor system prompt (v1 or v2), build the user prompt from
:func:`~envgen.compile.summary.summarize` + the command, call ``complete``, and run
the raw text through :func:`~envgen.compile.parse.extract_ops`. Each extracted op dict
is checked with :func:`envgen.edit.op_from_dict` so malformed ops surface as a note
rather than crashing the caller.
"""
from __future__ import annotations

from pathlib import Path

from envgen.compile.base import Complete, CompileResult
from envgen.compile.parse import CompileParseError, extract_ops
from envgen.compile.summary import summarize
from envgen.edit import EditError, op_from_dict
from envgen.schema import SceneGraph

_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


def load_system_prompt(prompt_name: str = "editor_system") -> str:
    """Read an editor system prompt from ``prompts/<prompt_name>.md``.

    ``prompt_name`` selects the variant (``"editor_system"`` or
    ``"editor_system_v2"``), so the eval harness can A/B prompts.
    """
    path = _PROMPTS_DIR / f"{prompt_name}.md"
    return path.read_text(encoding="utf-8")


def build_user_prompt(scene: SceneGraph, command: str) -> str:
    """Compose the user prompt: the current world summary + the NL command."""
    return (
        "Current world:\n"
        f"{summarize(scene)}\n\n"
        f"Command: {command}\n\n"
        "Emit the JSON list of edit ops (a diff against the world above)."
    )


def compile_edit(
    scene: SceneGraph,
    command: str,
    *,
    complete: Complete,
    prompt_name: str = "editor_system",
) -> CompileResult:
    """Compile one NL ``command`` against ``scene`` into a list of edit-op dicts.

    ``complete(system, user) -> text`` is the required, injectable model seam
    (key-free). Returns a :class:`CompileResult` with the op dicts, the raw model
    text, and a ``notes`` string. Unparseable output (no JSON found, or an op dict
    ``op_from_dict`` rejects) yields empty/partial ops plus an explanatory note
    instead of raising — so the repair loop (S3-T05) can react.
    """
    system = load_system_prompt(prompt_name)
    user = build_user_prompt(scene, command)
    raw = complete(system, user)

    try:
        dicts = extract_ops(raw)
    except CompileParseError as exc:
        return CompileResult(ops=[], raw=raw, notes=f"no ops extracted: {exc}")

    ops, notes = _check_ops(dicts)
    return CompileResult(ops=ops, raw=raw, notes=notes)


def _check_ops(dicts: list[dict]) -> tuple[list[dict], str]:
    """Keep op dicts that :func:`op_from_dict` accepts; note the ones it rejects."""
    ops: list[dict] = []
    problems: list[str] = []
    for d in dicts:
        try:
            op_from_dict(d)
        except EditError as exc:
            problems.append(f"{d.get('op', d)!r}: {exc}")
            continue
        ops.append(d)
    notes = "" if not problems else "rejected ops: " + "; ".join(problems)
    return ops, notes
