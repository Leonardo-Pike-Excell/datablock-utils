# SPDX-License-Identifier: GPL-2.0-or-later

# type: ignore

from __future__ import annotations

from collections.abc import Iterable

import bpy
from bpy.props import (
  BoolProperty,
  CollectionProperty,
  EnumProperty,
  FloatProperty,
  IntProperty,
  PointerProperty,
  StringProperty,
)
from bpy.types import Context, PropertyGroup, Scene
from bpy.utils import register_class, unregister_class

from .constants import ID_TYPES, get_id_type


def get_items(
  id_types: Iterable[str],
  reverse: bool = False,
) -> tuple[tuple[str, str, str, str, int], ...]:
    items = []
    for i, id_type in enumerate(id_types):
        val = ID_TYPES[id_type]
        items.append((id_type, val.label.title(), "", val.icon, i))

    if reverse:
        items.reverse()

    return tuple(items)


def add_parent_item(self: DBU_PG_UserMapSettings, context: Context) -> None:
    id_name = self.id_name

    if not id_name:
        return

    parents = self.parents
    bl_data = ID_TYPES[self.id_type].collection
    id_type = get_id_type(bl_data[id_name])

    if id_name in parents:
        if any((p.name, p.id_type) == (id_name, id_type) for p in parents):
            self.id_name = ""
            return

    parent = parents.add()
    parent.name = id_name
    parent.id_type = id_type

    self.id_name = ""

    update_user_map(self, context)


def update_similar(self: DBU_PG_FindSimilarSettings, context: Context) -> None:
    settings = context.scene.dbu_similar_settings
    if settings.enabled:
        bpy.ops.scene.dbu_node_trees_find_similar(id_type=settings.id_type)


def update_user_map(self: DBU_PG_UserMapSettings, context: Context) -> None:
    settings = context.scene.dbu_users_settings
    if settings.parent_map:
        bpy.ops.scene.dbu_user_map()


class DBU_PG_Item(PropertyGroup):
    pass


class DBU_PG_GroupItem(PropertyGroup):
    group: CollectionProperty(type=DBU_PG_Item)
    id_type: StringProperty()
    score: FloatProperty()


class DBU_PG_UserItem(PropertyGroup):
    id_type: StringProperty()
    node_names: CollectionProperty(type=DBU_PG_Item)
    as_parent_idx: IntProperty()


class DBU_PG_ParentItem(PropertyGroup):
    id_type: StringProperty()
    users: CollectionProperty(type=DBU_PG_UserItem)


class DBU_PG_FindSimilarSettings(PropertyGroup):
    id_type: EnumProperty(
      items=get_items(('NODETREE', 'MATERIAL', 'LIGHT')),
      name="Type",
      description="Data-block type",
      default='NODETREE',
      options=set(),
      update=update_similar)

    similarity_threshold: FloatProperty(
      name="Similarity Threshold",
      description="Threshold at which two items are considered similar",
      default=0.8,
      min=0.5,
      max=1,
      step=1,
      options=set(),
      update=update_similar)

    grouping_threshold: FloatProperty(
      name="Grouping Threshold",
      description=
      "Collections above this similarity threshold, when displayed in the results, are grouped together if they share items. One to disable",
      default=0.82,
      min=0.5,
      max=1,
      step=1,
      options=set(),
      update=update_similar)

    exclude_unused: BoolProperty(
      name="Unused Nodes",
      description="Exclude nodes that are muted or not used by any group outputs",
      default=True,
      options=set(),
      update=update_similar)

    exclude_organization: BoolProperty(
      name="Frames and Reroutes",
      description="Exclude frame and reroute nodes",
      default=True,
      options=set(),
      update=update_similar)

    select_object_users: BoolProperty(
      name="Select Object Users",
      description=
      "Object users will be selected when clicking on a data-block (in addition to revealing it in the shader editor)",
      options=set())

    unhidden_objects: CollectionProperty(type=DBU_PG_Item)

    duplicates: CollectionProperty(type=DBU_PG_GroupItem)
    scored: CollectionProperty(type=DBU_PG_GroupItem)
    enabled: BoolProperty()


class DBU_PG_UserMapSettings(PropertyGroup):
    SCENE: BoolProperty(
      name="Scenes",
      description="Show scenes",
      default=False,
      options=set(),
      update=update_user_map)

    MATERIAL: BoolProperty(
      name="Materials",
      description="Show materials",
      default=True,
      options=set(),
      update=update_user_map)

    NODETREE: BoolProperty(
      name="Node Groups",
      description="Show node groups",
      default=True,
      options=set(),
      update=update_user_map)

    OBJECT: BoolProperty(
      name="Objects",
      description="Show objects",
      default=True,
      options=set(),
      update=update_user_map)

    object_contents: BoolProperty(
      name="Object Contents",
      description="Show the contents of object elements",
      default=False,
      options=set(),
      update=update_user_map)

    MESH: BoolProperty(
      name="Meshes",
      description="Show mesh objects",
      default=True,
      options=set(),
      update=update_user_map)

    LIGHT: BoolProperty(
      name="Lights",
      description="Show light objects",
      default=True,
      options=set(),
      update=update_user_map)

    others: BoolProperty(
      name="Others",
      description="Show curves, metaballs, textures, ...",
      default=True,
      options=set(),
      update=update_user_map)

    hide: BoolProperty(name="Hide", description="Hide the list")

    parents: CollectionProperty(type=DBU_PG_ParentItem)

    id_type: EnumProperty(
      items=get_items(('MATERIAL', 'NODETREE', 'IMAGE', 'MESH', 'OBJECT'), reverse=True),
      name="Type",
      description="Data-block type",
      default='MATERIAL',
      options=set())

    id_name: StringProperty(
      name="Search",
      description="Search for data-blocks and add them to the list",
      update=add_parent_item)

    select_object_users: BoolProperty(
      name="Select Object Users",
      description=
      "When clicking on a data-block, select its object users (in addition to revealing it in the node editor)",
      options=set())

    unhidden_objects: CollectionProperty(type=DBU_PG_Item)

    parent_map: CollectionProperty(type=DBU_PG_ParentItem)
    user_map: CollectionProperty(type=DBU_PG_ParentItem)


classes = (
  DBU_PG_Item,
  DBU_PG_GroupItem,
  DBU_PG_FindSimilarSettings,
  DBU_PG_UserItem,
  DBU_PG_ParentItem,
  DBU_PG_UserMapSettings,
)


def register() -> None:
    for cls in classes:
        register_class(cls)

    Scene.dbu_similar_settings = PointerProperty(type=DBU_PG_FindSimilarSettings)
    Scene.dbu_users_settings = PointerProperty(type=DBU_PG_UserMapSettings)


def unregister() -> None:
    del Scene.dbu_users_settings
    del Scene.dbu_similar_settings

    for cls in reversed(classes):
        if cls.is_registered:
            unregister_class(cls)
