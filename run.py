#!/usr/bin/env python3
"""End-to-end harness: text prompt -> scene -> validate -> render -> solve.

This is the deliverable entrypoint. It walks the full finite-world loop for one
prompt and prints a human-readable trace ending in SOLVED or FAILED.

Usage::

    python run.py "a room with two tables, a key behind a wall, a locked door"
    python run.py --offline "..."   # skip the LLM, use the bundled example scene
    python run.py                    # no prompt -> offline demo on the example

Planning calls Claude (needs ANTHROPIC_API_KEY and the `anthropic` package). When
the key is missing, or with --offline / no prompt, the harness falls back to the
bundled `examples/room_key_door.json` so the loop is always runnable. Exit code is
0 when the generated environment is SOLVED, 1 when not, 2 on a planning failure.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from envgen.planner import DEFAULT_MODEL
from envgen.render import render_scene
from envgen.repair import RepairError, plan_valid
from envgen.schema import SceneGraph
from envgen.solve import solve
from envgen.validate import validate

EXAMPLE = Path(__file__).resolve().parent / "examples" / "room_key_door.json"


def _rule(title: str) -> None:
    print(f"\n=== {title} ===")


def _obtain_scene(prompt: str | None, offline: bool, model: str) -> tuple[SceneGraph, str]:
    """Return (scene, provenance). Falls back to the bundled example offline."""
    use_llm = bool(prompt) and not offline and bool(os.environ.get("ANTHROPIC_API_KEY"))
    if not use_llm:
        why = "offline flag" if offline else "no prompt" if not prompt else "no ANTHROPIC_API_KEY"
        return SceneGraph.from_json(EXAMPLE.read_text()), f"bundled example ({why})"
    scene, attempts = plan_valid(prompt, model=model)  # already validated + repaired
    return scene, f"planned by Claude ({model}); {len(attempts)} attempt(s)"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Text -> playable 2D environment -> solver.")
    parser.add_argument("prompt", nargs="?", default=None, help="natural-language level request")
    parser.add_argument("--offline", action="store_true", help="skip the LLM; use the bundled example")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Claude model id (default {DEFAULT_MODEL})")
    args = parser.parse_args(argv)

    _rule("PROMPT")
    print(args.prompt or "(none — offline demo)")

    _rule("SCENE")
    try:
        scene, provenance = _obtain_scene(args.prompt, args.offline, args.model)
    except RepairError as exc:
        print(f"planning failed: {exc}")
        return 2
    print(f"source: {provenance}\ngoal: {scene.goal}")

    _rule("VALIDATION")
    report = validate(scene)
    print("ok" if report.ok else "INVALID:\n  " + "\n  ".join(report.errors))

    _rule("RENDER")
    print(render_scene(scene))

    _rule("SOLVE")
    result = solve(scene)
    verdict = "SOLVED" if result.solved else "FAILED"
    print(f"{verdict} — {result.reason}")
    return 0 if result.solved else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
