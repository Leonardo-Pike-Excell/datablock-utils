# SPDX-License-Identifier: GPL-2.0-or-later

# type: ignore

import bpy
from bpy.types import Context, Panel, UILayout
from bpy.utils import register_class, unregister_class

from .constants import ID_TYPES
from .properties import DBU_PG_GroupItem, DBU_PG_ParentItem, DBU_PG_UserItem


class ScenePropertiesPanel:
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "scene"
    bl_options = {'DEFAULT_CLOSED'}


class DBU_PT_SimilarAndDuplicates(ScenePropertiesPanel, Panel):
    bl_label = "Similar & Duplicates"
    bl_idname = "SCENE_PT_DBU_similar_and_duplicates"

    @staticmethod
    def draw_group(layout: UILayout, item: DBU_PG_GroupItem) -> None:
        id_type = item.id_type
        icon = ID_TYPES[id_type].icon

        col = layout.box().column()
        for i in item.group:
            name = i.name
            row = col.row()
            row.alignment = 'LEFT'
            op = row.operator("scene.dbu_go_to_datablock", text=name, icon=icon, emboss=False)
            op.id_name = name
            op.id_type = id_type
            op.settings = 'dbu_similar_settings'

    def draw_header(self, context: Context) -> None:
        layout = self.layout
        layout.label(text="", icon='VIEWZOOM')

    def draw(self, context: Context) -> None:
        layout = self.layout
        layout.use_property_split = True

        scene = context.scene
        settings = scene.dbu_similar_settings
        id_type = settings.id_type

        is_ntree = ID_TYPES[id_type].is_ntree
        text = ID_TYPES[id_type].label
        label = text.title()

        row = layout.row(align=True)
        text = "Find Similar and Duplicates" if is_ntree else "Find Duplicates"
        row.operator("scene.dbu_find_similar_and_duplicates", text=text)
        if settings.enabled:
            row.operator("scene.dbu_similar_and_duplicates_clear_results", text="", icon='X')

        layout.prop(settings, "id_type")

        col = layout.column(align=True)
        col.active = is_ntree
        col.prop(settings, "similarity_threshold")
        col.prop(settings, "grouping_threshold")

        col = layout.column(heading="Exclude")
        col.active = is_ntree
        col.prop(settings, "exclude_unused")
        col.prop(settings, "exclude_organization")

        row = layout.row()
        row.prop(settings, "select_object_users")
        sub = row.row()
        sub.active = settings.select_object_users
        rehide_icon = 'HIDE_OFF' if settings.unhidden_objects else 'HIDE_ON'
        op = sub.operator("scene.dbu_rehide_object_users", text="", icon=rehide_icon)
        op.settings = 'dbu_similar_settings'

        if not settings.enabled:
            return

        if duplicates_coll := settings.duplicates:
            for ditem in duplicates_coll:
                layout.separator(factor=0.1)
                layout.label(text=f"{len(ditem.group)} Duplicates", icon='ERROR')
                self.draw_group(layout, ditem)

            layout.separator(factor=0.1)
            layout.operator_context = 'INVOKE_DEFAULT'
            layout.operator("scene.dbu_merge_duplicates", icon='FILE_PARENT')
            layout.separator(factor=0.3)

        for sitem in settings.scored:
            layout.separator(factor=0.1)
            layout.label(
              text=f"{len(sitem.group)} Similar {label} ({sitem.score:.1f}%)",
              icon='INFO',
            )
            self.draw_group(layout, sitem)


_NODE_NAME_SPACING = 3
_INDENT = 0.087
_INITIAL_INDENT_OFFSET = 0.026


