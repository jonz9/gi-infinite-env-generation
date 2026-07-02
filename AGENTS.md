# AGENTS.md — how any agent drives this harness

This repo turns **natural-language intent** into **playable, provably-solvable 2D
environments** — and lets you keep changing and growing them while the proof holds.
It is host-agnostic and key-free: *you, the agent reading this* (Claude Code, Codex,
anything else) are the planner. There is no model SDK and no API key. You emit JSON
(scene graphs, edit ops, objectives); deterministic pure-stdlib Python validates,
renders, solves, and proves. **No code generation — JSON is the only handoff.**

## When the user asks for an environment

The user runs nothing and writes no JSON — you do everything:

1. **Author** a `scene.json` yourself from their words (schema below). Invent the
   layout; encode their win condition as a typed objective if it's richer than
   "reach the exit".
2. **Prove it:** run `python3 run.py scene.json`. If it fails, the error names the
   exact problem — fix the JSON and re-run until SOLVED. Never show the user a
   broken world or ask them to debug.
3. **Show it in the engine:** `python3 -m envgen.engines.play scene.json` opens a
   pygame window and drives the proven plan through the **Box2D physics world**
   (walls/doors are solid bodies; the lock is collision, not bookkeeping). Headless:
   `--headless frames/` writes the rollout as PNGs; `--interactive` lets the user
   drive with WASD. If the pygame/Box2D extras are missing, fall back to the
   stdlib PNG frames (`python3 -m envgen.pixels`) and the ASCII render.
4. **Change, don't regenerate:** follow-ups ("add a second key", "move the exit")
   are live edits — drive `harness.py` (or `HarnessSession.step`) on the *same*
   world so the op-log and determinism guarantees hold.
5. **"Make it bigger / endless"** → `InfiniteSession` + `Extend` (way 3 below).

## The three ways to drive it

### 1. One-shot: author a scene, prove it

1. Read the schema (`envgen/schema.py`; shape below) and, if useful, the
   level-designer brief in `prompts/planner_system.md`.
2. Write a `scene.json`.
3. Run:
   ```bash
   python3 run.py scene.json        # validate → render ASCII → BFS-solve → SOLVED/FAILED
   python3 -m envgen.pixels scene.json frames/   # same, but writes one PNG per solver step
   ```
   Exit 0 = SOLVED, 1 = FAILED, 2 = won't parse/validate. On failure the output
   names the exact problem (unreachable exit, key-behind-its-own-door, overlap,
   out-of-bounds…). Fix the JSON and re-run — you are the repair loop.

### 2. Live session: build and change a world that stays solvable

```bash
python3 harness.py [scene.json]     # REPL over a persistent, self-healing world
```

Each line is a typed command (`add key at 2,5 opens door1`, `move player to 1,1`,
`carve 4,4 floor`, `fill 2,2 5,5 wall`, `remove table1`, `setprop door1 locked true`,
`goal <text-or-json>`) **or** a raw op-JSON dict (`{"op": "MoveObject", "id":
"player", "to": [1, 1]}`). Every step is **atomic**: ops apply to a clone, the result
is re-validated and re-proved, and a step that would break the objective is rejected
with a reason — the world is never left broken. Meta-commands:

```
:objective            show the live typed objective + SOLVED status
:frame out.png        render the live world to one PNG
:frames dir/          prove the objective, write one PNG per step of the proof
:play [dir/]          execute the plan in the Box2D physics engine — pygame
                      window, or headless rollout PNGs into [dir]
:save f / :load f     persist / restore (seed + scene + op-log)
:undo / :redo         step history
:replay               verify seed + op-log reproduces the live scene hash-for-hash
```

Programmatic equivalents: `envgen.session.core.HarnessSession.step(ops)`, and
`envgen.compile.compile_edit(scene, "your command", complete=...)` to turn free NL
into ops (the `complete` seam is any text-completion callable — you, usually).

### 3. Infinite worlds: growing is just another edit

