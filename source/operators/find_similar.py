# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection, Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from functools import cached_property
from itertools import chain, groupby, product, zip_longest
from math import floor, sqrt
from operator import itemgetter
from statistics import fmean
from typing import Any, cast

import bpy
import networkx as nx
from bpy.types import Context, Event, Node, NodeLink, NodeSocket, NodeTree, Operator

from ..constants import ID_TYPES, get_id_type
from ..properties import DBU_PG_FindSimilarSettings


def get_settings() -> DBU_PG_FindSimilarSettings:
    return bpy.context.scene.dbu_similar_settings  # type: ignore


def get_invalid_nodes(ntree: NodeTree) -> set[Node]:
    settings = get_settings()
    invalid_nodes = set()

    if settings.exclude_organization:
        invalid_nodes.update([
          n for n in ntree.nodes if n.bl_idname in {'NodeReroute', 'NodeFrame'}])

    if settings.exclude_unused:
        G = nx.DiGraph([(l.from_node, l.to_node) for l in ntree.links])
        G.add_nodes_from(ntree.nodes)

        output_nodes = [n for n in G if not n.outputs and G.pred[n]]
        used_nodes = chain(*[nx.ancestors(G, n) for n in output_nodes], output_nodes)
        invalid_nodes.update(set(G).difference(used_nodes) | {n for n in G if n.mute})

    return invalid_nodes


def get_precomputed_root_link(link: NodeLink, links: dict[NodeSocket, NodeLink]) -> NodeLink:
    if link.from_node.bl_idname != 'NodeReroute':
        return link

    try:
        prev_link = links[link.from_node.inputs[0]]
    except (IndexError, KeyError):
        return link

    return get_precomputed_root_link(prev_link, links) if prev_link.is_valid else link


def get_root_link(link: NodeLink) -> NodeLink:
    if link.from_node.bl_idname != 'NodeReroute':
        return link

    if links := link.from_node.inputs[0].links:
        prev_link = links[0]
    else:
        return link

    return get_root_link(prev_link) if prev_link.is_valid else link


@dataclass
class Link:
    from_socket_idx: int
    linked_props: NodeProperties

    @cached_property
    def reduced_props(self) -> tuple[int, list[Any]]:
        return (self.from_socket_idx, [p for p in self.linked_props if not isinstance(p, Link)])

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, Link) and self.reduced_props == other.reduced_props


def get_non_socket_prop_names(node: Node) -> tuple[str, ...]:
    node_type = type(node)
    node_props = set(node_type.bl_rna.properties.keys())
    parent_props = set(node_type.__mro__[1].bl_rna.properties.keys())  # type: ignore
    return tuple(node_props - parent_props)


