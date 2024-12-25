# SPDX-License-Identifier: GPL-2.0-or-later

from collections.abc import Mapping
from dataclasses import dataclass

import bpy


@dataclass(slots=True)
class IDType:
    label: str
    icon: str
    _collection: str
    is_object_data: bool = False

    @property
    def collection(self) -> Mapping:
        return getattr(bpy.data, self._collection, {})


def _assign(
  key: str,
  coll: str,
  enums: list[str, str],
  collections: list[bpy.types.CollectionProperty],
  *,
  remove: bool = True,
) -> None:
    coll_prop = next(c for c in collections if c.identifier == coll)
    if remove:
        collections.remove(coll_prop)

    enum = next(i for i in enums if i[0] == key)
    collections.insert(enums.index(enum), coll_prop)


def _generate_id_types() -> dict[str, IDType]:
    props = bpy.types.KeyingSetPath.bl_rna.properties
    enums = [(k, v.icon) for k, v in props.enum_items.items()]

    collections = [p for p in bpy.types.BlendData.bl_rna.properties if p.type == 'COLLECTION']
    collections.sort(key=lambda c: c.identifier)

    _assign('CURVES', 'hair_curves', enums, collections)
    _assign('GREASEPENCIL_V3', 'grease_pencils', enums, collections, remove=False)
    _assign('KEY', 'shape_keys', enums, collections)
    _assign('LIGHT', 'lights', enums, collections)
    _assign('LIGHT_PROBE', 'lightprobes', enums, collections)

    id_types = {'UNDEFINED': IDType("undefined", 'QUESTION', '')}
    for (key, icon), coll_prop in zip(enums, collections):
        label = coll_prop.name.lower()
        coll = coll_prop.identifier
        props = coll_prop.fixed_type.bl_rna.properties

        id_types[key] = IDType(label, icon, coll)

        if 'type' not in props:
            continue

        for subkey, subval in props['type'].enum_items.items():
            subicon = subval.icon if subval.icon != 'NONE' else icon
            id_types[f'{subkey}_{key}'] = IDType(label, subicon, coll)

    for key, val in id_types.items():
        val.is_object_data = f"{key.split('_')[-1]}_OBJECT" in id_types

    id_types['SHADER_NODETREE'].icon = 'NODE_MATERIAL'
    id_types['TEXTURE_NODETREE'].icon = 'NODE_TEXTURE'
    id_types['META'].icon = 'OUTLINER_DATA_META'

    return id_types


def get_id_type(id_data: bpy.types.ID) -> str:
    id_type = getattr(id_data, 'type', '')

    if id_type != (k := id_data.id_type):
        id_type += f'_{k}' if id_type else k

    return id_type if id_type in ID_TYPES else 'UNDEFINED'


ID_TYPES = _generate_id_types()