# SPDX-License-Identifier: GPL-2.0-or-later

from collections.abc import Collection, Iterator, Sequence
from itertools import chain

import bpy
from bpy.props import StringProperty
from bpy.types import ID, Context, Light, Material, Operator, ShaderNodeTree

from ..constants import ID_TYPES


def view_selected_delayed(area: bpy.types.Area, region: bpy.types.Region) -> float:
    with bpy.context.temp_override(area=area, region=region):
        bpy.ops.node.view_selected()
        return 0.0


def get_users(subset: Sequence[ID], value_types: set[str]) -> list[ID]:
    users = bpy.data.user_map(subset=subset, value_types=value_types)
    return list(chain(*users.values()))


def get_users_recursive(subset: Sequence[ID], value_types: set[str]) -> Iterator[ID]:
    value_types.add('NODETREE')
    for user in get_users(subset, value_types):
        if not hasattr(user, 'nodes'):
            yield user
        else:
            yield from get_users_recursive([user], value_types)


def get_material_path(
  users: Sequence[ID],
  mesh_users: Collection[ID],
  container: ShaderNodeTree | None = None,
) -> tuple[Material, ShaderNodeTree | None]:
    try:
        mat = next(
          u for u in users if isinstance(u, Material) and any(m.user_of_id(u) for m in mesh_users))
        return mat, container
    except StopIteration:
        nested_users = get_users([users[0]], {'MATERIAL', 'NODETREE'})
        return get_material_path(nested_users, mesh_users, users[0])


def get_light_path(
  users: Sequence[ID],
  container: ShaderNodeTree | None = None,
) -> tuple[Light, ShaderNodeTree | None]:
    try:
        light = next(u for u in users if isinstance(u, Light))
        return light, container
    except StopIteration:
        nested_users = get_users([users[0]], {'LIGHT', 'NODETREE'})
        return get_light_path(nested_users, users[0])


def get_geometry_node_group(
  space: bpy.types.Space,
  id_data: bpy.types.GeometryNodeTree,
) -> bpy.types.GeometryNodeGroup:
    nodes = [n for n in space.edit_tree.nodes if n.bl_idname == 'GeometryNodeGroup']
    try:
        node = next(n for n in nodes if n.node_tree == id_data)
    except StopIteration:
        container = next(
          n.node_tree for n in nodes if n.node_tree and n.node_tree.contains_tree(id_data))
        space.path.append(container)
        return get_geometry_node_group(space, id_data)

    return node


