# SPDX-License-Identifier: GPL-2.0-or-later

import bpy
from bpy.props import IntProperty
from bpy.types import ID, Context, Operator

from ..constants import ID_TYPES, get_id_type
from ..properties import DBU_PG_ParentItem

_EXCLUDED_VALUE_TYPES = {'COLLECTION', 'WINDOWMANAGER', 'WORKSPACE'}


class DBU_OT_UserMap(Operator):
    bl_idname = "scene.dbu_user_map"
    bl_label = "Show Data-Block Users"
    bl_description = "List the users of the specified data-blocks"
    bl_options = {'INTERNAL'}

    @classmethod
    def add_users(
      cls,
      parent: DBU_PG_ParentItem,
      user: ID,
      precomputed: dict[ID, set[ID]],
      ancestors: set[ID],
    ) -> None:
        settings = bpy.context.scene.dbu_users_settings
        user_map = settings.user_map

        name = user.name
        id_type = get_id_type(user)

        if not settings.OBJECT and ID_TYPES[id_type].is_object_data:
            return

        as_parent = user_map.add()
        as_parent.name = name
        as_parent.id_type = id_type

        as_user = parent.users.add()
        as_user.name = name
        as_user.id_type = id_type
        as_user.as_parent_idx = len(user_map) - 1

        if user in ancestors:
            return

        ntree = getattr(user, 'node_tree', user)
        try:
            nodes = ntree.nodes
        except AttributeError:
            pass
        else:
            # yapf: disable
            if parent.id_type != 'IMAGE':
                node_names = [
                  n.name for n in nodes if hasattr(n, 'node_tree')
                  and n.node_tree and n.node_tree.name == parent.name]
            else:
                node_names = [
                  n.name for n in nodes if hasattr(n, 'image')
                  and n.image.name == parent.name]
            # yapf: enable

            for name in sorted(node_names):
                n = as_user.node_names.add()
                n.name = name

        for u in precomputed[user]:
            if u != user:
                cls.add_users(as_parent, u, precomputed, ancestors | {user})

    def execute(self, context: Context) -> set[str]:
        settings = context.scene.dbu_users_settings
        parents = [p for p in settings.parents if p.id_type != 'UNDEFINED']

        if not parents:
            return {'CANCELLED'}

        parent_map = settings.parent_map
        parent_map.clear()
        settings.user_map.clear()

        setting_enums = {e for e in dir(settings) if e.isupper()}
        value_types = {e for e in setting_enums if getattr(settings, e)}
        if settings.others:
            prop = bpy.types.KeyingSetPath.bl_rna.properties['id_type']
            value_types.update(set(prop.enum_items.keys()) - setting_enums)

        value_types -= _EXCLUDED_VALUE_TYPES
        key_types = value_types.union(settings.bl_rna.properties['id_type'].enum_items.keys())
        precomputed = bpy.data.user_map(key_types=key_types, value_types=value_types)

        for temp_parent in parents:
            name = temp_parent.name
            id_type = temp_parent.id_type

            as_parent = parent_map.add()
            as_parent.name = name
            as_parent.id_type = id_type

            id_data = ID_TYPES[id_type].collection[name]
            for user in precomputed[id_data]:
                self.add_users(as_parent, user, precomputed, {id_data})

        return {'FINISHED'}


class DBU_OT_UserMapClearResults(Operator):
    bl_idname = "scene.dbu_user_map_clear_results"
    bl_label = "Clear"
    bl_description = "Clear the results"
    bl_options = {'INTERNAL'}

    def execute(self, context: Context) -> set[str]:
        settings = context.scene.dbu_users_settings

        settings.parent_map.clear()
        settings.user_map.clear()

        return {'FINISHED'}


class DBU_OT_UserMapAddAll(Operator):
    bl_idname = "scene.dbu_user_map_add_all"
    bl_label = "Add All"
    bl_description = "Add all data-blocks of this type"
    bl_options = {'INTERNAL'}

    def execute(self, context: Context) -> set[str]:
        settings = context.scene.dbu_users_settings
        parents = settings.parents
        bl_data = ID_TYPES[settings.id_type].collection

        for id_data in bl_data:
            name = id_data.name
            id_type = get_id_type(id_data)

            if name in parents:
                if any((p.name, p.id_type) == (name, id_type) for p in parents):
                    continue

            parent = parents.add()
            parent.name = name
            parent.id_type = id_type

        return {'FINISHED'}


class DBU_OT_UserMapRemove(Operator):
    bl_idname = "scene.dbu_user_map_remove"
    bl_label = "Remove"
    bl_description = "Remove item"
    bl_options = {'INTERNAL'}

    idx: IntProperty()

    def execute(self, context: Context) -> set[str]:
        settings = context.scene.dbu_users_settings
        idx = self.idx

        settings.parents.remove(idx)
        settings.parent_map.remove(idx)

        return {'FINISHED'}


class DBU_OT_UserMapRemoveAll(Operator):
    bl_idname = "scene.dbu_user_map_remove_all"
    bl_label = "Clear"
    bl_description = "Clear the list"
    bl_options = {'INTERNAL'}

    def execute(self, context: Context) -> set[str]:
        settings = context.scene.dbu_users_settings

        settings.parents.clear()
        settings.parent_map.clear()

        return {'FINISHED'}
