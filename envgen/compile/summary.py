"""World summary serializer (Stage 3, S3-T01).

Turns a :class:`~envgen.schema.SceneGraph` into a compact, NL-friendly text
description for the compiler's *user* prompt. The model reads this summary (the
"known state") plus a command and emits an edit-op *diff* against it — never a
full rewrite. The output is deterministic and bounded in length: large object
lists are capped and very large grids are described by size rather than dumped,
so a huge/infinite world still yields a short prompt.

Functions are pure and side-effect free.
"""
from __future__ import annotations

from envgen.schema import EntityType, SceneGraph, SceneObject

#: Cap on how many objects are listed verbatim; the rest are summarized away.
MAX_OBJECTS = 40


def summarize(scene: SceneGraph, *, max_objects: int = MAX_OBJECTS) -> str:
    """Return a deterministic, bounded NL description of ``scene``.

    Covers the grid size, the goal, every object's id/type/position, and calls
    out locked doors together with the key (if any) that opens each.
    """
    grid = scene.grid
    lines = [
        f"Grid: {grid.w}x{grid.h} (x in 0..{grid.w - 1}, y in 0..{grid.h - 1}); "
        "origin top-left, [x, y] = [col, row].",
        f"Goal: {scene.goal}",
    ]
    lines += _object_lines(scene, max_objects)
    door_notes = _door_notes(scene)
    if door_notes:
        lines.append("Locked doors:")
        lines += door_notes
    return "\n".join(lines)


def _object_lines(scene: SceneGraph, max_objects: int) -> list[str]:
    """One line per object (id, type, pos), capped at ``max_objects``."""
    objs = scene.objects
    total = len(objs)
    if total == 0:
        return ["Objects: (none)"]
    shown = objs[:max_objects]
    header = f"Objects ({total}):"
    if total > max_objects:
        header = f"Objects ({total}, showing first {max_objects}):"
    lines = [header]
    lines += [f"  - {_describe(o)}" for o in shown]
    if total > max_objects:
        lines.append(f"  ... and {total - max_objects} more (omitted for brevity).")
    return lines


def _describe(obj: SceneObject) -> str:
    """A one-line ``id (Type) at [x, y]`` description, with door lock state."""
    base = f"{obj.id} ({obj.type.value}) at [{obj.pos[0]}, {obj.pos[1]}]"
    if obj.type is EntityType.DOOR:
        base += " [locked]" if obj.locked else " [open]"
    if obj.type is EntityType.KEY and obj.opens is not None:
        base += f" opens {obj.opens}"
    return base


def _door_notes(scene: SceneGraph) -> list[str]:
    """For each locked door, name the key that opens it (or note none does)."""
    keys_for = {
        o.opens: o.id
        for o in scene.of_type(EntityType.KEY)
        if o.opens is not None
    }
    notes: list[str] = []
    for door in scene.of_type(EntityType.DOOR):
        if not door.locked:
            continue
        key_id = keys_for.get(door.id)
        if key_id is not None:
            notes.append(f"  - {door.id} is locked; opened by key {key_id}.")
        else:
            notes.append(f"  - {door.id} is locked; no key opens it.")
    return notes
