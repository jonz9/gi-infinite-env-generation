"""Interactive REPL driver for a :class:`HarnessSession` (ticket S2-T10).

``python harness.py [scene.json]`` opens a read-eval-print loop over a live,
self-healing world. Each input line is one of:

* a **typed command** in the Stage-2 DSL (see :mod:`envgen.session.commands`),
  e.g. ``add key at 2,5 opens door1`` or ``move player to 1,1``;
* a **raw op-JSON** dict, e.g. ``{"op": "MoveObject", "id": "player", "to": [1, 1]}``;
* a **meta-command** beginning with ``:`` — ``:save <f>``, ``:load <f>``,
  ``:undo``, ``:redo``, ``:replay``, ``:objective``, ``:frame <f>``,
  ``:frames <dir>``, ``:help``, ``:quit``.

A command/op line is compiled to an :class:`~envgen.edit.base.EditOp`, applied via
:meth:`HarnessSession.step`, and the resulting render + ``SOLVED``/``FAILED`` verdict
(plus any rejection reason) is printed. Because ``step`` is atomic, a rejected edit
leaves the world untouched — the REPL just reports why.

Meta-commands wire to the sibling Stage-2 modules (:mod:`envgen.session.persist`,
``envgen.session.history``, :mod:`envgen.session.replay`) via a **lazy import inside
the handler**, so a missing/unfinished sibling degrades to a polite "not available"
rather than crashing the loop. :func:`main` reads from an injectable line source so it
is fully testable without a live TTY. ``run.py`` (the one-shot path) is untouched.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional, TextIO

from envgen.edit import clone_scene, op_from_dict
from envgen.render import render_scene
from envgen.schema import SceneGraph
from envgen.session.commands import CommandError, parse_command
from envgen.session.core import HarnessSession

#: Scene loaded when no path is given on the command line.
DEFAULT_SCENE = Path(__file__).resolve().parent / "examples" / "room_key_door.json"

_HELP = """\
commands:
  <dsl>                a typed command, e.g. 'add key at 2,5 opens door1',
                       'move player to 1,1', 'carve 2,5 floor', 'goal reach exit'
  {"op": ...}          a raw op-JSON dict
