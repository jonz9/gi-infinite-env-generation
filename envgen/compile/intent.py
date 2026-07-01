"""Coarse intent classifier for NL commands (Stage 3, S3-T09).

A small, pure, deterministic keyword/heuristic classifier — *no* training and *no*
model. It maps a natural-language command into one of a handful of coarse intents so
the compiler can route prompting and sanity-check the op the model proposes.

``classify(command) -> (intent, confidence)`` where ``confidence`` is a simple
heuristic score in ``[0, 1]``. Empty / ambiguous input is handled gracefully by
falling back to :data:`Intent.QUERY` with low confidence.
"""
from __future__ import annotations

import re
from enum import Enum


class Intent(str, Enum):
    """Coarse command intents. String-valued so ``intent == "add"`` works too."""

    ADD = "add"
    REMOVE = "remove"
    MOVE = "move"
    TERRAIN = "terrain"
    GOAL = "goal"
    EXTEND = "extend"
    QUERY = "query"


# Keyword cues per intent. Each entry is a (regex, weight) pair; the regex is matched
# with word boundaries against the lowercased command. Higher weights mark cues that
# are strongly diagnostic of a single intent. Order does not matter — scores sum.
_CUES: dict[Intent, list[tuple[str, float]]] = {
    Intent.ADD: [
        (r"add", 2.0),
        (r"place", 2.0),
        (r"put", 1.5),
        (r"create", 1.5),
        (r"spawn", 1.5),
        (r"insert", 1.5),
        (r"drop", 1.0),
        (r"new", 1.0),
    ],
    Intent.REMOVE: [
        (r"remove", 2.0),
        (r"delete", 2.0),
        (r"del", 1.0),
        (r"erase", 1.5),
        (r"destroy", 1.5),
        (r"clear", 1.0),
        (r"get rid of", 2.0),
        (r"take out", 1.5),
    ],
    Intent.MOVE: [
        (r"move", 2.0),
        (r"shift", 1.5),
        (r"relocate", 2.0),
        (r"drag", 1.5),
        (r"reposition", 2.0),
        (r"teleport", 1.5),
        (r"slide", 1.0),
    ],
    Intent.TERRAIN: [
        (r"carve", 2.0),
        (r"dig", 1.5),
        (r"wall", 1.5),
        (r"walls", 1.5),
        (r"floor", 1.5),
        (r"tile", 1.5),
        (r"terrain", 2.0),
        (r"fill", 1.5),
        (r"water", 1.0),
        (r"lava", 1.0),
        (r"paint", 1.0),
    ],
    Intent.GOAL: [
        (r"goal", 2.0),
        (r"objective", 2.0),
        (r"win condition", 2.0),
        (r"reward", 1.5),
        (r"task", 1.0),
        (r"mission", 1.5),
    ],
    Intent.EXTEND: [
        (r"extend", 2.0),
        (r"expand", 2.0),
        (r"grow", 1.5),
        (r"enlarge", 1.5),
        (r"stretch", 1.0),
        (r"generate more", 2.0),
        (r"north", 1.0),
        (r"south", 1.0),
        (r"east", 1.0),
        (r"west", 1.0),
    ],
    Intent.QUERY: [
        (r"where", 2.0),
        (r"what", 1.5),
        (r"which", 1.5),
        (r"how many", 2.0),
        (r"is there", 1.5),
        (r"are there", 1.5),
        (r"list", 1.5),
        (r"show", 1.0),
        (r"find", 1.0),
        (r"locate", 1.5),
    ],
}


def _score(command: str) -> dict[Intent, float]:
    """Sum keyword weights per intent for ``command`` (already lowercased)."""
    scores: dict[Intent, float] = {intent: 0.0 for intent in Intent}
    for intent, cues in _CUES.items():
        for pattern, weight in cues:
            # ``\b`` boundaries keep "add" from matching "ladder"; multi-word cues
            # like "get rid of" still match as a phrase.
            if re.search(rf"\b{pattern}\b", command):
                scores[intent] += weight
    # A trailing "?" is a strong signal of a query regardless of keywords.
    if command.strip().endswith("?"):
        scores[Intent.QUERY] += 1.5
    return scores


def classify(command: str) -> tuple[Intent, float]:
    """Classify ``command`` into a coarse :class:`Intent` plus a confidence in [0,1].

    Pure and deterministic. Empty or signal-free input returns
    ``(Intent.QUERY, 0.0)`` — query is the safe, side-effect-free default.
    """
    if not command or not command.strip():
        return Intent.QUERY, 0.0

    scores = _score(command.lower())
    total = sum(scores.values())
    if total <= 0.0:
        return Intent.QUERY, 0.0

    # Pick the highest-scoring intent; ties break deterministically by Intent order.
    order = list(Intent)
    best = max(order, key=lambda i: (scores[i], -order.index(i)))
    best_score = scores[best]

    # Confidence blends share-of-total (how dominant the winner is) with absolute
    # evidence (a single weak cue should not read as certain).
    share = best_score / total
    evidence = min(best_score / 2.0, 1.0)
    confidence = round(min(1.0, 0.5 * share + 0.5 * evidence), 4)
    return best, confidence
