"""Auto-imports every biome module so each self-registers.

⚠️ FROZEN FILE. Do not edit as part of a ticket. Add a biome by dropping a
``<name>.py`` module here that calls ``register_biome(Biome(...))`` at import time.
No other import-time side effects. See ``tickets/README.md``.
"""
from __future__ import annotations

import importlib
import pkgutil

for _module in pkgutil.iter_modules(__path__):
    importlib.import_module(f"{__name__}.{_module.name}")