meta-commands:
  :save <file>         persist the session (seed + scene + op-log) to <file>
  :load <file>         replace the session with one loaded from <file>
  :undo                undo the last accepted edit (if history is available)
  :redo                redo the last undone edit (if history is available)
  :replay              verify the op-log replays to the live scene hash-for-hash
  :objective           show the live typed objective (set it via 'goal <json>')
  :frame <file.png>    render the live world to one PNG frame
  :frames <dir>        solve the live world; write one PNG per step to <dir>
  :help                show this help
  :quit                leave the REPL"""


class Harness:
    """REPL state: a live session plus where to write output.

    The session can be swapped wholesale by ``:load``/``:undo``/``:redo``; the
    initial scene snapshot is kept so ``:replay`` has the pre-edit world to fold the
    op-log over (the core does not retain it).
    """

    def __init__(self, scene: SceneGraph, *, out: Optional[TextIO] = None) -> None:
        self.session = HarnessSession(scene)
        self._initial: Optional[SceneGraph] = clone_scene(scene)
        self.out: TextIO = out if out is not None else sys.stdout

    # -- output ------------------------------------------------------------
    def emit(self, text: str = "") -> None:
        """Print one line to the configured output stream."""
        print(text, file=self.out)

    # -- main loop ---------------------------------------------------------
    def run(self, lines: Iterable[str], *, prompt: bool = False) -> int:
        """Consume ``lines`` until exhausted or ``:quit``. Returns an exit code."""
        for raw in lines:
            if prompt:
                print("> ", end="", file=self.out, flush=True)
            line = raw.rstrip("\n")
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith(":"):
                if self._meta(stripped):
                    return 0  # :quit
                continue
            self._edit(stripped)
        return 0

    # -- edit lines --------------------------------------------------------
    def _edit(self, line: str) -> None:
        """Compile one command/op-JSON line and step the session with it."""
        op_dict = self._compile(line)
        if op_dict is None:
            return
        try:
            op = op_from_dict(op_dict)
        except Exception as exc:  # malformed/unknown op shape
            self.emit(f"bad op: {exc}")
            return
        transcript = self.session.step([op])
        self._report(transcript)

    def _compile(self, line: str) -> Optional[dict[str, Any]]:
        """Parse a line as a DSL command, falling back to raw op-JSON."""
        try:
            return parse_command(line)
        except CommandError as cmd_exc:
            if line.lstrip().startswith("{"):
                try:
                    data = json.loads(line)
                except json.JSONDecodeError as json_exc:
                    self.emit(f"parse error: invalid op-JSON: {json_exc}")
                    return None
                if not isinstance(data, dict):
                    self.emit("parse error: op-JSON must be an object")
                    return None
                return data
            self.emit(f"parse error: {cmd_exc}")
            return None

    def _report(self, transcript: Any) -> None:
        """Print the post-step render and the SOLVED/FAILED verdict."""
        self.emit(transcript.render_after)
        if transcript.applied:
            verdict = "SOLVED" if transcript.solved else "FAILED"
            self.emit(f"{verdict}: applied {len(transcript.applied)} op(s)")
        else:
            reason = "; ".join(transcript.errors) or "rejected"
            self.emit(f"FAILED: {reason}")

    # -- meta-commands -----------------------------------------------------
    def _meta(self, line: str) -> bool:
        """Dispatch a ``:`` meta-command. Returns True iff the loop should stop."""
        parts = line.split(maxsplit=1)
        name = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""
        if name in (":quit", ":q", ":exit"):
            self.emit("bye")
            return True
        if name in (":help", ":h", ":?"):
            self.emit(_HELP)
        elif name == ":save":
            self._save(arg)
        elif name == ":load":
            self._load(arg)
        elif name == ":undo":
            self._history("undo")
        elif name == ":redo":
            self._history("redo")
        elif name == ":replay":
            self._replay()
        elif name == ":objective":
            self._objective()
        elif name == ":frame":
            self._frame(arg)
        elif name == ":frames":
            self._frames(arg)
        else:
            self.emit(f"unknown meta-command {name!r}; try :help")
        return False

    def _save(self, arg: str) -> None:
        if not arg:
            self.emit("usage: :save <file>")
            return
        try:
            from envgen.session import persist
        except Exception:
            self.emit(":save not available")
            return
        try:
            Path(arg).write_text(persist.save(self.session), encoding="utf-8")
        except Exception as exc:
            self.emit(f":save failed: {exc}")
            return
        self.emit(f"saved session to {arg}")

    def _load(self, arg: str) -> None:
        if not arg:
            self.emit("usage: :load <file>")
            return
        try:
            from envgen.session import persist
        except Exception:
            self.emit(":load not available")
            return
        try:
            self.session = persist.load(Path(arg).read_text(encoding="utf-8"))
        except Exception as exc:
            self.emit(f":load failed: {exc}")
            return
        # The persisted form keeps only the final scene, not the pre-edit world, so
        # :replay can't fold the log afterwards without it.
        self._initial = getattr(self.session, "initial_scene", None)
        self.emit(f"loaded session from {arg}")
        self.emit(render_scene(self.session.scene))

    def _history(self, direction: str) -> None:
        """Wire ``:undo``/``:redo`` to ``envgen.session.history`` if present."""
        try:
            from envgen.session import history  # type: ignore
        except Exception:
            self.emit(f":{direction} not available")
            return
        fn = getattr(history, direction, None)
        if fn is None:
            self.emit(f":{direction} not available")
            return
        try:
            result = fn(self.session)
        except Exception as exc:
            self.emit(f":{direction} failed: {exc}")
            return
        if isinstance(result, HarnessSession):
            self.session = result  # functional style returns a new session
        self.emit(render_scene(self.session.scene))
        self.emit(f"{direction} ok")

    def _objective(self) -> None:
        """Print the live typed objective (and the raw goal it parsed from)."""
        from envgen.objective import objective_from_scene

        scene = self.session.scene
        self.emit(f"objective: {objective_from_scene(scene).describe()}")
        self.emit(f"goal: {scene.goal}")
        self.emit("status: SOLVED" if self.session.solved else "status: NOT satisfiable")

    def _frame(self, arg: str) -> None:
        """Render the live world to a single PNG frame."""
        if not arg:
            self.emit("usage: :frame <file.png>")
            return
        from envgen.pixels import frame_size, render_scene as render_frame, save_png

        try:
            frame = render_frame(self.session.scene)
            save_png(arg, frame)
        except Exception as exc:
            self.emit(f":frame failed: {exc}")
            return
        w, h = frame_size(frame)
        self.emit(f"wrote {arg} ({w}x{h}px)")

    def _frames(self, arg: str) -> None:
        """Solve the live world and write the trajectory as PNG frames."""
        if not arg:
            self.emit("usage: :frames <dir>")
            return
        from envgen.objective_solve import solve_objective
        from envgen.pixels import render_trajectory, save_trajectory

        result = solve_objective(self.session.scene)
        if not result.solved:
            self.emit(f":frames failed: {result.reason}")
            return
        try:
            paths = save_trajectory(arg, render_trajectory(self.session.scene, result.actions))
        except Exception as exc:
            self.emit(f":frames failed: {exc}")
            return
        self.emit(f"wrote {len(paths)} frame(s) to {arg} — {result.reason}")

    def _replay(self) -> None:
        """Verify the op-log replays to the live scene via ``envgen.session.replay``."""
        try:
            from envgen.session import replay
        except Exception:
            self.emit(":replay not available")
            return
        try:
            check = replay.check_replay(self.session, initial=self._initial)
        except Exception as exc:
            self.emit(f":replay failed: {exc}")
            return
        if check.ok:
            self.emit(f"replay OK: {check.detail}")
        else:
            self.emit(f"replay DIVERGED at #{check.diverged_at}: {check.detail}")


def _stdin_lines(stream: TextIO) -> Iterator[str]:
    """Yield lines from ``stream`` one at a time (lazy, so it works on a live TTY)."""
    for line in stream:
        yield line


def main(
    argv: Optional[list[str]] = None,
    *,
    lines: Optional[Iterable[str]] = None,
    inp: Optional[TextIO] = None,
    out: Optional[TextIO] = None,
) -> int:
    """Entry point. ``argv`` is ``sys.argv[1:]`` (an optional scene path).

    Input comes from ``lines`` (any iterable of strings) when given — the testable
    path — else from ``inp``/``stdin``. Output goes to ``out`` (default stdout).
    """
    argv = list(argv) if argv is not None else sys.argv[1:]
    out = out if out is not None else sys.stdout

    path = Path(argv[0]) if argv else DEFAULT_SCENE
    try:
        scene = SceneGraph.from_json(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"could not load scene {path}: {exc}", file=out)
        return 2

    from envgen.objective import objective_from_scene

    driver = Harness(scene, out=out)
    print(f"loaded {path} — objective: {objective_from_scene(scene).describe()}", file=out)
    print(render_scene(scene), file=out)
    print("type :help for commands", file=out)

    if lines is not None:
        source: Iterable[str] = lines
        interactive = False
    else:
        source = _stdin_lines(inp if inp is not None else sys.stdin)
        interactive = bool(getattr(out, "isatty", lambda: False)())
    return driver.run(source, prompt=interactive)


if __name__ == "__main__":  # pragma: no cover - thin CLI wrapper
    raise SystemExit(main(sys.argv[1:]))
