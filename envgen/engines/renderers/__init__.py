"""Auto-imports every renderer module so each self-registers.

⚠️ FROZEN FILE. Do not edit as part of a ticket. Add a renderer by dropping a
``<name>.py`` module here that calls ``register_renderer(name, fn)`` at import time.
Keep heavy deps (e.g. pygame) imported INSIDE the renderer function, not at module
top level, so discovery never fails when the dep is absent. See ``tickets/README.md``.
"""
from __future__ import annotations

import importlib
import pkgutil

for _module in pkgutil.iter_modules(__path__):
    importlib.import_module(f"{__name__}.{_module.name}")
