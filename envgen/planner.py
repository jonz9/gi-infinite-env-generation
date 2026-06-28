"""Planner (build step 3): natural language prompt -> schema-valid scene graph.

The planner prompts Claude with the schema (loaded from
``prompts/planner_system.md`` — prompts never live in source) and parses the
model's reply into a :class:`~envgen.schema.SceneGraph`. There is deliberately
no code-generation step: the model emits JSON, which the engine consumes
directly.

The model call is injectable via the ``complete`` seam so the planner can be
exercised fully offline (see ``tests/test_planner.py``). The default ``complete``
calls the Anthropic SDK; that path needs ``ANTHROPIC_API_KEY`` and the
``anthropic`` package, neither of which the offline tests touch.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable

from envgen.schema import SceneGraph

# Type of the injectable model seam: (system_prompt, user_prompt) -> raw text.
Complete = Callable[[str, str], str]

DEFAULT_MODEL = "claude-opus-4-8"

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


def _anthropic_complete(model: str) -> Complete:
    """Build a default ``complete`` backed by the Anthropic SDK.

    The ``anthropic`` import is lazy so this module imports fine without the
    package installed (only the live path needs it).
    """

    def complete(system_prompt: str, user_prompt: str) -> str:
        import anthropic  # lazy: keeps the dependency optional for offline use

        client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the env
        msg = client.messages.create(
            model=model,
            max_tokens=2000,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return msg.content[0].text

    return complete


def plan(
    prompt: str,
    *,
    complete: Complete | None = None,
    model: str = DEFAULT_MODEL,
) -> SceneGraph:
    """Plan a scene graph from a natural-language ``prompt``.

    ``complete`` is the injectable model seam taking ``(system_prompt,
    user_prompt)`` and returning raw model text; when ``None`` a default backed
    by the Anthropic SDK is used. The raw text is stripped of any prose/fences
    and parsed via :meth:`SceneGraph.from_json` — a
    :class:`~envgen.schema.SchemaError` from bad JSON or a bad schema propagates
    (the repair loop, build step 5, catches it).
    """
    system_prompt = load_system_prompt()
    do_complete = complete if complete is not None else _anthropic_complete(model)
    raw = do_complete(system_prompt, prompt)
    return SceneGraph.from_json(extract_json(raw))


if __name__ == "__main__":  # pragma: no cover - needs a real API key
    import sys

    if len(sys.argv) < 2:
        print('usage: python3 -m envgen.planner "<prompt>"', file=sys.stderr)
        raise SystemExit(2)
    scene = plan(sys.argv[1])
    print(scene.to_json())