@dataclass(slots=True)
class NodeProperties:
    id_data: Node | NodeTree
    props: list[Link | Any] = field(default_factory=list)

    def __post_init__(self) -> None:
        if isinstance(self.id_data, Node):
            self.props.extend((self.id_data.bl_idname, self.id_data.mute))

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, NodeProperties) and self.props == other.props

    def __iter__(self) -> Iterator[Any]:
        return iter(self.props)

    def __len__(self) -> int:
        return len(self.props)

    def _add_link(self, link: NodeLink, node_map: dict[str, NodeProperties]) -> None:
        i = int(link.from_socket.path_from_id()[-2:-1])
        self.props.append(Link(i, node_map[link.from_node.name]))

    def add_inputs(
      self,
      links: dict[NodeSocket, NodeLink],
      node_map: dict[str, NodeProperties],
    ) -> None:
        node = self.id_data

        if not isinstance(node, Node):
            return

        props = self.props
        for socket in node.inputs:
            if socket.is_linked:
                if socket.is_multi_input:
                    assert socket.links is not None
                    for link in socket.links:
                        root_link = get_root_link(link)
                        if not root_link.from_node.mute:
                            self._add_link(root_link, node_map)
                    continue

                if not links[socket].from_node.mute:
                    self._add_link(links[socket], node_map)
                    continue

            if socket.hide_value or socket.type in {'SHADER', 'GEOMETRY'}:
                props.append((socket.bl_idname, socket.name))
                continue

            try:
                props.append(socket.default_value)  # type: ignore
            except AttributeError:
                continue

        if node.bl_idname in {'ShaderNodeValue', 'ShaderNodeRGB', 'ShaderNodeNormal'}:
            props.append(node.outputs[0].default_value)  # type: ignore

    def add_other_props(self) -> None:
        node = self.id_data

        if not isinstance(node, Node):
            return

        non_socket_props = get_non_socket_prop_names(node)

        if not non_socket_props:
            return

        props = self.props
        for prop_name in non_socket_props:
            if prop_name in {'color_mapping', 'texture_mapping', 'image_user', 'lightmixer'}:
                continue

            # yapf: disable
            prop = getattr(node, prop_name)
            if isinstance(prop, bpy.types.CurveMapping):
                curve_points = [(p.location, p.handle_type) for c in prop.curves for p in c.points]
                props.extend((
                  prop.black_level,
                  prop.white_level,
                  prop.extend,
                  prop.tone,
                  prop.use_clip,
                  prop.clip_max_x,
                  prop.clip_max_y,
                  prop.clip_min_x,
                  prop.clip_min_y,
                  curve_points))
            elif isinstance(prop, bpy.types.ColorRamp):
                elm_positions = [prop.evaluate(e.position) for e in prop.elements]
                props.extend((
                  prop.color_mode,
                  prop.hue_interpolation,
                  prop.interpolation,
                  *elm_positions))
            elif isinstance(prop, bpy.types.Image):
                props.extend((
                  prop.filepath,
                  prop.source,
                  prop.colorspace_settings.name,
                  prop.alpha_mode))
                if prop.source in {'SEQUENCE', 'MOVIE'}:
                    img_user: bpy.types.ImageUser = node.image_user # type: ignore
                    props.extend((
                      img_user.frame_duration,
                      img_user.frame_start,
                      img_user.frame_offset,
                      img_user.use_cyclic,
                      img_user.use_auto_refresh))
            else:
                props.append(prop)
            # yapf: enable


def contents_of_ntrees(
  bl_data: Iterable[NodeTree | bpy.types.Material | bpy.types.Light]
) -> defaultdict[str, list[NodeProperties]]:
    content_map = defaultdict(list)
    for id_data in bl_data:
        if id_data.library or (not isinstance(id_data, NodeTree) and not id_data.use_nodes):
            continue

        ntree = id_data if isinstance(id_data, NodeTree) else id_data.node_tree
        assert ntree is not None

        # Precompute links to avoid `O(len(ntree.links))` time
        links = {l.to_socket: l for l in ntree.links}
        root_links = {i: get_precomputed_root_link(l, links) for i, l in links.items()}
        contents = content_map[id_data.name]

        invalid_nodes = get_invalid_nodes(ntree)
        node_map = {n.name: NodeProperties(n) for n in ntree.nodes if n not in invalid_nodes}
        for props in node_map.values():
            props.add_inputs(root_links, node_map)
            props.add_other_props()
            props.props = [
              tuple(p) if isinstance(p, bpy.types.bpy_prop_array) else p for p in props]
            contents.append(props)

        if not isinstance(id_data, NodeTree):
            continue

        tree_sockets = [#
          (i.bl_socket_idname, i.name)
          for i in id_data.interface.items_tree
          if isinstance(i, bpy.types.NodeTreeInterfaceSocket)]
        contents.append(NodeProperties(ntree, ['TREE SOCKETS'] + tree_sockets))

    return content_map


_SENTINEL = object()


def pair_nodes(nodes1: Collection[NodeProperties], nodes2: Collection[NodeProperties]) -> int:
    diff_map = {}
    for props1 in nodes1:
        props1_len = len(props1.props[1:])
        for props2 in nodes2:
            zipped = zip_longest(props1.props[1:], props2.props[1:], fillvalue=_SENTINEL)
            dot = sum([1 for a, b in zipped if a == b])
            diff_map[(props1.id_data, props2.id_data)] = (props1_len - dot, dot)

    sums = []
    seen = set()
    for key in sorted(diff_map, key=lambda k: diff_map[k][0]):
        if not seen.intersection(key):
            sums.append(diff_map[key][1])
            seen.update(key)

    return sum(sums)


