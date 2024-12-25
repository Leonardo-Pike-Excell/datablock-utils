# SPDX-License-Identifier: GPL-2.0-or-later

from . import operators, properties, ui


def register():
    ui.register()
    operators.register()
    properties.register()


def unregister():
    properties.unregister()
    operators.unregister()
    ui.unregister()
