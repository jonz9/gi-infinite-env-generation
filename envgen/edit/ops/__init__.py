"""Op package — auto-imports every op module so each self-registers.

⚠️ FROZEN FILE. Do not edit as part of a ticket. Adding a new op = dropping a new
``<op_name>.py`` module in this directory that defines an :class:`~envgen.edit.base.EditOp`
subclass decorated with ``@register_op``. This loader discovers it automatically;
you never list modules here. Op modules must have NO import-time side effects other
than class definition + registration. See ``tickets/README.md``.
"""
from __future__ import annotations

import importlib
import pkgutil

for _module in pkgutil.iter_modules(__path__):
    importlib.import_module(f"{__name__}.{_module.name}")
