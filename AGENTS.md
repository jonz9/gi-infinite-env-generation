# AGENTS.md — how any agent runs this repo

This repo turns **natural language** into a **playable 2D grid environment** and
**proves it solvable**. It is host-agnostic and key-free: *you, the agent reading
this* (Claude Code, Codex, or anything else), are the harness. There is no model
SDK and no API key. You emit JSON (scene graphs / edit ops); deterministic Python
validates, renders, and solves.

## Where this is going

The end goal is **not** a one-shot level generator. It is an **infinitely
generating + changing harness**: a persistent session where you grow and mutate an
unbounded, provably-solvable world through a *stream* of natural-language commands.
Natural language compiles to a closed **edit algebra** (typed ops like `AddObject`,
`MoveObject`, `Carve`, `Extend`, `SetGoal`) applied to a living world state, with
solvability kept as an invariant across every edit. "Generate more world" is just
the `Extend` op. **Build toward that.** The one-shot scene flow below is Phase 0, the
verified substrate the harness is built on.

## To generate an environment from a prompt

1. **Read the schema** in `envgen/schema.py` and the level-designer brief in
   `prompts/planner_system.md`. The scene graph is the only handoff — JSON in, no
   code generation.
2. **Write a scene graph** to `scene.json` matching the schema (shape below).
3. **Run it:**
   ```bash
   python run.py scene.json
   ```
   This validates → renders ASCII → runs the BFS solver → prints `SOLVED` or
   `FAILED`. Exit code 0 = SOLVED, 1 = FAILED, 2 = won't parse/validate.
4. **If validation fails**, the output lists the exact problems (unreachable exit,
   key-behind-its-own-door, overlaps, out-of-bounds, …). Fix `scene.json` and
   re-run. That is the repair loop, done by you.

## Run with no LLM at all (determinism check)

```bash
python run.py                 # runs the bundled worked example, zero setup
python -m pytest -q           # full offline test suite
```

The whole engine (validate / render / solve) is pure standard library — the
correctness of the harness never depends on any agent or key.

## Scene graph shape

```json
{
  "grid": {
    "w": 12,
    "h": 8,
    "tiles": [[1,1,1,...], [1,0,0,...], ...]
  },
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

- **Coordinates:** `pos` is `[x, y]`; `x` = column `0..w-1`, `y` = row `0..h-1`.
  The tile layer is `tiles[y][x]`. Origin `(0,0)` is top-left.
- **Tiles:** `1` = wall (blocking), `0` = floor (walkable).
- **Object types:** `Player` (exactly one), `Table` (static blocker), `Key`
  (`opens` → a Door id), `Door` (`locked: true|false`), `Exit` (the goal).
- **Solvability rules the validator enforces:** the Exit must be reachable; every
  Key must be reachable *before* its locked door opens (no key locked behind its
  own door); objects in-bounds and not overlapping incompatibly.

See `examples/room_key_door.json` for a complete worked example.

## What NOT to do

- Don't add a model SDK or an API-key code path — the agent is the planner.
- Don't generate or `exec` Python for levels — emit the JSON scene graph only.
- Don't validate/render/solve by hand — run `python run.py`; that is the harness.

For the full design rationale, see `README.md`.