def cosine_similarity(A: list[NodeProperties], B: list[NodeProperties]) -> float:

    # Nodes from A are compared with nodes from B of the same type. The most similar are paired
    # together, and their dot product is returned in `pair_nodes()`.

    bl_idname = lambda p: p.props[0]
    A.sort(key=bl_idname)
    B.sort(key=bl_idname)

    if A == B:
        return 1

    ntypes1 = {t1: list(g1) for t1, g1 in groupby(A, bl_idname)}
    ntypes2 = {t2: list(g2) for t2, g2 in groupby(B, bl_idname)}

    s1 = sum([len(p1) - 1 for p1 in A])
    s2 = sum([pair_nodes(g1, ntypes2[t1]) for t1, g1 in ntypes1.items() if t1 in ntypes2])

    try:
        return s2 / sqrt(s1 * s2)
    except ZeroDivisionError:
        return 0


_Scores = dict[tuple[str, str], float]


def find_similar(contents: dict[str, list[NodeProperties]], results: _Scores) -> None:
    items = contents.items()
    seen = set()
    threshold = get_settings().similarity_threshold
    for k1, A in items:
        for k2, B in items:
            if {k1, k2} in seen or k1 == k2:
                continue

            seen.add(frozenset((k1, k2)))
            smallest, largest = sorted((A, B), key=lambda c: sum([len(p) - 1 for p in c]))

            # To avoid as many `cosine_similarity()` calls as possible, check for large
            # differences in length.
            if len(largest) != 0 and (len(smallest) / len(largest)) + 0.1 < threshold:
                continue

            score = cosine_similarity(largest, smallest)
            if score >= threshold:
                results[(k1, k2)] = score


def process(results: _Scores) -> tuple[list[tuple[str, ...]], _Scores]:
    graphs = defaultdict(nx.Graph)
    for (p, q), score in results.items():
        graphs[score].add_edge(p, q)

    cliques = {}
    for score, G in graphs.items():
        for c in nx.find_cliques(G):
            cliques[tuple(sorted(c))] = score  # type: ignore

    threshold = round(get_settings().grouping_threshold, 2)
    G = nx.Graph()
    for group, score in cliques.items():
        if 1 > score >= threshold:
            G.add_edges_from(product(group, group), score=score)

    groups = {}
    for c in nx.connected_components(G):
        if len(c) > 2:
            H = G.subgraph(c)
            groups[tuple(G)] = fmean([d for *_, d in H.edges.data('score')])

    seen = set(chain(*groups))
    raw_scored = {g: s for g, s in cliques.items() if s < 1 and not seen.intersection(g)} | groups
    scored = {
      g: floor((s * 100) * 10**1) / 10**1
      for g, s in sorted(raw_scored.items(), key=itemgetter(1), reverse=True)}

    duplicates = [g for g, s in cliques.items() if s >= 1]

    return duplicates, scored


# -------------------------------------------------------------------


def update_collections(
  bl_data: bpy.types.bpy_prop_collection,
  duplicates: Iterable[Sequence[str]],
  scored: _Scores | None = None,
) -> None:
    settings = get_settings()
    duplicates_coll = settings.duplicates
    scored_coll = settings.scored

    duplicates_coll.clear()
    scored_coll.clear()

    for dgroup in duplicates:
        ditem = duplicates_coll.add()
        ditem.id_type = get_id_type(bl_data[dgroup[0]])
        for name in dgroup:
            i = ditem.group.add()
            i.name = name

    if not scored:
        return

    for sgroup, score in scored.items():
        sitem = scored_coll.add()
        sitem.id_type = get_id_type(bl_data[sgroup[0]])
        sitem.score = score
        for name in sgroup:
            i = sitem.group.add()
            i.name = name


def find_similar_and_duplicate_ntrees(id_type: str) -> None:
    bl_data = ID_TYPES[id_type].collection
    results = {}

    for key, sub_data in groupby(sorted(bl_data, key=get_id_type), get_id_type):
        if 'UNDEFINED' not in key:
            content_map = contents_of_ntrees(tuple(sub_data))
            find_similar(content_map, results)

    duplicates, scored = process(results)
    update_collections(bl_data, duplicates, scored)


def find_duplicate_images() -> None:
    duplicates = []
    path = lambda img: img.filepath
    for _, raw_group in groupby(sorted(bpy.data.images, key=path), path):
        group = [i.name for i in raw_group]
        if len(group) > 1:
            duplicates.append(group)

    update_collections(bpy.data.images, duplicates)


