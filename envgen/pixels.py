"""Pixel frame renderer — the harness speaking the vision policy's modality.

The brief's consumer is a *vision* policy that observes **rendered frames** and the
reward-model bridge pairs those frames with exact code rewards. This module rasterizes
a scene / live world to an RGB frame and writes a PNG — with **zero third-party
dependencies** (a tiny stdlib PNG encoder over ``zlib``), so ``python run`` renders
frames on any machine with no ``pip install`` friction. ``render_trajectory`` rolls the
BFS solver and emits one frame per step: the agent visibly maneuvering to the goal.

ASCII (``envgen.render``) stays the fast, text-only view; this is the pixel view that
feeds a policy / reward model. A frame is ``list[bytearray]`` (one RGB scanline per row);
:func:`to_ndarray` lifts it to a numpy ``(H, W, 3)`` array when numpy is available.
"""
from __future__ import annotations

import struct
import zlib
from typing import List

from envgen.schema import EntityType, SceneGraph
from envgen.world import Coord, World

Color = tuple[int, int, int]
Frame = List[bytearray]      # `height` scanlines, each `width*3` bytes (RGB)

CELL = 16                    # pixels per grid tile

PALETTE: dict[str, Color] = {
    "floor": (208, 206, 196),
    "wall": (44, 46, 58),
    "grid": (150, 148, 140),
    "Player": (48, 122, 220),
    "Key": (240, 200, 48),
    "Door_locked": (176, 92, 44),
    "Door_open": (120, 184, 120),
    "Exit": (64, 200, 96),
    "Table": (128, 96, 62),
}


# --- rasterizer ---------------------------------------------------------------
def render_world(world: World, cell: int = CELL) -> Frame:
    """Rasterize the live ``world`` (player/inventory/opened reflected) to a frame."""
    scene = world.scene
    w, h = scene.grid.w, scene.grid.h
    pw, ph = w * cell, h * cell
    rows: Frame = [bytearray(pw * 3) for _ in range(ph)]

    def block(gx: int, gy: int, color: Color, inset: int = 0) -> None:
        r, g, b = color
        for py in range(gy * cell + inset, gy * cell + cell - inset):
            row = rows[py]
            base = (gx * cell + inset) * 3
            for i in range(base, (gx * cell + cell - inset) * 3, 3):
                row[i], row[i + 1], row[i + 2] = r, g, b

    for gy in range(h):
        for gx in range(w):
            block(gx, gy, PALETTE["wall"] if scene.grid.is_wall(gx, gy) else PALETTE["floor"])

    for o in scene.objects:
        if o.type is EntityType.PLAYER:
            continue                                   # drawn last, at the live position
        if o.type is EntityType.KEY and o.id in world.inventory:
            continue                                   # collected keys disappear
        block(o.pos[0], o.pos[1], _object_color(o, world), inset=max(1, cell // 5))

    px, py = world.player_pos
    block(px, py, PALETTE["Player"], inset=max(1, cell // 4))
    return rows


def _object_color(o, world: World) -> Color:
    if o.type is EntityType.DOOR:
        opened = (o.id in world.opened) or (not o.locked)
        return PALETTE["Door_open" if opened else "Door_locked"]
    return PALETTE.get(o.type.value, (200, 60, 200))   # magenta = unhandled type


def render_scene(scene: SceneGraph, cell: int = CELL) -> Frame:
    """Rasterize a scene in its initial state."""
    return render_world(World.from_scene(scene), cell)


def frame_size(frame: Frame) -> tuple[int, int]:
    """``(width, height)`` in pixels."""
    return (len(frame[0]) // 3, len(frame)) if frame else (0, 0)


# --- solver rollout -> frame sequence -----------------------------------------
def render_trajectory(scene: SceneGraph, actions, cell: int = CELL) -> list[Frame]:
    """One frame per step of the solver's actions — the agent maneuvering to goal."""
    from envgen.env import GridEnv

    env = GridEnv(scene)
    env.reset()
    frames = [render_world(env.world, cell)]
    for action in actions:
        env.step(action)
        frames.append(render_world(env.world, cell))
    return frames


# --- PNG output (stdlib only) -------------------------------------------------
def to_png_bytes(frame: Frame) -> bytes:
    """Encode a frame as PNG bytes using only the standard library."""
    width, height = frame_size(frame)

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)   # 8-bit, RGB (color type 2)
    raw = b"".join(b"\x00" + bytes(row) for row in frame)         # filter byte 0 per scanline
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def save_png(path: str, frame: Frame) -> None:
    with open(path, "wb") as fh:
        fh.write(to_png_bytes(frame))


def save_trajectory(outdir: str, frames: list[Frame]) -> list[str]:
    """Write ``frame_000.png`` … to ``outdir``; returns the paths written."""
    import os

    os.makedirs(outdir, exist_ok=True)
    paths = []
    for i, frame in enumerate(frames):
        p = os.path.join(outdir, f"frame_{i:03d}.png")
        save_png(p, frame)
        paths.append(p)
    return paths


def to_ndarray(frame: Frame):
    """Lift a frame to a numpy ``(H, W, 3)`` uint8 array (numpy imported lazily)."""
    import numpy as np

    width, height = frame_size(frame)
    return np.frombuffer(b"".join(bytes(r) for r in frame), dtype=np.uint8).reshape(height, width, 3)


def _main(argv: list[str]) -> int:  # pragma: no cover - manual entrypoint
    """``python3 -m envgen.pixels <scene.json> [outdir]`` — render the solve to PNGs."""
    from envgen.objective import objective_from_scene
    from envgen.solve import solve

    if not argv:
        print("usage: python3 -m envgen.pixels <scene.json> [outdir]")
        return 2
    scene = SceneGraph.from_json(open(argv[0], encoding="utf-8").read())
    outdir = argv[1] if len(argv) > 1 else "frames"
    print(f"objective: {objective_from_scene(scene).describe()}")

    result = solve(scene)
    frames = render_trajectory(scene, result.actions) if result.solved else [render_scene(scene)]
    paths = save_trajectory(outdir, frames)
    w, h = frame_size(frames[0])
    print("SOLVED" if result.solved else "FAILED")
    print(f"wrote {len(paths)} frame(s) at {w}x{h}px to {outdir}/ ({paths[0]} … {paths[-1]})")
    return 0 if result.solved else 1


if __name__ == "__main__":  # pragma: no cover
    import sys

    raise SystemExit(_main(sys.argv[1:]))
