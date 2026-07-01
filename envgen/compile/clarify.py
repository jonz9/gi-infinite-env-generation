"""Ambiguity / clarification detection (Stage 3, S3-T06).

Before the compiler tries to turn a natural-language command into edit ops, this
module flags commands that are *genuinely* under-specified — so the host agent can
ask the user a question instead of guessing. Examples::

    needs_clarification(scene, "move it")            -> flagged (no antecedent)
    needs_clarification(scene, "open the door")      -> flagged (two doors)
    needs_clarification(scene, "add a table at 3,3") -> not flagged

The result is a small :class:`Clarification` value: truthy when clarification is
needed, and unpackable as ``(needs, message)`` so callers may write either::

    c = needs_clarification(scene, cmd)
    if c: ask(c.message)

    needs, msg = needs_clarification(scene, cmd)

Pure heuristics over the scene + command text — no model, no API key. Deliberately
**conservative**: only flag cases that are truly ambiguous, never merely terse.
The detected message is intended to flow into :attr:`CompileResult.notes`.

Inputs : a :class:`~envgen.schema.SceneGraph` and the raw command string.
Outputs: a :class:`Clarification` (``needs`` bool + human-readable ``message``).
Failure: never raises on ordinary input; an empty command is itself flagged.
Version: 1.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..schema import EntityType, SceneGraph

__all__ = ["Clarification", "needs_clarification"]


# Pronouns that point at an *object* but carry no antecedent on their own.
_OBJECT_PRONOUNS = frozenset({"it", "them", "that", "this", "those", "these"})
# Pronouns that point at a *location* ("put it there") — ungroundable alone.
_LOCATION_PRONOUNS = frozenset({"there", "here"})

# Coarse verb buckets used to decide which checks apply.
_ADD_VERBS = frozenset({"add", "place", "put", "create", "spawn", "insert", "drop"})
_MOVE_VERBS = frozenset({"move", "drag", "relocate", "shift", "reposition"})

# Definite vs. indefinite determiners — "the door" is ambiguous, "a door" is not.
_DEFINITE = frozenset({"the"})
_DETERMINERS = frozenset({"the", "a", "an", "that", "this", "these", "those"})

# Attribute adjectives that can disambiguate a same-type group on their own.
_DISAMBIGUATORS = frozenset({"locked", "unlocked", "open", "closed"})

# NL type words → EntityType (lowercased, singular).
_TYPE_WORDS: dict[str, EntityType] = {t.value.lower(): t for t in EntityType}

# Spatial language that supplies a location for an add without explicit coords.
_SPATIAL_WORDS = frozenset(
    {
        "north", "south", "east", "west", "top", "bottom", "left", "right",
        "center", "centre", "middle", "corner", "above", "below", "beside",
        "near", "next", "adjacent",
    }
)

# A coordinate like "3,3" / "3, 3" — a sufficient location for an add.
_COORD_RE = re.compile(r"\d+\s*,\s*\d+")
# "at 3 3" — two whitespace-separated integers after "at".
_AT_COORD_RE = re.compile(r"\bat\s+\d+\s+\d+\b")


@dataclass(frozen=True)
class Clarification:
    """Whether a command needs clarification, plus a human-readable reason.

    Truthy iff :attr:`needs` is set, and iterable as ``(needs, message)`` so the
    return value works with both ``if c:`` and ``needs, msg = ...`` call styles.
    """

    needs: bool
    message: str = ""

    def __bool__(self) -> bool:
        return self.needs

    def __iter__(self):
        yield self.needs
        yield self.message


def _tokens(command: str) -> list[str]:
    """Lowercase, strip punctuation (keeping digits/commas split out), tokenize."""
    cleaned = re.sub(r"[^\w\s,]", " ", command.lower())
    return cleaned.replace(",", " ").split()


def needs_clarification(
    scene: SceneGraph,
    command: str,
    *,
    last_mentioned: str | None = None,
) -> Clarification:
    """Flag an under-specified ``command`` against the current ``scene``.

    Parameters
    ----------
    scene: the current world the command edits.
    command: the raw natural-language command.
    last_mentioned: id of a previously referenced object, if any. When present it
        supplies the antecedent for a pronoun, so "move it" is no longer ambiguous.

    Returns
    -------
    A :class:`Clarification`. ``needs`` is ``True`` only for genuinely ambiguous
    commands; the ``message`` then explains what to disambiguate.
    """
    if command is None or not command.strip():
        return Clarification(True, "empty command: nothing to compile; please say what to change.")

    tokens = _tokens(command)
    token_set = set(tokens)
    verbs = token_set & (_ADD_VERBS | _MOVE_VERBS)

    # 1. Object pronoun with no antecedent ("move it", "remove that").
    object_pronoun = next((t for t in tokens if t in _OBJECT_PRONOUNS), None)
    if object_pronoun is not None and last_mentioned is None:
        return Clarification(
            True,
            f"ambiguous reference {object_pronoun!r} in {command!r}: no antecedent "
            f"is known. Which object do you mean?",
        )

    # 2. Location pronoun for a placement/move ("put it there") with no antecedent.
    if (token_set & _LOCATION_PRONOUNS) and (verbs & (_ADD_VERBS | _MOVE_VERBS)):
        if last_mentioned is None:
            loc = next(t for t in tokens if t in _LOCATION_PRONOUNS)
            return Clarification(
                True,
                f"under-specified location {loc!r} in {command!r}: where exactly? "
                f"Give a coordinate (e.g. 3,3) or a spatial phrase.",
            )

    # 3. Ambiguous definite reference ("the door" when several doors exist).
    ambiguous = _ambiguous_definite(scene, tokens)
    if ambiguous is not None:
        return ambiguous

    # 4. An add with no location at all.
    if verbs & _ADD_VERBS:
        missing = _missing_add_location(command, tokens)
        if missing is not None:
            return missing

    return Clarification(False, "")


def _ambiguous_definite(scene: SceneGraph, tokens: list[str]) -> Clarification | None:
    """Flag "the <type>" where the scene holds more than one such object.

    Only definite references with no disambiguating attribute adjective are flagged;
    indefinite ("a door") and attribute-qualified ("the locked door") are left alone.
    """
    for i, tok in enumerate(tokens):
        etype = _type_of(tok)
        if etype is None:
            continue
        # Look back over the determiner + adjective run preceding the type word.
        determiner = None
        adjectives: list[str] = []
        j = i - 1
        while j >= 0 and tokens[j] not in _TYPE_WORDS and _type_of(tokens[j]) is None:
            if tokens[j] in _DETERMINERS:
                determiner = tokens[j]
                break
            adjectives.append(tokens[j])
            j -= 1
        if determiner not in _DEFINITE:
            continue
        if any(adj in _DISAMBIGUATORS for adj in adjectives):
            continue  # an adjective may already pin it down
        matches = scene.of_type(etype)
        if len(matches) > 1:
            ids = ", ".join(o.id for o in matches)
            return Clarification(
                True,
                f"ambiguous reference 'the {etype.value.lower()}': "
                f"{len(matches)} candidates ({ids}). Which one?",
            )
    return None


def _missing_add_location(command: str, tokens: list[str]) -> Clarification | None:
    """Flag an add command that names no coordinate and no spatial phrase."""
    if _COORD_RE.search(command) or _AT_COORD_RE.search(command.lower()):
        return None
    if set(tokens) & _SPATIAL_WORDS:
        return None
    return Clarification(
        True,
        f"missing location in {command!r}: where should it go? "
        f"Give a coordinate (e.g. 3,3) or a spatial phrase (e.g. 'next to the exit').",
    )


def _type_of(token: str) -> EntityType | None:
    """Map a (possibly plural) NL type word to an EntityType, else None."""
    if token in _TYPE_WORDS:
        return _TYPE_WORDS[token]
    if token.endswith("s") and token[:-1] in _TYPE_WORDS:
        return _TYPE_WORDS[token[:-1]]
    return None
