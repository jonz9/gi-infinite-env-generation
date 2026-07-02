"""Box2D physics engine — the scene graph as a real rigid-body world.

The same JSON IR, executed in continuous physics instead of the discrete grid:
wall tiles and Tables become static bodies, the Player a dynamic circle driven by
velocity control, Keys and Exits contact *sensors*, locked Doors solid bodies that
unlock (and disappear) when the player bumps them holding the right key. Top-down,
so gravity is zero and damping supplies the friction feel. 1 tile = 1 meter.

Verification stays layered: the exact BFS/objective plan on the grid is the *proof*;
:func:`run_plan` is the *execution* — a waypoint controller steers the physics body
along the proven path, contact events fire the key/door/exit mechanics, and the typed
objective (:mod:`envgen.objective`) judges the physical end-state. Solved here means
"a rigid body actually drove through the world and the predicate held at the end".

Box2D is imported lazily inside the builder so the stdlib-only core never needs it;
:func:`have_box2d` reports availability and everything raises an actionable error
without it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from envgen.objective import satisfied
from envgen.schema import EntityType, SceneGraph

Vec = Tuple[float, float]

PLAYER_RADIUS = 0.35     # meters; tile = 1m
PLAYER_SPEED = 3.5       # m/s under velocity control
WAYPOINT_TOL = 0.25      # close enough to a tile center to advance
DT = 1.0 / 60.0          # physics timestep
_ITERS = (8, 3)          # velocity / position solver iterations

_INSTALL_HINT = "Box2D not installed; run `pip install Box2D` (physics engine extra)."


def have_box2d() -> bool:
    """Whether the Box2D bindings can be imported."""
    try:
        import Box2D  # noqa: F401
        return True
    except Exception:
        return False


def _require_box2d():
    try:
        import Box2D
        return Box2D
    except Exception as exc:  # pragma: no cover - exercised only without Box2D
        raise RuntimeError(_INSTALL_HINT) from exc


def tile_center(cell: Tuple[int, int]) -> Vec:
    """Continuous center of a grid cell (grid coords double as world meters)."""
    return (cell[0] + 0.5, cell[1] + 0.5)


class PhysicsWorld:
    """A live Box2D world built from a scene graph, with the game mechanics wired.

    Mechanics mirror :class:`envgen.env.GridEnv`: touching a Key collects it,
    bumping a locked Door while holding its key opens (removes) it, the Exit is a
    sensor. State surface: ``player_pos`` (continuous), ``player_cell``,
    ``inventory``, ``opened``, ``objective_met``.
    """

    def __init__(self, scene: SceneGraph) -> None:
        b2 = _require_box2d()
        self.scene = scene
        self.inventory: set = set()
        self.opened: set = set()
        self._pending_open: List[object] = []   # door bodies to destroy after Step
        self._collected_now: List[str] = []     # key ids touched during a Step

        self.world = b2.b2World(gravity=(0, 0), doSleep=True)
        self._build_static(b2)
        self._build_objects(b2)
        self._build_player(b2)
        self.world.contactListener = _Contacts(self)

    # -- construction -------------------------------------------------------
    def _build_static(self, b2) -> None:
        """One static box per wall tile (grids are small; simple wins)."""
        grid = self.scene.grid
        for y in range(grid.h):
            for x in range(grid.w):
                if grid.tiles[y][x] == 1:
                    body = self.world.CreateStaticBody(position=tile_center((x, y)))
                    body.CreatePolygonFixture(box=(0.5, 0.5), friction=0.2)
                    body.userData = ("wall", f"{x},{y}")

    def _build_objects(self, b2) -> None:
        self._door_bodies: dict = {}
        for o in self.scene.objects:
            if o.type is EntityType.PLAYER:
                continue
            body = self.world.CreateStaticBody(position=tile_center(o.pos))
            body.userData = (o.type.value, o.id)
            if o.type is EntityType.TABLE:
                body.CreatePolygonFixture(box=(0.45, 0.45), friction=0.2)
            elif o.type is EntityType.DOOR and o.locked:
                body.CreatePolygonFixture(box=(0.5, 0.5), friction=0.2)
                self._door_bodies[o.id] = body
            else:  # Key, Exit, unlocked Door — sensors: detected, never blocking
                fixture = body.CreatePolygonFixture(box=(0.4, 0.4))
                fixture.sensor = True

    def _build_player(self, b2) -> None:
        player = self.scene.player
        if player is None:
            raise ValueError("scene has no Player")
        self.player = self.world.CreateDynamicBody(
            position=tile_center(player.pos), fixedRotation=True, linearDamping=5.0
        )
        fixture = self.player.CreateCircleFixture(
            radius=PLAYER_RADIUS, density=1.0, friction=0.2
        )
        fixture.userData = ("player", player.id)
        self.player.userData = ("player", player.id)

    # -- state --------------------------------------------------------------
    @property
    def player_pos(self) -> Vec:
        p = self.player.position
        return (p.x, p.y)

    @property
    def player_cell(self) -> Tuple[int, int]:
        return (int(self.player_pos[0]), int(self.player_pos[1]))

    @property
    def objective_met(self) -> bool:
        """The typed objective, judged on the physical state (cell + inventory)."""
        return satisfied(self.scene, self.player_cell, frozenset(self.inventory))

    # -- stepping -----------------------------------------------------------
    def step(self, velocity: Vec = (0.0, 0.0)) -> None:
        """Advance one physics tick with the player under velocity control."""
        self.player.linearVelocity = velocity
        self.world.Step(DT, *_ITERS)
        # Box2D forbids destroying bodies inside callbacks; flush the queue here.
        for body in self._pending_open:
            self.world.DestroyBody(body)
        self._pending_open.clear()

    # -- contact effects (called by the listener) ----------------------------
    def _touch(self, kind: str, obj_id: str) -> None:
        if kind == "Key" and obj_id not in self.inventory:
            self.inventory.add(obj_id)
        elif kind == "Door":
            self._try_open(obj_id)

    def _try_open(self, door_id: str) -> None:
        door = self.scene.get(door_id)
        if door is None or door_id in self.opened:
            return
        holds_key = any(
            (k := self.scene.get(kid)) is not None and k.opens == door_id
            for kid in self.inventory
        )
        if holds_key:
            self.opened.add(door_id)
            body = self._door_bodies.pop(door_id, None)
            if body is not None:
                self._pending_open.append(body)


def _make_contacts_class():
    """Build the listener class lazily (its base class lives inside Box2D)."""
    b2 = _require_box2d()

    class Contacts(b2.b2ContactListener):
        def __init__(self, pw: PhysicsWorld) -> None:
            super().__init__()
            self.pw = pw

        def BeginContact(self, contact) -> None:
            a = contact.fixtureA.body.userData
            b = contact.fixtureB.body.userData
            for me, other in ((a, b), (b, a)):
                if me and me[0] == "player" and other and other[0] != "wall":
                    self.pw._touch(other[0], other[1])

    return Contacts


def _Contacts(pw: PhysicsWorld):
    return _make_contacts_class()(pw)


# --- executing the proven plan in physics --------------------------------------
@dataclass
class PhysicsResult:
    """Outcome of driving the grid plan through the Box2D world."""

    solved: bool
    steps: int = 0
    trace: List[Vec] = field(default_factory=list)   # player position per tick
    reason: str = ""


def run_plan(
    scene: SceneGraph,
    path: Optional[List[Tuple[int, int]]] = None,
    *,
    max_seconds: float = 60.0,
    record_trace: bool = True,
) -> PhysicsResult:
    """Steer the physics body along the (proven) grid path; judge the objective.

    ``path`` defaults to the objective-aware plan from
    :func:`envgen.objective_solve.solve_objective`. The controller drives waypoint to
    waypoint at tile centers; Box2D handles all collision. Solved = the typed
    objective holds on the physical end-state within the time budget.
    """
    if path is None:
        from envgen.objective_solve import solve_objective

        plan = solve_objective(scene)
        if not plan.solved:
            return PhysicsResult(False, reason=f"no plan: {plan.reason}")
        path = plan.path

    pw = PhysicsWorld(scene)
    waypoints = [tile_center(c) for c in path]
    trace: List[Vec] = []
    budget = int(max_seconds / DT)
    wp = 0
    for tick in range(budget):
        if record_trace:
            trace.append(pw.player_pos)
        while wp < len(waypoints) and _dist(pw.player_pos, waypoints[wp]) < WAYPOINT_TOL:
            wp += 1
        if wp >= len(waypoints):
            if pw.objective_met:
                return PhysicsResult(True, tick, trace,
                                     f"objective met in {tick} physics ticks")
            return PhysicsResult(False, tick, trace,
                                 "path completed but objective unmet")
        pw.step(_steer(pw.player_pos, waypoints[wp]))
        if pw.objective_met and wp >= len(waypoints) - 1:
            return PhysicsResult(True, tick + 1, trace,
                                 f"objective met in {tick + 1} physics ticks")
    return PhysicsResult(False, budget, trace, "physics time budget exhausted")


def _dist(a: Vec, b: Vec) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _steer(pos: Vec, target: Vec) -> Vec:
    dx, dy = target[0] - pos[0], target[1] - pos[1]
    d = (dx * dx + dy * dy) ** 0.5
    if d < 1e-6:
        return (0.0, 0.0)
    return (dx / d * PLAYER_SPEED, dy / d * PLAYER_SPEED)