`envgen.worldgen.session_adapter.InfiniteSession` holds an unbounded world
(`world(seed, x, y) → tile`, lazily chunked, bounded memory). Macro ops
`Extend(direction, n, biome)` / `SetBiome(...)` grow and repaint it;
`session.window(x0, y0, w, h)` materializes any slice as a normal finite scene, so
everything above (ops, render, solve, frames) applies to the visible region.
Solvability is proved across chunks by lazy BFS (`worldgen.lazy_validate` /
`lazy_solve`), hazards routed around. Biomes/chunk-generators are registries
(`armory`, `flooded_crypt`, `swamp` / `flat`, `maze`, `caves`, `rooms`) — add one by
dropping a self-registering module, never by editing a central file.

## Scene graph shape (the IR)

```json
{
  "grid": { "w": 12, "h": 8, "tiles": [[1,1,1], [1,0,1], [1,1,1]] },
  "objects": [
    {"id": "player", "type": "Player", "pos": [1, 1]},
    {"id": "table1", "type": "Table",  "pos": [2, 2]},
    {"id": "key1",   "type": "Key",    "pos": [4, 6], "opens": "door1"},
    {"id": "door1",  "type": "Door",   "pos": [6, 3], "locked": true},
    {"id": "exit",   "type": "Exit",   "pos": [10, 6]}
  ],
  "goal": "reach exit"
}
```

- `pos` is `[x, y]`: `x` = column `0..w-1`, `y` = row `0..h-1`; tiles are
  `tiles[y][x]`, `1` = wall, `0` = floor; origin top-left.
- Types: `Player` (exactly one), `Table` (blocker), `Key` (`opens` → Door id),
  `Door` (`locked`), `Exit`. Extended kinds (Lava/Water/Ice hazards) live in the
  `envgen.entities` registry and are honored by the infinite-world proofs.
- Worked example: `examples/room_key_door.json`.

## Typed objectives (code-level win conditions)

`goal` also accepts a JSON predicate — this is what "code-level objectives" means:

```json
{"all": [{"pred": "has", "item": "key1"}, {"pred": "reach", "target": "exit"}]}
```

Predicates: `{"pred":"reach","target":<id>}` (stand on it), `{"pred":"has","item":
<id>}` (collected), `{"all":[…]}`, `{"any":[…]}`. The harness plans for the
*predicate* (detouring to collect `has` items), executes the plan on the real env,
and accepts only if the predicate holds on the end state. In a live session the
objective **is the invariant**: an edit that keeps the exit reachable but breaks the
objective is rejected. Plain-string goals mean `reach <exit>` (backward compatible).

## Edit ops (the verbs)

`AddObject · RemoveObject · MoveObject · CloneObject · SwapObjects · SetProp ·
SetGoal · Carve · FillRegion · AddWallLine · ConnectCorridor · StampRoom ·
ResizeGrid` — all pure, JSON-round-trip, invertible (exactly or via recorded
restore). Enumerate live: `python3 -c "from envgen.edit import registered_ops;
print(sorted(registered_ops()))"`. Macro verbs for infinite worlds: `Extend`,
`SetBiome`.

## Guarantees the harness gives you

- **Verification:** structural checks + BFS reachability + key-before-door +
  objective execution — every accepted state is *provably* winnable, never "looks ok".
- **Atomicity:** a bad edit is rejected with a specific reason; the world stands.
- **Determinism:** `seed + op-log` reproduces any world exactly (`:replay` checks it).
- **Physics execution:** the same scene runs as a Box2D rigid-body world
  (`envgen.engines`) — solid walls/doors/tables, sensor keys/exits, a waypoint
  controller driving the proven plan, the typed objective judged on the physical
  end-state. PyGame renders it live; headless PNG capture needs no display.
- **Rendering fallbacks:** dependency-free PNG frames (`envgen.pixels`) and ASCII
  (`envgen.render`) always work, even with no extras installed.
- **Deps:** the core (validate/prove/edit/render-PNG) is pure stdlib. Extras:
  `pip install pygame Box2D` for the physics engine + window, `pytest` for the
  suite (`python3 -m pytest -q`).

## What NOT to do

- Don't add a model SDK or API-key path — the agent is the planner.
- Don't generate or `exec` code for levels — emit JSON (scenes, ops, objectives).
- Don't verify by hand — run the harness; the proof is the product.
- Don't edit frozen contract files (`base.py`, `__init__.py`, Phase-0 modules) —
  extend via the registries (ops, kinds, biomes, chunkgens, metrics).
