"""NL→edit-ops compiler — frozen contracts (Stage 3).

⚠️ FROZEN FILE. Do not edit as part of a ticket. Defines the host-agnostic,
key-free seam that turns a natural-language command (against the *current* world)
into a list of edit-op dicts. The agent reading ``AGENTS.md`` IS the compiler; tests
inject a canned ``complete``. No vendor SDK, no API key — same discipline as the
existing :mod:`envgen.planner`. See ``tickets/README.md``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

# A text-completion seam: (system_prompt, user_prompt) -> raw model text.
# The host agent supplies this; a test injects a canned function. Key-free.
Complete = Callable[[str, str], str]


@dataclass(frozen=True)
class CompileResult:
    """The output of compiling one NL command against a world summary.

    ``ops`` are op dicts (each ``op_from_dict``-parseable). ``raw`` is the model text
    they were extracted from. ``notes`` carries clarifications / ambiguity flags.
    """

    ops: list[dict[str, Any]] = field(default_factory=list)
    raw: str = ""
    notes: str = ""