class DBU_PT_UserMap(ScenePropertiesPanel, Panel):
    bl_label = "Data-Block Users"
    bl_idname = "SCENE_PT_DBU_user_map"

    @staticmethod
    def draw_datablock(layout: UILayout, item: DBU_PG_UserItem | DBU_PG_ParentItem) -> None:
        name = item.name
        id_type = item.id_type

        row = layout.box().column().row()
        row.scale_y = 0.5
        row.alignment = 'LEFT'
        op = row.operator(
          "scene.dbu_go_to_datablock",
          text=name,
          icon=ID_TYPES[id_type].icon,
          emboss=False,
        )
        op.id_name = name
        op.id_type = id_type

    @staticmethod
    def draw_node_names(layout: UILayout, user: DBU_PG_UserItem) -> None:
        node_names = user.node_names

        if not node_names:
            return

        layout.scale_y = 0.5
        layout.separator()
        col = layout.column(align=True)

        for n in node_names:
            row = col.row(align=True)
            row.alignment = 'LEFT'

            fac = _NODE_NAME_SPACING if n != node_names[-1] else _NODE_NAME_SPACING / 2
            col.separator(factor=fac)

            op = row.operator("scene.dbu_go_to_datablock", text=n.name, emboss=False)
            op.id_name = user.name
            op.id_type = user.id_type
            op.node_name = n.name

    @classmethod
    def draw_users(cls, layout: UILayout, parent: DBU_PG_ParentItem, depth: int = 1) -> None:
        settings = bpy.context.scene.dbu_users_settings
        user_map = settings.user_map
        object_contents = settings.object_contents

        indent = _INDENT + _INITIAL_INDENT_OFFSET if depth == 1 else _INDENT * depth

        for user in parent.users:
            idx = user.as_parent_idx

            if not object_contents and ID_TYPES[user.id_type].is_object_data:
                cls.draw_users(layout, user_map[idx], depth)
                continue

            split = layout.split(factor=indent)
            split.separator()
            cls.draw_datablock(split, user)

            split = layout.split(factor=indent + 0.0574)
            cls.draw_node_names(split, user)

            cls.draw_users(layout, user_map[idx], depth + 1)

    def draw_header(self, context: Context) -> None:
        layout = self.layout
        layout.label(text="", icon='FAKE_USER_OFF')

    def draw(self, context: Context) -> None:
        layout = self.layout
        layout.use_property_split = True

        settings = context.scene.dbu_users_settings
        parent_map = settings.parent_map

        split = layout.split(factor=(65 / context.area.width), align=True)
        split.popover("SCENE_PT_DBU_user_map_filter", icon='FILTER')
        row = split.row(align=True)
        row.operator("scene.dbu_user_map")
        if parent_map:
            row.operator("scene.dbu_user_map_clear_results", text="", icon='X')

        col = layout.column(align=True)
        col.use_property_split = False
        col.separator()

        if parents := settings.parents:
            row = col.row(align=True)
            row.alignment = 'RIGHT'
            row.prop(settings, "hide", text="Hide", toggle=1)
            row.operator("scene.dbu_user_map_remove_all", text="Clear")

            if not settings.hide:
                box = col.box()
                box.scale_y = 0.75
                box.emboss = 'NONE'
                for i, parent in enumerate(parents):
                    name = parent.name
                    id_type = parent.id_type

                    split = box.split(factor=0.9)
                    row = split.row()
                    row.alignment = 'LEFT'
                    op = row.operator(
                      "scene.dbu_go_to_datablock",
                      text=name,
                      icon=ID_TYPES[id_type].icon,
                    )
                    op.id_name = name
                    op.id_type = id_type
                    row = split.row()
                    row.alignment = 'RIGHT'
                    op = row.operator("scene.dbu_user_map_remove", text="", icon='X')
                    op.idx = i

        row = col.row(align=True)
        row.prop(settings, "id_type", icon_only=True)
        row.prop_search(
          settings,
          "id_name",
          bpy.data,
          ID_TYPES[settings.id_type]._collection,
          text="",
          icon='BLANK1',
        )
        sub = row.row()
        sub.alignment = 'RIGHT'
        sub.operator("scene.dbu_user_map_add_all", text="All", icon='ADD')

        layout.separator()
        row = layout.row(align=True)
        row.use_property_split = False
        row.alignment = 'CENTER'
        row.prop(settings, "select_object_users")
        sub = row.row()
        sub.active = settings.select_object_users
        rehide_icon = 'HIDE_OFF' if settings.unhidden_objects else 'HIDE_ON'
        op = sub.operator("scene.dbu_rehide_object_users", text="", icon=rehide_icon)
        op.settings = 'dbu_users_settings'

        if not parent_map:
            return

        layout.separator(factor=0.5)

        for parent in parent_map:
            header, panel = layout.panel(parent.id_type + parent.name, default_closed=True)
            self.draw_datablock(header, parent)

            if not panel:
                continue

            if parent.users:
                self.draw_users(panel, parent)
            else:
                split = panel.split(factor=_INDENT + _INITIAL_INDENT_OFFSET)
                split.separator()
                row = split.row()
                row.active = False
                row.label(text="No Users Matching Filter")


class DBU_PT_UserMapFilter(ScenePropertiesPanel, Panel):
    bl_idname = "SCENE_PT_DBU_user_map_filter"
    bl_label = ""
    bl_description = "Filter users by type"
    bl_options = {'INSTANCED'}

    @staticmethod
    def draw_user_type(layout: UILayout, prop_name: str) -> None:
        settings = bpy.context.scene.dbu_users_settings

        if prop_name not in {'OBJECT', 'object_contents'}:
            if prop_name == 'others':
                enums = bpy.types.KeyingSetPath.bl_rna.properties['id_type'].enum_items.keys()
                if not any([ID_TYPES[e].collection for e in enums if e not in dir(settings)]):
                    return
            elif not ID_TYPES[prop_name].collection:
                return

        icon = ID_TYPES[prop_name].icon if prop_name in ID_TYPES else 'BLANK1'

        row = layout.row()
        row.label(icon=icon)
        row.prop(settings, prop_name)

    def draw(self, context: Context) -> None:
        layout = self.layout
        settings = context.scene.dbu_users_settings

        layout.label(text="Filter Users")

        col = layout.column()
        self.draw_user_type(col, 'SCENE')
        self.draw_user_type(col, 'MATERIAL')
        self.draw_user_type(col, 'NODETREE')
        self.draw_user_type(col, 'OBJECT')
        sub = col.column()
        sub.enabled = settings.OBJECT
        self.draw_user_type(sub, 'object_contents')
        self.draw_user_type(sub, 'MESH')
        self.draw_user_type(sub, 'LIGHT')
        self.draw_user_type(sub, 'others')


classes = (
  DBU_PT_SimilarAndDuplicates,
  DBU_PT_UserMap,
  DBU_PT_UserMapFilter,
)


def register() -> None:
    for cls in classes:
        register_class(cls)


def unregister() -> None:
    for cls in reversed(classes):
        unregister_class(cls)