def find_duplicate_meshes() -> None:
    meshes = [m for m in bpy.data.meshes if not m.library]
    seen = set()
    results = []
    for m1 in meshes:
        for m2 in meshes:
            if {m1, m2} in seen or m1 == m2:
                continue

            if m1.unit_test_compare(mesh=m2) == 'Same':
                results.append((m1, m2))

            seen.add(frozenset((m1, m2)))

    G = nx.Graph()
    for group in results:
        G.add_edges_from(product(group, group))

    duplicates = [sorted([m.name for m in c]) for c in nx.connected_components(G)]
    update_collections(bpy.data.meshes, duplicates)


class DBU_OT_FindSimilarAndDuplicates(Operator):
    bl_idname = "scene.dbu_find_similar_and_duplicates"
    bl_label = ""
    bl_options = {'INTERNAL', 'UNDO'}

    @classmethod
    def description(cls, context: Context, event: DBU_OT_FindSimilarAndDuplicates) -> str:
        id_type = get_settings().id_type
        text = ID_TYPES[id_type].label
        if ID_TYPES[id_type].is_ntree:
            return f"Show {text} with the highest similarity to each other"
        elif id_type == 'IMAGE':
            return f"Show {text} with identical names and filepaths"
        else:
            return f"Show duplicate {text}"

    def invoke(self, context: Context, event: Event) -> set[str]:
        settings = get_settings()
        settings.enabled = True
        return self.execute(context)

    def execute(self, context: Context) -> set[str]:
        settings = get_settings()
        id_type = settings.id_type

        if ID_TYPES[id_type].is_ntree:
            find_similar_and_duplicate_ntrees(id_type)
        elif id_type == 'IMAGE':
            find_duplicate_images()
        elif id_type == 'MESH':
            find_duplicate_meshes()

        if not settings.duplicates and not settings.scored:
            word = "similar" if ID_TYPES[id_type].is_ntree else "duplicate"
            self.report({'INFO'}, f"No {word} {ID_TYPES[id_type].label} found")
            settings.enabled = False

        return {'FINISHED'}


class DBU_OT_SimilarAndDuplicatesClearResults(Operator):
    bl_idname = "scene.dbu_similar_and_duplicates_clear_results"
    bl_label = "Clear"
    bl_description = "Clear the results"
    bl_options = {'INTERNAL', 'UNDO'}

    def execute(self, context: Context) -> set[str]:
        settings = get_settings()
        settings.enabled = False
        return {'FINISHED'}


# -------------------------------------------------------------------


def merge_ids(duplicate_ids: Iterable[Iterable[bpy.types.ID]]) -> int:
    to_remove = []
    for target, *junk in duplicate_ids:
        to_remove.extend(junk)
        for id_data in junk:
            id_data.user_remap(target)

    bpy.data.batch_remove(to_remove)
    return len(to_remove)


class DBU_OT_MergeDuplicates(Operator):
    bl_idname = "scene.dbu_merge_duplicates"
    bl_label = "Merge Duplicates"
    bl_options = {'INTERNAL', 'UNDO'}

    @classmethod
    def description(cls, context: Context, event: DBU_OT_MergeDuplicates) -> str:
        id_type = get_settings().id_type
        desc = f"Merge duplicate {ID_TYPES[id_type].label}"
        if id_type == 'MESH':
            desc += ". Equivalent to having them as if they were linked"

        return desc

    def invoke(self, context: Context, event: Event) -> set[str]:
        wm = context.window_manager
        return cast(set[str], wm.invoke_confirm(self, event))

    def execute(self, context: Context) -> set[str]:
        settings = get_settings()
        id_type = settings.id_type

        bl_data = ID_TYPES[id_type].collection
        duplicate_ids = []
        for group in settings.duplicates:
            # Reporting that IDs are missing could give the false impression that stale data is
            # always checked for, including changed node trees.
            if new_group := [bl_data[i.name] for i in group.group if i.name in bl_data]:
                duplicate_ids.append(new_group)

        count = merge_ids(duplicate_ids)
        bpy.ops.scene.dbu_find_similar_and_duplicates()  # type: ignore

        text = f"{ID_TYPES[id_type].label[:-1]}(s)" if id_type != 'MESH' else "mesh(s)"
        self.report({'INFO'}, f"Cleared {count} {text}")

        return {'FINISHED'}
