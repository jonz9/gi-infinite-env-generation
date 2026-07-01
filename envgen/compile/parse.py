"""Ops extraction — pull a JSON edit-op list out of raw model text (Stage 3).

The compiler core (S3-T02) asks the model for a JSON **list of edit ops** and hands
the raw text here. Models wrap that JSON in prose or a ```json fence, and sometimes
emit a single op object instead of a list — this module normalizes all of those into
a ``list[dict]``. It mirrors the robustness of :func:`envgen.planner.extract_json`
(fenced block first, then a balanced bare span) but targets *arrays* (and a lone
object, promoted to a 1-element list).

This is a *syntactic* step only: it returns op dicts and does NOT validate op
semantics — the caller runs :func:`envgen.edit.op_from_dict` on each dict, which
raises :class:`~envgen.edit.base.EditError` for unknown/ill-formed ops.
"""
from __future__ import annotations

import json
import re
from typing import Any

# A fenced ```json (or bare ```) block capturing the first array or object inside.
_FENCE_RE = re.compile(r"```(?:json)?\s*(\[.*?\]|\{.*?\})\s*```", re.DOTALL)


class CompileParseError(ValueError):
    """Raised when no JSON op array/object can be extracted from model text.

    A specific error (a ``ValueError`` subclass) so the compile repair loop
    (S3-T05) can feed the failure back to the model, mirroring
    :class:`~envgen.schema.SchemaError` / :class:`~envgen.edit.base.EditError`.
    """


def extract_ops(text: str) -> list[dict[str, Any]]:
    """Extract a list of op dicts from raw model ``text``.

    Tries, in order: a fenced ```json block, the first balanced bare ``[...]``
    array, then the first balanced bare ``{...}`` object (promoted to a 1-element
    list). An array of objects is returned as-is; a single object becomes
    ``[obj]``. Raises :class:`CompileParseError` if none of these yields a JSON
    array or object. Op *semantics* are not checked here.
    """
    for candidate in _candidates(text):
        parsed = _try_load(candidate)
        ops = _as_op_list(parsed) if parsed is not None else None
        if ops is not None:
            return ops
    raise CompileParseError(
        "no JSON op array or object found in model text: " + repr(text[:200])
    )


def _candidates(text: str):
    """Yield candidate JSON spans, most-specific first (fence, array, object)."""
    fenced = _FENCE_RE.search(text)
    if fenced:
        yield fenced.group(1)
    bare_array = _first_balanced(text, "[", "]")
    if bare_array is not None:
        yield bare_array
    bare_object = _first_balanced(text, "{", "}")
    if bare_object is not None:
        yield bare_object


def _try_load(span: str) -> Any | None:
    """Parse ``span`` as JSON, returning the value or ``None`` if it is invalid."""
    try:
        return json.loads(span)
    except (json.JSONDecodeError, ValueError):
        return None


def _as_op_list(parsed: Any) -> list[dict[str, Any]] | None:
    """Normalize parsed JSON into a list of op dicts, or ``None`` if not op-shaped.

    Returning ``None`` (rather than raising) lets :func:`extract_ops` skip a
    candidate that parsed as JSON but isn't an op container — e.g. a nested
    ``[x, y]`` coordinate matched before the enclosing op object — and try the
    next candidate. No op *semantics* are validated.
    """
    if isinstance(parsed, dict):
        return [parsed]
    if isinstance(parsed, list) and parsed and all(isinstance(i, dict) for i in parsed):
        return parsed
    return None


def _first_balanced(text: str, open_ch: str, close_ch: str) -> str | None:
    """Return the first ``open_ch``-balanced span, or ``None``.

    Depth counting is string-literal aware so brackets/braces inside JSON string
    values don't throw off the balance (same technique as the planner).
    """
    start = text.find(open_ch)
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
        elif ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None
