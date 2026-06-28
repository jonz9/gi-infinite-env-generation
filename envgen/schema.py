"""Scene graph schema — the engine-independent intermediate representation (IR).

This module defines the *only* handoff between language and simulation: a JSON
scene graph. The planner (an LLM) emits it; the engine consumes it directly.
There is deliberately no code-generation step.

Coordinate convention
---------------------
Positions are ``[x, y]`` where ``x`` is the column (0..w-1) and ``y`` is the row
(0..h-1). The tile layer is indexed ``tiles[y][x]`` with ``1`` = wall (blocking)
and ``0`` = floor (walkable). The origin (0, 0) is the top-left corner.

Scope
-----
This file handles *representation*, *(de)serialization*, and *structural*
well-formedness only (ids unique, positions in bounds, references resolve, ...).
Semantic feasibility — reachability, key-before-door, solvability — is the
validator's job (build step 4), not the schema's.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EntityType(str, Enum):
    """Object types that live in the object layer (walls live in the tile layer)."""

    PLAYER = "Player"
    TABLE = "Table"
    KEY = "Key"
    DOOR = "Door"
    EXIT = "Exit"


# Entity types that block movement when standing on their tile. A locked Door
# blocks until opened; the engine (build step 4+) resolves that dynamically.
BLOCKING_TYPES = frozenset({EntityType.TABLE, EntityType.DOOR})


class SchemaError(ValueError):
    """Raised when a dict/JSON payload cannot be parsed into the schema.

    The message is intentionally specific so the planner repair loop (build
    step 5) can feed it straight back to the LLM.
    """


@dataclass
class SceneObject:
    """A single entity placed on the grid.

    Attributes
    ----------
    id: Unique identifier, referenced by relationships (e.g. ``Key.opens``).
    type: One of :class:`EntityType`.
    pos: ``(x, y)`` grid coordinate.
    opens: For a Key, the id of the Door it unlocks. ``None`` otherwise.
    locked: For a Door, whether it starts locked. Ignored for other types.
    """

    id: str
    type: EntityType
    pos: tuple[int, int]
    opens: str | None = None
    locked: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict, omitting fields that don't apply."""
        out: dict[str, Any] = {
            "id": self.id,
            "type": self.type.value,
            "pos": [self.pos[0], self.pos[1]],
        }
        if self.type is EntityType.KEY and self.opens is not None:
            out["opens"] = self.opens
        if self.type is EntityType.DOOR:
            out["locked"] = self.locked
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SceneObject:
        """Parse a single object dict, raising :class:`SchemaError` on bad input."""
        for key in ("id", "type", "pos"):
            if key not in data:
                raise SchemaError(f"object missing required field {key!r}: {data!r}")
        try:
            etype = EntityType(data["type"])
        except ValueError:
            valid = ", ".join(t.value for t in EntityType)
            raise SchemaError(
                f"unknown object type {data['type']!r} for id {data.get('id')!r}; "
                f"valid types: {valid}"
            )
        pos = data["pos"]
        if not (isinstance(pos, (list, tuple)) and len(pos) == 2):
            raise SchemaError(f"object {data['id']!r} pos must be [x, y], got {pos!r}")
        return cls(
            id=str(data["id"]),
            type=etype,
            pos=(int(pos[0]), int(pos[1])),
            opens=data.get("opens"),
            locked=bool(data.get("locked", False)),
        )


@dataclass
class Grid:
    """The static tile layer. ``tiles[y][x]``: 1 = wall, 0 = floor."""

    w: int
    h: int
    tiles: list[list[int]]

    def in_bounds(self, x: int, y: int) -> bool:
        """Whether ``(x, y)`` falls inside the grid."""
        return 0 <= x < self.w and 0 <= y < self.h

    def is_wall(self, x: int, y: int) -> bool:
        """Whether ``(x, y)`` is a wall tile. Out-of-bounds counts as wall."""
        if not self.in_bounds(x, y):
            return True
        return self.tiles[y][x] == 1

    def to_dict(self) -> dict[str, Any]:
        return {"w": self.w, "h": self.h, "tiles": self.tiles}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Grid:
        for key in ("w", "h", "tiles"):
            if key not in data:
                raise SchemaError(f"grid missing required field {key!r}")
        return cls(w=int(data["w"]), h=int(data["h"]), tiles=data["tiles"])


