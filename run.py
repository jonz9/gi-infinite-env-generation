#!/usr/bin/env python3
"""End-to-end harness: scene graph -> validate -> render -> solve.

This is the deliverable entrypoint, and it is **host-agnostic and key-free**. It
runs the deterministic half of the loop on a scene graph (JSON):

    validate -> render (ASCII) -> solve (BFS) -> SOLVED / FAILED

Where does the scene come from? The *agent running this repo* is the planner. The
intended flow (see AGENTS.md) is:

    1. agent reads a natural-language prompt,
    2. agent writes a scene graph to a .json file matching envgen/schema.py,
    3. agent runs:  python run.py <that file.json>

No vendor SDK, no ANTHROPIC_API_KEY. With no argument it runs the bundled worked
example, so the loop is always runnable with zero setup.

Usage::

    python run.py                       # demo on the bundled example
    python run.py path/to/scene.json    # run an agent-authored scene

Exit code: 0 when SOLVED, 1 when FAILED, 2 when the scene won't parse/validate.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from envgen.render import render_scene
from envgen.schema import SceneGraph, SchemaError
from envgen.solve import solve
from envgen.validate import validate

EXAMPLE = Path(__file__).resolve().parent / "examples" / "room_key_door.json"


def _rule(title: str) -> None:
    print(f"\n=== {title} ===")


def _load_scene(path: Path) -> SceneGraph:
    """Read and parse a scene graph file (raises SchemaError on bad JSON/schema)."""
    return SceneGraph.from_json(path.read_text())


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Scene graph -> validate -> render -> solve (key-free)."
    )
    parser.add_argument(
        "scene",
        nargs="?",
        default=None,
        help="path to a scene-graph JSON file (default: bundled example)",
    )
    args = parser.parse_args(argv)

    path = Path(args.scene) if args.scene else EXAMPLE
    provenance = "agent-authored scene" if args.scene else "bundled example (no scene given)"

    _rule("SCENE")
    try:
        scene = _load_scene(path)
    except (OSError, SchemaError) as exc:
        print(f"could not load scene from {path}: {exc}")
        return 2
    print(f"source: {provenance} -> {path}\ngoal: {scene.goal}")

    _rule("VALIDATION")
    report = validate(scene)
    if report.ok:
        print("ok")
    else:
        print("INVALID:\n  " + "\n  ".join(report.errors))
        return 2

    _rule("RENDER")
    print(render_scene(scene))

    _rule("SOLVE")
    result = solve(scene)
    verdict = "SOLVED" if result.solved else "FAILED"
    print(f"{verdict} — {result.reason}")
    return 0 if result.solved else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