class DBU_OT_GoToDatablock(Operator):
    bl_idname = "scene.dbu_go_to_datablock"
    bl_label = "Go To Data-Block"
    bl_description = "See where this data-block is used"
    bl_options = {'INTERNAL'}

    id_name: StringProperty()
    id_type: StringProperty()
    node_name: StringProperty()
    settings: StringProperty(default='dbu_users_settings')

    def execute(self, context: Context) -> set[str]:
        id_type = self.id_type

        if 'TEXTURE' in id_type:
            return {'CANCELLED'}

        try:
            id_data = ID_TYPES[id_type].collection[self.id_name]
        except KeyError:
            self.report({'WARNING'}, "Data-Block not found")
            return {'CANCELLED'}

        # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

        is_mat = id_type == 'MATERIAL'
        is_obj = 'OBJECT' in id_type

        if id_type in {'MATERIAL', 'SHADER_NODETREE', 'IMAGE'}:
            if not is_mat:
                subset = list(get_users_recursive([id_data], {'MATERIAL'}))
            else:
                subset = [id_data]

            raw_mesh_users = get_users(subset, {'MESH'})
            light_users = list(get_users_recursive([id_data], {'LIGHT'}))

            shr_obj_users = get_users(raw_mesh_users + light_users, {'OBJECT'})
            geo_obj_users = get_users([id_data], {'OBJECT'})
            raw_obj_users = list(set(shr_obj_users + geo_obj_users))
        elif is_obj:
            raw_obj_users = [id_data] + get_users([id_data], {'OBJECT'})
        else:
            raw_obj_users = list(set(get_users_recursive([id_data], {'OBJECT'})))

        if not raw_obj_users:
            self.report({'WARNING'}, "No object users")
            return {'CANCELLED'}

        # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

        node_name = self.node_name
        is_obj_data = ID_TYPES[id_type].is_object_data and not node_name
        view_layer = context.view_layer.objects
        obj_users: list[bpy.types.Object] = [o for o in raw_obj_users if o.name in view_layer]

        settings = getattr(context.scene, self.settings)
        if settings.select_object_users or (is_obj or is_obj_data) or not obj_users:
            if count := len(raw_obj_users) - len(obj_users):
                self.report({'WARNING'},
                  f"Unable to select {count} object(s) in excluded collection(s)")
                if not obj_users:
                    return {'CANCELLED'}

            for obj in obj_users:
                if obj.hide_get():
                    obj.hide_set(False)
                    item = settings.unhidden_objects.add()
                    item.name = obj.name

                obj.select_set(True)

            if is_obj:
                view_layer.active = id_data
                return {'FINISHED'}

            if is_obj_data:
                return {'FINISHED'}

        # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

        is_geo = id_type == 'GEOMETRY_NODETREE'
        is_light = 'LIGHT' in id_type
        container = None

        if is_light:
            obj = next(o for o in obj_users if o.user_of_id(id_data))
        elif not is_geo:
            if geo_obj_users and not shr_obj_users:
                return {'FINISHED'}
            if subset:
                if not is_mat:
                    users = get_users([id_data], {'MATERIAL', 'NODETREE'})
                    mat, container = get_material_path(users, [o.data for o in obj_users])
                else:
                    mat = id_data

                for obj in obj_users:
                    slots = obj.material_slots
                    if mat.name in slots:
                        obj.active_material_index = slots[mat.name].slot_index
                        break
            else:
                users = get_users([id_data], {'LIGHT', 'NODETREE'})
                light, container = get_light_path(users)
                obj = next(o for o in obj_users if o.user_of_id(light))
        else:
            obj = obj_users[0]
            obj.modifiers.active = next(
              m for m in obj.modifiers
              if hasattr(m, 'node_group') and m.node_group.contains_tree(id_data))

        view_layer.active = obj

        # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

        try:
            area = next(
              a for a in bpy.context.window.screen.areas
              if a.type == 'NODE_EDITOR' and not a.spaces[0].pin)
            region = next(r for r in area.regions if r.type == 'WINDOW')
        except StopIteration:
            return {'FINISHED'}

        area.ui_type = 'GeometryNodeTree' if is_geo else 'ShaderNodeTree'
        with bpy.context.temp_override(area=area, region=region):
            space: bpy.types.SpaceNodeEditor = context.space_data

            if not is_geo:
                space.shader_type = 'OBJECT'

            space.path.clear()

            if not node_name and (is_mat or (is_geo and space.edit_tree == id_data)):
                bpy.ops.node.view_all('INVOKE_DEFAULT')
                return {'FINISHED'}

            if not is_mat and not is_light:
                if node_name:
                    space.path.append(id_data)
                elif container:
                    space.path.append(container)

            nodes = space.edit_tree.nodes

            if node_name:
                node = nodes[node_name]
            elif id_type == 'SHADER_NODETREE':
                node = next(
                  n for n in nodes if n.bl_idname == 'ShaderNodeGroup' and n.node_tree == id_data)
            elif is_geo:
                node = get_geometry_node_group(space, id_data)
                nodes = space.edit_tree.nodes  # In case the current tree changed
            else:
                node = next(
                  n for n in nodes if n.bl_idname == 'ShaderNodeTexImage' and n.image == id_data)

            for n in nodes:
                n.select = n == node

            nodes.active = node
            bpy.ops.view2d.reset()

            # If the node editor wasn't originally on the target node tree, then the selection
            # will only be recognised after `execute()` has ran. A workaround is to use a timer.
            bpy.app.timers.register(lambda: view_selected_delayed(area, region))

        # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

        self.node_name = ''
        self.settings = 'dbu_users_settings'

        return {'FINISHED'}


class DBU_OT_RehideObjectsUsers(Operator):
    bl_idname = "scene.dbu_rehide_object_users"
    bl_label = ""
    bl_description = "Rehide object users that were previously hidden"
    bl_options = {'INTERNAL', 'UNDO'}

    settings: StringProperty()

    def execute(self, context: Context) -> set[str]:
        settings = getattr(context.scene, self.settings)
        unhidden_objects = settings.unhidden_objects

        if not unhidden_objects:
            return {'CANCELLED'}

        for obj_item in unhidden_objects:
            obj = bpy.data.objects[obj_item.name]
            obj.hide_set(True)

        unhidden_objects.clear()

        return {'FINISHED'}