@dataclass
class SceneGraph:
    """A complete environment description: tile layer + objects + goal."""

    grid: Grid
    objects: list[SceneObject] = field(default_factory=list)
    goal: str = "reach exit"

    # -- accessors ---------------------------------------------------------
    def get(self, obj_id: str) -> SceneObject | None:
        """Return the object with ``obj_id``, or ``None``."""
        return next((o for o in self.objects if o.id == obj_id), None)

    def of_type(self, etype: EntityType) -> list[SceneObject]:
        """All objects of a given type, in definition order."""
        return [o for o in self.objects if o.type is etype]

    @property
    def player(self) -> SceneObject | None:
        """The (single) player object, if present."""
        players = self.of_type(EntityType.PLAYER)
        return players[0] if players else None

    # -- (de)serialization -------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "grid": self.grid.to_dict(),
            "objects": [o.to_dict() for o in self.objects],
            "goal": self.goal,
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        """Serialize to a JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SceneGraph:
        """Parse a scene-graph dict, raising :class:`SchemaError` on bad input."""
        if "grid" not in data:
            raise SchemaError("scene graph missing required field 'grid'")
        objects = [SceneObject.from_dict(o) for o in data.get("objects", [])]
        return cls(
            grid=Grid.from_dict(data["grid"]),
            objects=objects,
            goal=data.get("goal", "reach exit"),
        )

    @classmethod
    def from_json(cls, text: str) -> SceneGraph:
        """Parse a scene graph from a JSON string."""
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SchemaError(f"invalid JSON: {exc}") from exc
        return cls.from_dict(data)


def check_well_formed(scene: SceneGraph) -> list[str]:
    """Return a list of structural problems with ``scene`` (empty == well-formed).

    Structural only: grid shape, tile values, unique ids, in-bounds positions,
    resolvable references, exactly one player. Does NOT check solvability — that
    is the semantic validator's job.
    """
    errors: list[str] = []
    errors += _check_grid(scene.grid)
    errors += _check_objects(scene)
    return errors


def _check_grid(grid: Grid) -> list[str]:
    """Validate grid dimensions and tile contents."""
    errors: list[str] = []
    if grid.w <= 0 or grid.h <= 0:
        errors.append(f"grid dimensions must be positive, got w={grid.w} h={grid.h}")
        return errors  # remaining checks assume sane dimensions
    if len(grid.tiles) != grid.h:
        errors.append(f"tiles has {len(grid.tiles)} rows, expected h={grid.h}")
    for y, row in enumerate(grid.tiles):
        if len(row) != grid.w:
            errors.append(f"tiles row {y} has {len(row)} cols, expected w={grid.w}")
        for x, val in enumerate(row):
            if val not in (0, 1):
                errors.append(f"tile ({x},{y}) is {val!r}, expected 0 or 1")
    return errors


def _check_objects(scene: SceneGraph) -> list[str]:
    """Validate object ids, positions, and cross-references."""
    errors: list[str] = []
    seen: set[str] = set()
    for obj in scene.objects:
        if obj.id in seen:
            errors.append(f"duplicate object id {obj.id!r}")
        seen.add(obj.id)
        if not scene.grid.in_bounds(*obj.pos):
            errors.append(f"object {obj.id!r} at {obj.pos} is out of bounds")
        if obj.type is EntityType.KEY and obj.opens is not None:
            target = scene.get(obj.opens)
            if target is None:
                errors.append(f"key {obj.id!r} opens unknown door {obj.opens!r}")
            elif target.type is not EntityType.DOOR:
                errors.append(f"key {obj.id!r} opens {obj.opens!r}, which is not a Door")

    players = scene.of_type(EntityType.PLAYER)
    if len(players) != 1:
        errors.append(f"expected exactly 1 Player, found {len(players)}")
    return errors


if __name__ == "__main__":  # pragma: no cover - quick manual smoke test
    import pathlib

    example = pathlib.Path(__file__).resolve().parent.parent / "examples" / "room_key_door.json"
    scene = SceneGraph.from_json(example.read_text())
    problems = check_well_formed(scene)
    print(f"loaded {example.name}: {len(scene.objects)} objects, goal={scene.goal!r}")
    print("well-formed" if not problems else "PROBLEMS:\n  " + "\n  ".join(problems))
    # round-trip check
    assert SceneGraph.from_json(scene.to_json()).to_dict() == scene.to_dict()
    print("round-trip OK")
