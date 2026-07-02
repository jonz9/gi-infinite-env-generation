"""Typed objective predicates — machine-checkable, engine-portable win conditions.

The scene graph's ``goal`` was a free string (``"reach exit"``) informally interpreted
by the grid engine. This module promotes it to a small typed predicate language so the
objective is *code-level and verifiable* — exactly the property the brief prizes
("successfully picked up the can from the table… far more reliable than using a VLM on
pixel output"). The same predicate tree evaluates identically against a grid rollout or
a physics rollout (it reads only player position + inventory + entity positions), so it
is the reward-model's regression target: pair a rendered frame with ``satisfied(...)``.

Backward compatible: a legacy ``goal`` string maps to ``Reach(<exit id>)``; a richer
objective rides in ``goal`` as a JSON predicate dict. Nothing in the frozen schema or
grid engine changes — the predicate is consumed alongside them.

Predicate JSON shapes::

    {"pred": "reach", "target": "exit"}      # player standing on entity `target`
    {"pred": "has",   "item": "key1"}        # `item` collected (in inventory)
    {"all": [ ...predicates... ]}            # conjunction
    {"any": [ ...predicates... ]}            # disjunction
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from envgen.schema import EntityType, SceneGraph

Coord = tuple[int, int]


@dataclass(frozen=True)
class ObjectiveState:
    """The minimal world state a predicate reads — engine-agnostic on purpose."""

    player_pos: Coord
    inventory: frozenset[str]
    positions: dict[str, Coord]     # entity id -> position


class Predicate:
    """Base class for a machine-checkable objective term."""

    def evaluate(self, state: ObjectiveState) -> bool:  # pragma: no cover - abstract
        raise NotImplementedError

    def to_dict(self) -> dict[str, Any]:  # pragma: no cover - abstract
        raise NotImplementedError

    def describe(self) -> str:  # pragma: no cover - abstract
        raise NotImplementedError


@dataclass(frozen=True)
class Reach(Predicate):
    """True when the player is standing on entity ``target``."""

    target: str

    def evaluate(self, state: ObjectiveState) -> bool:
        return state.player_pos == state.positions.get(self.target)

    def to_dict(self) -> dict[str, Any]:
        return {"pred": "reach", "target": self.target}

    def describe(self) -> str:
        return f"reach {self.target}"


@dataclass(frozen=True)
class Has(Predicate):
    """True when ``item`` has been collected (is in the inventory)."""

    item: str

    def evaluate(self, state: ObjectiveState) -> bool:
        return self.item in state.inventory

    def to_dict(self) -> dict[str, Any]:
        return {"pred": "has", "item": self.item}

    def describe(self) -> str:
        return f"has {self.item}"


@dataclass(frozen=True)
class All(Predicate):
    """Conjunction — every child predicate must hold."""

    terms: tuple[Predicate, ...]

    def evaluate(self, state: ObjectiveState) -> bool:
        return all(t.evaluate(state) for t in self.terms)

    def to_dict(self) -> dict[str, Any]:
        return {"all": [t.to_dict() for t in self.terms]}

    def describe(self) -> str:
        return " and ".join(t.describe() for t in self.terms)


@dataclass(frozen=True)
class Any_(Predicate):
    """Disjunction — at least one child predicate must hold."""

    terms: tuple[Predicate, ...]

    def evaluate(self, state: ObjectiveState) -> bool:
        return any(t.evaluate(state) for t in self.terms)

    def to_dict(self) -> dict[str, Any]:
        return {"any": [t.to_dict() for t in self.terms]}

    def describe(self) -> str:
        return "(" + " or ".join(t.describe() for t in self.terms) + ")"


def predicate_from_dict(data: dict[str, Any]) -> Predicate:
    """Parse one predicate dict (recursively for ``all``/``any``)."""
    if "all" in data:
        return All(tuple(predicate_from_dict(t) for t in data["all"]))
    if "any" in data:
        return Any_(tuple(predicate_from_dict(t) for t in data["any"]))
    kind = data.get("pred")
    if kind == "reach":
        return Reach(str(data["target"]))
    if kind == "has":
        return Has(str(data["item"]))
    raise ValueError(f"unknown objective predicate: {data!r}")


def objective_from_scene(scene: SceneGraph) -> Predicate:
    """Build the scene's objective predicate.

    A JSON-object ``goal`` is parsed as a predicate tree; any other string is the
    legacy ``reach exit`` objective, mapped to ``Reach(<the Exit's id>)``.
    """
    goal = (scene.goal or "").strip()
    if goal.startswith("{"):
        try:
            return predicate_from_dict(json.loads(goal))
        except (json.JSONDecodeError, ValueError, KeyError):
            pass  # fall through to legacy handling
    exits = scene.of_type(EntityType.EXIT)
    return Reach(exits[0].id if exits else "exit")


def state_from_scene(
    scene: SceneGraph,
    player_pos: Coord | None = None,
    inventory: frozenset[str] = frozenset(),
) -> ObjectiveState:
    """Assemble an :class:`ObjectiveState` from a scene (+ optional live overrides)."""
    positions = {o.id: o.pos for o in scene.objects}
    if player_pos is None:
        player = scene.player
        player_pos = player.pos if player is not None else (0, 0)
    return ObjectiveState(player_pos=player_pos, inventory=inventory, positions=positions)


def satisfied(
    scene: SceneGraph,
    player_pos: Coord | None = None,
    inventory: frozenset[str] = frozenset(),
) -> bool:
    """Whether the scene's objective holds for the given live player state."""
    objective = objective_from_scene(scene)
    return objective.evaluate(state_from_scene(scene, player_pos, inventory))
