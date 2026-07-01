"""Window -> SceneGraph materializer (Stage 4, ticket S4-T02).

Projects a bounded rectangle of an (infinite) :class:`~envgen.infinite.InfiniteWorld`
into a finite :class:`~envgen.schema.SceneGraph`, so the Stage-1 edit ops, the finite
renderer, validator and solver all apply to the *visible region*. This is the concrete
realization of the architecture's "finite scene = one-chunk world" unification: the
finite pipeline never learns the world is unbounded — it just sees a scene.

Coordinates are translated so the window's top-left ``(x0, y0)`` becomes local
``(0, 0)``. Deterministic: because the underlying chunks are seed-consistent, the same
``(world, x0, y0, w, h)`` always materializes the byte-identical scene (equal
``scene_hash``).
"""
from __future__ import annotations

from envgen.infinite import CHUNK, ChunkCoord, InfiniteWorld
from envgen.schema import Grid, SceneGraph, SceneObject


def _overlapping_chunks(x0: int, y0: int, w: int, h: int) -> list[ChunkCoord]:
    """Chunk coords whose cells can intersect the window rectangle."""
    cx0, cy0 = x0 // CHUNK, y0 // CHUNK
    cx1, cy1 = (x0 + w - 1) // CHUNK, (y0 + h - 1) // CHUNK
    return [(cx, cy) for cy in range(cy0, cy1 + 1) for cx in range(cx0, cx1 + 1)]


def _window_objects(
    world: InfiniteWorld, x0: int, y0: int, w: int, h: int
) -> list[SceneObject]:
    """Objects whose global pos lands inside the window, translated to local coords."""
    seen: set[str] = set()
    out: list[SceneObject] = []
    for cc in _overlapping_chunks(x0, y0, w, h):
        for o in world.chunk(cc).objects:
            gx, gy = o.pos
            if not (x0 <= gx < x0 + w and y0 <= gy < y0 + h):
                continue
            if o.id in seen:
                continue
            seen.add(o.id)
            out.append(
                SceneObject(
                    id=o.id, type=o.type, pos=(gx - x0, gy - y0),
                    opens=o.opens, locked=o.locked,
                )
            )
    # stable order -> stable scene hash, independent of chunk/gen iteration order
    out.sort(key=lambda o: (o.pos[1], o.pos[0], o.id))
    return out


def window(world: InfiniteWorld, x0: int, y0: int, w: int, h: int) -> SceneGraph:
    """Materialize the ``w`` x ``h`` rectangle at global ``(x0, y0)`` as a SceneGraph."""
    if w <= 0 or h <= 0:
        raise ValueError(f"window dimensions must be positive, got w={w} h={h}")
    tiles = [
        [1 if world.is_wall((x0 + lx, y0 + ly)) else 0 for lx in range(w)]
        for ly in range(h)
    ]
    return SceneGraph(
        grid=Grid(w=w, h=h, tiles=tiles),
        objects=_window_objects(world, x0, y0, w, h),
        goal=world.layout.goal,
    )
