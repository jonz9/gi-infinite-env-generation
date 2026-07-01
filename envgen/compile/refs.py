"""Reference resolution — NL phrase → object id (Stage 3, S3-T07).

Resolve a natural-language reference inside an edit command to a concrete object
id in the *current* scene, without a model for the unambiguous cases. Examples::

    resolve_ref(scene, "the door")          -> "door1"   (if unique)
    resolve_ref(scene, "the locked door")   -> the locked Door's id
    resolve_ref(scene, "door1")             -> "door1"    (explicit id passthrough)
    resolve_ref(scene, "it", last_mentioned="key1") -> "key1"

On ambiguity (more than one match) or no match, raise :class:`RefError` with a
specific message so the compiler's repair / clarification loop can react.

Pure, deterministic, key-free. Operates over a :class:`~envgen.schema.SceneGraph`.
"""
from __future__ import annotations

import re

from ..schema import EntityType, SceneGraph, SceneObject

__all__ = ["RefError", "resolve_ref"]


class RefError(ValueError):
    """Raised when an NL reference cannot be resolved to exactly one object.

    Distinguishes the two failure modes via the message: ambiguity (several
    candidates) and no-match (zero candidates). The text is specific so it can be
    fed back into the compiler's clarification / repair loop.
    """


# Anaphora — pronouns that point back to the previously mentioned object.
_PRONOUNS = frozenset({"it", "that", "this", "them"})

# Leading determiners stripped before parsing a phrase.
_DETERMINERS = frozenset({"the", "a", "an", "that", "this"})

# Attribute adjectives we understand, mapped to a predicate over an object.
_ATTRS: dict[str, "callable"] = {
    "locked": lambda o: o.type is EntityType.DOOR and o.locked,
    "unlocked": lambda o: o.type is EntityType.DOOR and not o.locked,
    "open": lambda o: o.type is EntityType.DOOR and not o.locked,
    "closed": lambda o: o.type is EntityType.DOOR and o.locked,
}

# NL type words → EntityType (lowercased, singular).
_TYPE_WORDS: dict[str, EntityType] = {t.value.lower(): t for t in EntityType}


def _normalize(phrase: str) -> list[str]:
    """Lowercase, strip punctuation, split into tokens."""
    cleaned = re.sub(r"[^\w\s]", " ", phrase.lower())
    return cleaned.split()


def resolve_ref(
    scene: SceneGraph,
    phrase: str,
    last_mentioned: str | None = None,
) -> str:
    """Resolve ``phrase`` to a single object id in ``scene``.

    Resolution order:

    1. **Explicit id** — if ``phrase`` (trimmed) is exactly an object id, return it.
    2. **Pronoun** — "it"/"that"/... resolves to ``last_mentioned``.
    3. **Type (+ attributes)** — "the door", "the locked door": filter objects by
       type word and any recognized attribute adjectives.

    Parameters
    ----------
    scene: the current world.
    phrase: the NL reference (may include a determiner, adjectives, a type word,
        or be a bare id / pronoun).
    last_mentioned: id of the most recently resolved object, for anaphora.

    Returns
    -------
    The matching object id.

    Raises
    ------
    RefError: on empty input, unknown reference, or ambiguity.
    """
    if phrase is None or not phrase.strip():
        raise RefError("empty reference phrase")

    # 1. Explicit id passthrough (exact, before normalization).
    trimmed = phrase.strip()
    if scene.get(trimmed) is not None:
        return trimmed

    tokens = _normalize(phrase)
    if not tokens:
        raise RefError(f"empty reference phrase: {phrase!r}")

    # A single bare token that is an id (case-insensitive recovery).
    if len(tokens) == 1:
        match = scene.get(tokens[0])
        if match is not None:
            return match.id

    # 2. Pronoun / anaphora.
    if any(tok in _PRONOUNS for tok in tokens):
        if last_mentioned is None:
            raise RefError(
                f"pronoun {phrase!r} has no antecedent (last_mentioned is None)"
            )
        if scene.get(last_mentioned) is None:
            raise RefError(
                f"pronoun {phrase!r} refers to unknown object {last_mentioned!r}"
            )
        return last_mentioned

    # 3. Type + attribute filtering.
    return _resolve_descriptive(scene, phrase, tokens)


def _resolve_descriptive(
    scene: SceneGraph, phrase: str, tokens: list[str]
) -> str:
    """Resolve a "[det] [adjectives] <type>" descriptive phrase."""
    etype: EntityType | None = None
    attrs: list[str] = []
    for tok in tokens:
        if tok in _DETERMINERS:
            continue
        if tok in _TYPE_WORDS:
            etype = _TYPE_WORDS[tok]
            continue
        # tolerate a trailing plural ("doors")
        if tok.endswith("s") and tok[:-1] in _TYPE_WORDS:
            etype = _TYPE_WORDS[tok[:-1]]
            continue
        if tok in _ATTRS:
            attrs.append(tok)
            continue
        # Unknown adjective — keep it for the error message but don't filter on it.
        attrs.append(tok)

    if etype is None:
        raise RefError(
            f"could not resolve {phrase!r}: no known object type in the phrase"
        )

    candidates: list[SceneObject] = scene.of_type(etype)

    for attr in attrs:
        pred = _ATTRS.get(attr)
        if pred is None:
            raise RefError(
                f"could not resolve {phrase!r}: unknown attribute {attr!r} "
                f"for type {etype.value}"
            )
        candidates = [o for o in candidates if pred(o)]

    if not candidates:
        descr = " ".join(attrs + [etype.value.lower()]) if attrs else etype.value.lower()
        raise RefError(f"no object matches {phrase!r} (looking for {descr})")
    if len(candidates) > 1:
        ids = ", ".join(o.id for o in candidates)
        raise RefError(
            f"ambiguous reference {phrase!r}: {len(candidates)} matches ({ids}); "
            f"be more specific"
        )
    return candidates[0].id
