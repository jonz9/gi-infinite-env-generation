"""Planner (build step 3): natural language prompt -> schema-valid scene graph.

The planner is **host-agnostic and key-free**. It does not embed any model SDK.
Instead it exposes the schema (loaded from ``prompts/planner_system.md`` — prompts
never live in source) and parses raw model text into a
:class:`~envgen.schema.SceneGraph`. There is deliberately no code-generation step:
the model emits JSON, which the engine consumes directly.

Who supplies the model text? The *agent that runs this repo* — Claude Code, Codex,
or anything else. The LLM is the harness: the agent reads the prompt, emits a scene
graph, and the deterministic pipeline (validate -> render -> solve) takes over. No
``ANTHROPIC_API_KEY``, no vendor SDK.

The model call is an injectable ``complete`` seam: any
``(system_prompt, user_prompt) -> raw text`` callable. Tests inject a canned one
(see ``tests/test_planner.py``); a caller who wants a specific model wires their own.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from envgen.schema import SceneGraph

# Type of the injectable model seam: (system_prompt, user_prompt) -> raw text.
Complete = Callable[[str, str], str]

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "planner_system.md"


def load_system_prompt() -> str:
    """Read the planner system prompt from ``prompts/planner_system.md``."""
    return _PROMPT_PATH.read_text(encoding="utf-8")


def extract_json(text: str) -> str:
    """Pull a single JSON object out of raw model text.

    Models sometimes wrap the object in prose or a ```json fence. We first look
    for a fenced block, then fall back to the first balanced ``{...}`` span. The
    returned string is handed to :meth:`SceneGraph.from_json`, which raises
    :class:`~envgen.schema.SchemaError` if it is not valid JSON.
    """
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        return fenced.group(1)
    bare = _first_balanced_object(text)
    if bare is not None:
        return bare
    return text.strip()


def _first_balanced_object(text: str) -> str | None:
    """Return the first brace-balanced ``{...}`` substring, or ``None``.

    Brace counting is string-literal aware so braces inside JSON strings don't
    throw off the depth.
    """
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def parse_scene(raw: str) -> SceneGraph:
    """Parse raw model text into a scene graph (no model call).

    Strips any prose/fences via :func:`extract_json` and parses via
    :meth:`SceneGraph.from_json`. A :class:`~envgen.schema.SchemaError` from bad
    JSON or a bad schema propagates (the repair loop, build step 5, catches it).
    This is the seam the host agent uses: it produces the text, this parses it.
    """
    return SceneGraph.from_json(extract_json(raw))


def plan(prompt: str, *, complete: Complete) -> SceneGraph:
    """Plan a scene graph from a natural-language ``prompt``.

    ``complete`` is the (required) model seam taking ``(system_prompt,
    user_prompt)`` and returning raw model text. There is no built-in vendor SDK:
    the host agent, a test, or a caller's own model supplies it. The returned text
    is parsed via :func:`parse_scene`.
    """
    raw = complete(load_system_prompt(), prompt)
    return parse_scene(raw)


if __name__ == "__main__":  # pragma: no cover - simple stdin utility, no network
    import sys

    # Key-free utility: pipe raw model output in, get a clean validated scene out.
    #   <agent emits JSON> | python3 -m envgen.planner
    raw = sys.stdin.read()
    if not raw.strip():
        print("usage: <raw model text with a JSON scene> | python3 -m envgen.planner",
              file=sys.stderr)
        raise SystemExit(2)
    print(parse_scene(raw).to_json())
