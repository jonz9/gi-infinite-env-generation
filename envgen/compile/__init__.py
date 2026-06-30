"""NL→edit-ops compiler subsystem (Stage 3).

Frozen surface: the :data:`Complete` seam type and :class:`CompileResult` in
:mod:`envgen.compile.base`. Concrete compiler, parser, repair loop, reference
resolver, and prompts are added by Stage 3 tickets as their own modules and imported
directly by consumers — this file stays frozen.
"""
from envgen.compile.base import CompileResult, Complete

__all__ = ["CompileResult", "Complete"]
