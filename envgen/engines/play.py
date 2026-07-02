"""Play a scene in the physics engine — pygame window or headless PNG frames.

The primary way to *see* an environment: build the Box2D world, drive the proven
plan through it, and render the continuous state (the player is a circle at its
real float position, collected keys vanish, opened doors disappear) either live in
a pygame window or as numbered PNGs. Interactive mode hands the controls to a human
(arrow keys / WASD apply velocity to the physics body) with the typed objective
checked live — the same world the agent's controller drives.

Everything imports lazily: without pygame you still get headless frames; without
Box2D you get an actionable install hint. Entrypoint:

    python3 -m envgen.engines.play scene.json                 # window playback
    python3 -m envgen.engines.play scene.json --headless dir/ # PNGs, no window
    python3 -m envgen.engines.play scene.json --interactive   # you drive
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from envgen.pixels import CELL, PALETTE, Frame, frame_size, save_png, to_png_bytes
from envgen.schema import EntityType, SceneGraph

_FRAME_EVERY = 4     # capture every Nth physics tick headless (60Hz -> 15fps)


# --- continuous rasterizer ------------------------------------------------------
def render_physics_frame(pw, cell: int = CELL) -> Frame:
    """Rasterize the live physics world (continuous player position) to a frame."""
    scene = pw.scene
    w, h = scene.grid.w, scene.grid.h
    rows: Frame = [bytearray(w * cell * 3) for _ in range(h * cell)]

    def block(gx: int, gy: int, color, inset: int = 0) -> None:
        r, g, b = color
        for py in range(gy * cell + inset, gy * cell + cell - inset):
            row = rows[py]
            for i in range((gx * cell + inset) * 3, (gx * cell + cell - inset) * 3, 3):
                row[i], row[i + 1], row[i + 2] = r, g, b

    for gy in range(h):
        for gx in range(w):
            block(gx, gy, PALETTE["wall"] if scene.grid.is_wall(gx, gy) else PALETTE["floor"])

    for o in scene.objects:
        if o.type is EntityType.PLAYER:
            continue
        if o.type is EntityType.KEY and o.id in pw.inventory:
            continue                                   # collected
        if o.type is EntityType.DOOR and o.id in pw.opened:
            block(*o.pos, PALETTE["Door_open"], inset=max(1, cell // 3))
            continue
        color = PALETTE.get(
            "Door_locked" if o.type is EntityType.DOOR else o.type.value, (200, 60, 200)
        )
        block(*o.pos, color, inset=max(1, cell // 5))

    _circle(rows, pw.player_pos, 0.35, PALETTE["Player"], cell, w, h)
    return rows


def _circle(rows: Frame, center, radius: float, color, cell: int, w: int, h: int) -> None:
    """Fill a circle at a continuous world position (meters -> pixels)."""
    r, g, b = color
    cx, cy, pr = center[0] * cell, center[1] * cell, radius * cell
    for py in range(max(0, int(cy - pr)), min(h * cell, int(cy + pr) + 1)):
        row = rows[py]
        for px in range(max(0, int(cx - pr)), min(w * cell, int(cx + pr) + 1)):
            if (px - cx) ** 2 + (py - cy) ** 2 <= pr * pr:
                i = px * 3
                row[i], row[i + 1], row[i + 2] = r, g, b


# --- headless: physics rollout -> PNGs ------------------------------------------
def run_headless(
    scene: SceneGraph, outdir: str, *, every: int = _FRAME_EVERY,
    path: Optional[List[Tuple[int, int]]] = None,
):
    """Drive the plan through Box2D and write every Nth tick as a PNG."""
    import os

    from envgen.engines.box2d_engine import run_plan

    os.makedirs(outdir, exist_ok=True)
    frames: List[str] = []

    def capture(pw, tick: int) -> None:
        if tick % every == 0:
            p = os.path.join(outdir, f"frame_{len(frames):04d}.png")
            save_png(p, render_physics_frame(pw))
            frames.append(p)

    result = run_plan(scene, path=path, on_tick=capture, record_trace=False)
    return result, frames


# --- pygame: live window ---------------------------------------------------------
def play(scene: SceneGraph, *, fps: int = 60) -> "object":  # pragma: no cover - needs display
    """Watch the physics controller drive the proven plan, live."""
    import pygame

    from envgen.engines.box2d_engine import run_plan
    from envgen.pygame_view import frame_to_surface

    pygame.init()
    screen = clock = None

    def show(pw, tick: int) -> None:
        nonlocal screen, clock
        frame = render_physics_frame(pw)
        if screen is None:
            screen = pygame.display.set_mode(frame_size(frame))
            pygame.display.set_caption("gi-env-gen — physics playback")
            clock = pygame.time.Clock()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                raise KeyboardInterrupt
        screen.blit(frame_to_surface(frame, pygame), (0, 0))
        pygame.display.flip()
        clock.tick(fps)

    try:
        result = run_plan(scene, on_tick=show, record_trace=False)
    except KeyboardInterrupt:
        pygame.quit()
        return None
    pygame.quit()
    return result


def interactive(scene: SceneGraph, *, fps: int = 60) -> None:  # pragma: no cover - needs display
    """You drive: arrows/WASD apply velocity to the physics body."""
    import pygame

    from envgen.engines.box2d_engine import PLAYER_SPEED, PhysicsWorld
    from envgen.pygame_view import frame_to_surface

    keymap = {
        pygame.K_UP: (0, -1), pygame.K_w: (0, -1),
        pygame.K_DOWN: (0, 1), pygame.K_s: (0, 1),
        pygame.K_LEFT: (-1, 0), pygame.K_a: (-1, 0),
        pygame.K_RIGHT: (1, 0), pygame.K_d: (1, 0),
    }
    pw = PhysicsWorld(scene)
    pygame.init()
    frame = render_physics_frame(pw)
    screen = pygame.display.set_mode(frame_size(frame))
    clock = pygame.time.Clock()
    running, done = True, False
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
        pressed = pygame.key.get_pressed()
        vx = sum(d[0] for k, d in keymap.items() if pressed[k])
        vy = sum(d[1] for k, d in keymap.items() if pressed[k])
        norm = (vx * vx + vy * vy) ** 0.5 or 1.0
        pw.step((vx / norm * PLAYER_SPEED, vy / norm * PLAYER_SPEED))
        if pw.objective_met and not done:
            done = True
        pygame.display.set_caption(
            "gi-env-gen — OBJECTIVE COMPLETE" if done
            else "gi-env-gen — arrows/WASD; reach the objective"
        )
        screen.blit(frame_to_surface(render_physics_frame(pw), pygame), (0, 0))
        pygame.display.flip()
        clock.tick(fps)
    pygame.quit()


def _main(argv: List[str]) -> int:  # pragma: no cover - manual entrypoint
    from envgen.objective import objective_from_scene

    if not argv:
        print("usage: python3 -m envgen.engines.play <scene.json> "
              "[--headless <dir>] [--interactive]")
        return 2
    scene = SceneGraph.from_json(open(argv[0], encoding="utf-8").read())
    print(f"objective: {objective_from_scene(scene).describe()}")

    if "--interactive" in argv:
        interactive(scene)
        return 0
    if "--headless" in argv:
        outdir = argv[argv.index("--headless") + 1]
        result, frames = run_headless(scene, outdir)
        print("PHYSICS SOLVED" if result.solved else "PHYSICS FAILED", "—", result.reason)
        print(f"wrote {len(frames)} frame(s) to {outdir}/")
        return 0 if result.solved else 1
    result = play(scene)
    if result is not None:
        print("PHYSICS SOLVED" if result.solved else "PHYSICS FAILED", "—", result.reason)
        return 0 if result.solved else 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    import sys

    raise SystemExit(_main(sys.argv[1:]))
