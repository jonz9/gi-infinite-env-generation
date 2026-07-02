"""Optional PyGame window — a live/interactive view over the pixel frames.

Strictly optional and off the default path: the dependency-free PNG renderer
(:mod:`envgen.pixels`) is what feeds a policy / reward model. This adds a human-facing
window for demos — play back the solver's trajectory, or drive the agent yourself with
the arrow keys (the grid analogue of the policy's move actions) while the typed
objective is checked live at the code level.

PyGame is imported lazily and never required to import this module: :func:`have_pygame`
reports availability and the window functions raise a clear, actionable error if it is
absent, so the rest of the harness (and the test suite) is unaffected.
"""
from __future__ import annotations

from envgen.pixels import CELL, Frame, frame_size, render_world
from envgen.schema import SceneGraph

_INSTALL_HINT = "PyGame not installed; run `pip install pygame` (optional viewer only)."


def have_pygame() -> bool:
    """Whether PyGame can be imported (the viewer is a no-op extra without it)."""
    try:
        import pygame  # noqa: F401
        return True
    except Exception:
        return False


def _require_pygame():
    try:
        import pygame
        return pygame
    except Exception as exc:  # pragma: no cover - exercised only without pygame
        raise RuntimeError(_INSTALL_HINT) from exc


def frame_to_surface(frame: Frame, pygame):
    """Convert a pixel :data:`~envgen.pixels.Frame` to a PyGame ``Surface``."""
    w, h = frame_size(frame)
    data = b"".join(bytes(row) for row in frame)
    return pygame.image.frombuffer(data, (w, h), "RGB")


def play(scene: SceneGraph, *, fps: int = 6, cell: int = CELL) -> None:  # pragma: no cover
    """Open a window and animate the BFS solver's trajectory to the goal."""
    from envgen.pixels import render_trajectory
    from envgen.solve import solve

    pygame = _require_pygame()
    result = solve(scene)
    frames = render_trajectory(scene, result.actions, cell) if result.solved else [
        render_world(_fresh_world(scene), cell)
    ]
    w, h = frame_size(frames[0])
    pygame.init()
    screen = pygame.display.set_mode((w, h))
    pygame.display.set_caption("gi-env-gen — solver trajectory")
    clock = pygame.time.Clock()
    i, running = 0, True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
        screen.blit(frame_to_surface(frames[min(i, len(frames) - 1)], pygame), (0, 0))
        pygame.display.flip()
        i = (i + 1) % (len(frames) + fps)   # brief pause on the final frame, then loop
        clock.tick(fps)
    pygame.quit()


def interactive(scene: SceneGraph, *, cell: int = CELL) -> None:  # pragma: no cover
    """Drive the agent with the arrow keys; the typed objective is checked live."""
    from envgen.env import Action, GridEnv
    from envgen.objective import satisfied

    pygame = _require_pygame()
    keymap = {
        pygame.K_UP: Action.UP, pygame.K_DOWN: Action.DOWN,
        pygame.K_LEFT: Action.LEFT, pygame.K_RIGHT: Action.RIGHT,
    }
    env = GridEnv(scene)
    env.reset()
    frame = render_world(env.world, cell)
    w, h = frame_size(frame)
    pygame.init()
    screen = pygame.display.set_mode((w, h))
    pygame.display.set_caption("gi-env-gen — arrow keys; reach the objective")
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key in keymap:
                env.step(keymap[event.key])
                if satisfied(scene, env.world.player_pos, frozenset(env.world.inventory)):
                    pygame.display.set_caption("gi-env-gen — OBJECTIVE COMPLETE")
        screen.blit(frame_to_surface(render_world(env.world, cell), pygame), (0, 0))
        pygame.display.flip()
    pygame.quit()


def _fresh_world(scene: SceneGraph):
    from envgen.world import World

    return World.from_scene(scene)


def _main(argv: list[str]) -> int:  # pragma: no cover - manual entrypoint
    """``python3 -m envgen.pygame_view <scene.json> [--play|--interactive]``."""
    if not argv:
        print("usage: python3 -m envgen.pygame_view <scene.json> [--play|--interactive]")
        return 2
    if not have_pygame():
        print(_INSTALL_HINT)
        return 1
    scene = SceneGraph.from_json(open(argv[0], encoding="utf-8").read())
    mode = argv[1] if len(argv) > 1 else "--play"
    (interactive if mode == "--interactive" else play)(scene)
    return 0


if __name__ == "__main__":  # pragma: no cover
    import sys

    raise SystemExit(_main(sys.argv[1:]))
