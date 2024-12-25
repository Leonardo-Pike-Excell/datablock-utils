# SPDX-License-Identifier: GPL-2.0-or-later

import importlib
import inspect
import pkgutil
from collections.abc import Iterator
from typing import Type

import bpy


def classes() -> Iterator[Type]:
    for _, module_name, _ in pkgutil.iter_modules(__path__):
        module = importlib.import_module(f'{__name__}.{module_name}')
        for cls_name, cls in inspect.getmembers(module, inspect.isclass):
            if cls_name.startswith('DBU_OT'):
                yield cls


def register() -> None:
    for cls in classes():
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in classes():
        bpy.utils.unregister_class(cls)
