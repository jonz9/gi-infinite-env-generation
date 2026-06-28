"""Gym-like environment — ``reset`` / ``step`` over a finite :class:`World`.

This is build step 6 of the harness: the thin runtime layer the solver agent
(step 7) drives. It wraps a :class:`envgen.world.World` (itself a live view over a
validated :class:`envgen.schema.SceneGraph`) and adds the *mechanic* logic that
the World deliberately omits — moving the player, collecting keys, unlocking
doors, and firing the code-level objective (reach the Exit).

Door convention
---------------
Following the package convention, doors are never static blockers in
``World.passable`` / ``World.static_block_at``; locked-door gating is *runtime*
agent logic and lives here in :meth:`GridEnv.step`. A locked door is impassable
until the player holds a key whose ``.opens`` matches the door id, at which point
the door id is added to ``world.opened`` and the player steps onto it.

Determinism
-----------
No randomness, no global state. Two ``GridEnv`` instances built from the same
scene behave identically; calling ``reset`` returns the env to the scene's
initial configuration.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Tuple

from envgen.schema import EntityType, SceneGraph, SceneObject
from envgen.world import Coord, World

# Reward scheme (documented):
#   +1.0   on the step that reaches the Exit (terminal).
#   -0.01  per ordinary step (a small cost so a solver prefers short paths).
# A blocked / no-op move also costs STEP_COST — bumping a wall is not "free", so
# the objective stays "reach the exit in as few moves as possible".
REACH_EXIT_REWARD = 1.0
STEP_COST = -0.01

#: Observation dict returned by :meth:`GridEnv.reset` / :meth:`GridEnv.step`.
Obs = Dict[str, Any]


class Action(Enum):
    """A 4-connected grid move, stored as an ``(dx, dy)`` delta.

    Mirrors the vision policy's move forward / back / left / right. ``y`` grows
    downward (row index), so ``UP`` decrements ``y``.
    """

    UP = (0, -1)
    DOWN = (0, 1)
    LEFT = (-1, 0)
    RIGHT = (1, 0)

    @property
    def delta(self) -> Coord:
        """The ``(dx, dy)`` movement this action applies to ``player_pos``."""
        return self.value


class GridEnv:
    """A deterministic, Gym-like environment over a finite :class:`World`.

    Public API mirrors a minimal Gym contract: :meth:`reset` returns the first
    observation and :meth:`step` returns ``(obs, reward, done, info)``. The solver
    drives via :class:`Action`; it mainly reads ``obs["player_pos"]`` and
    ``obs["done"]``.
    """

    def __init__(self, scene: SceneGraph) -> None:
        """Build an env from a (assumed well-formed) scene graph."""
        self.scene = scene
        self.world = World.from_scene(scene)
        self._start: Coord = self.world.player_pos
        self._exit = scene.of_type(EntityType.EXIT)
        self.done = False

    # -- Gym-like surface --------------------------------------------------
    def reset(self) -> Obs:
        """Reset to the scene's initial state and return the first observation.

        Player returns to the scene start; inventory and opened-doors are empty.
        """
        self.world = World.from_scene(self.scene)
        self.world.player_pos = self._start
        self.world.inventory = set()
        self.world.opened = set()
        self.done = False
        return self._obs()

    def step(self, action: Action) -> Tuple[Obs, float, bool, Dict[str, Any]]:
        """Apply one action; return ``(obs, reward, done, info)``.

        Movement is a no-op (player stays put) when the target cell is a wall, a
        static blocker (Table), or a still-locked door the player can't open.
        Stepping onto a Key collects it; stepping onto a matching locked Door
        unlocks it; stepping onto the Exit ends the episode with a reward.
        """
        if self.done:
            return self._obs(), 0.0, True, {"event": "already_done"}

        target = self._target(action)
        event = self._resolve(target)
        if event != "blocked":
            self.world.player_pos = target

        if event == "reached_exit":
            self.done = True
            return self._obs(), REACH_EXIT_REWARD, True, {"event": event}
        return self._obs(), STEP_COST, False, {"event": event}

    # -- mechanic helpers --------------------------------------------------
    def _target(self, action: Action) -> Coord:
        """The cell the player would move into for ``action``."""
        x, y = self.world.player_pos
        dx, dy = action.delta
        return (x + dx, y + dy)

    def _resolve(self, target: Coord) -> str:
        """Decide what happens at ``target`` and apply collect/unlock effects.

        Returns an event tag for ``info``: one of ``"blocked"``,
        ``"picked_up_key"``, ``"opened_door"``, ``"reached_exit"``, ``"moved"``.
        """
        if self.world.is_wall(target) or self.world.static_block_at(target):
            return "blocked"

        key = self._object_of(target, EntityType.KEY)
        if key is not None:
            self.world.inventory.add(key.id)
            return "picked_up_key"

        door = self._object_of(target, EntityType.DOOR)
        if door is not None:
            return self._resolve_door(door)

        if self._object_of(target, EntityType.EXIT) is not None:
            return "reached_exit"
        return "moved"

    def _resolve_door(self, door: SceneObject) -> str:
        """Gate a locked door: pass only if a held key opens it."""
        if not door.locked or door.id in self.world.opened:
            return "moved"
        if any(self._opens(kid) == door.id for kid in self.world.inventory):
            self.world.opened.add(door.id)
            return "opened_door"
        return "blocked"

    def _object_of(self, pos: Coord, etype: EntityType) -> SceneObject | None:
        """First object of ``etype`` on ``pos``, or ``None``."""
        return next(
            (o for o in self.world.objects_at(pos) if o.type is etype), None
        )

    def _opens(self, key_id: str) -> str | None:
        """The door id a collected key opens (``None`` if unknown)."""
        obj = self.scene.get(key_id)
        return obj.opens if obj is not None else None

    # -- observation -------------------------------------------------------
    def _obs(self) -> Obs:
        """Build the observation dict (see module / class docstrings)."""
        from envgen.render import render  # local import: render imports world only

        return {
            "ascii": render(self.world),
            "player_pos": self.world.player_pos,
            "inventory": frozenset(self.world.inventory),
            "done": self.done,
        }


def _main() -> int:  # pragma: no cover - manual demo
    """Load the worked example and take a few hand-picked steps."""
    import pathlib

    example = (
        pathlib.Path(__file__).resolve().parent.parent
        / "examples"
        / "room_key_door.json"
    )
    env = GridEnv(SceneGraph.from_json(example.read_text()))
    obs = env.reset()
    print("start:")
    print(obs["ascii"], "\n")
    for action in (Action.DOWN, Action.DOWN, Action.RIGHT):
        obs, reward, done, info = env.step(action)
        print(f"{action.name:5s} -> pos={obs['player_pos']} "
              f"reward={reward:+.2f} done={done} event={info['event']}")
    print()
    print(obs["ascii"])
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
