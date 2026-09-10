bl_info = {
    "name": "Export SBL",
    "author": "Adyox0",
    "version": (2, 0, 0),
    "blender": (4, 0, 0),
    "location": "File > Export > SBL (.sbl)",
    "description": "SBL exporter",
    "category": "Import-Export",
}

import os
import math
import struct
from collections import defaultdict

import bpy
import bmesh
from bpy.props import (
    StringProperty,
    IntProperty,
    IntVectorProperty,
    BoolProperty,
    FloatProperty,
    EnumProperty,
)
from bpy_extras.io_utils import ExportHelper
from mathutils import Vector


# ---------------- math helpers ----------------

EPS = 1e-6


def bilerp(p00: Vector, p10: Vector, p11: Vector, p01: Vector, u: float, v: float) -> Vector:
    return (
        p00 * (1.0 - u) * (1.0 - v)
        + p10 * u * (1.0 - v)
        + p11 * u * v
        + p01 * (1.0 - u) * v
    )



def safe_normal(p00: Vector, p10: Vector, p11: Vector, p01: Vector) -> Vector:
    n = (p10 - p00).cross(p11 - p00) + (p11 - p00).cross(p01 - p00)
    if n.length <= EPS:
        return Vector((0.0, 0.0, 0.0))
    return n.normalized()



def face_area(points) -> float:
    if len(points) == 3:
        return 0.5 * (points[1] - points[0]).cross(points[2] - points[0]).length
    if len(points) == 4:
        return (
            0.5 * (points[1] - points[0]).cross(points[2] - points[0]).length
            + 0.5 * (points[2] - points[0]).cross(points[3] - points[0]).length
        )
    return 0.0



def aabb_from_points(points):
    if not points:
        z = Vector((0.0, 0.0, 0.0))
        return z.copy(), z.copy()
    mn = Vector((1e30, 1e30, 1e30))
    mx = Vector((-1e30, -1e30, -1e30))
    for p in points:
        mn.x = min(mn.x, p.x)
        mn.y = min(mn.y, p.y)
        mn.z = min(mn.z, p.z)
        mx.x = max(mx.x, p.x)
        mx.y = max(mx.y, p.y)
        mx.z = max(mx.z, p.z)
    return mn, mx



def aabb_corners(points, padding: float = 0.0):
    mn, mx = aabb_from_points(points)
    if padding > 0.0:
        pad = Vector((padding, padding, padding))
        mn -= pad
        mx += pad

    minx, miny, minz = mn.x, mn.y, mn.z
    maxx, maxy, maxz = mx.x, mx.y, mx.z
    return [
        (minx, miny, minz),
        (maxx, miny, minz),
        (maxx, maxy, minz),
        (minx, maxy, minz),
        (minx, miny, maxz),
        (maxx, miny, maxz),
        (maxx, maxy, maxz),
        (minx, maxy, maxz),
    ]



def to_game_space(v: Vector, axis_fix: bool) -> Vector:
    if not axis_fix:
        return v.copy()
    # Blender Z-up -> engine-style Y-up
    return Vector((v.x, v.z, -v.y))



def uv_vec(uv) -> Vector:
    return Vector((float(uv[0]), float(uv[1])))



def nearly_equal_vec2(a: Vector, b: Vector, tol: float) -> bool:
    return (a - b).length <= tol



def build_patch_cps(
    p00, p10, p11, p01,
    uv00, uv10, uv11, uv01,
    override_uv=False, ou=0.0, ov=0.0,
):
    steps = [0.0, 1.0 / 3.0, 2.0 / 3.0, 1.0]
    cps = []
    for vv in steps:
        for uu in steps:
            pos = bilerp(p00, p10, p11, p01, uu, vv)
            if override_uv:
                u = float(ou)
                v = float(ov)
            else:
                tuv = bilerp(
                    Vector((uv00.x, uv00.y, 0.0)),
                    Vector((uv10.x, uv10.y, 0.0)),
                    Vector((uv11.x, uv11.y, 0.0)),
                    Vector((uv01.x, uv01.y, 0.0)),
                    uu,
                    vv,
                )
                u = float(tuv.x)
                v = float(tuv.y)
            cps.append((pos.x, pos.y, pos.z, u, v))
    return cps


# ---------------- topology helpers ----------------


def face_record_from_bmface(bmface, uv_layer, matrix_world, axis_fix, flip_v):
    loops = list(bmface.loops)
    positions = []
    uvs = []
    for loop in loops:
        p = to_game_space(matrix_world @ loop.vert.co, axis_fix)
        uv = loop[uv_layer].uv.copy() if uv_layer is not None else Vector((0.0, 0.0))
        if flip_v:
            uv.y = 1.0 - uv.y
        positions.append(p)
        uvs.append(uv_vec(uv))

    return {
        "face": bmface,
        "verts": [loop.vert.index for loop in loops],
        "positions": positions,
        "uvs": uvs,
        "material_index": int(bmface.material_index),
        "is_boundary_like": any((not edge.is_manifold) or len(edge.link_faces) < 2 for edge in bmface.edges),
    }



def build_boundary_cycle_from_tri_pair(tri_a, tri_b):
    counts = defaultdict(int)
    edges = []

    def add_edges(face):
        verts = face["verts"]
        for i in range(3):
            a = verts[i]
            b = verts[(i + 1) % 3]
            key = tuple(sorted((a, b)))
            counts[key] += 1
            edges.append((a, b))

    add_edges(tri_a)
    add_edges(tri_b)
    boundary = [e for e in counts.keys() if counts[e] == 1]
    if len(boundary) != 4:
        return None

    adj = defaultdict(list)
    for a, b in boundary:
        adj[a].append(b)
        adj[b].append(a)

    if any(len(v) != 2 for v in adj.values()):
        return None

    start = boundary[0][0]
    cycle = [start]
    prev = None
    cur = start
    for _ in range(3):
        nxts = [n for n in adj[cur] if n != prev]
        if not nxts:
            return None
        nxt = nxts[0]
        cycle.append(nxt)
        prev, cur = cur, nxt

    if len(set(cycle)) != 4:
        return None
    if start not in adj[cycle[-1]]:
        return None
    return cycle



def vertex_payload_map(face, uv_tol):
    result = {}
    for vid, pos, uv in zip(face["verts"], face["positions"], face["uvs"]):
        if vid in result:
            prev_pos, prev_uv = result[vid]
            if (pos - prev_pos).length > EPS or not nearly_equal_vec2(uv, prev_uv, uv_tol):
                return None
        result[vid] = (pos, uv)
    return result



def try_merge_tri_pair(tri_a, tri_b, uv_tol, normal_tol_deg):
    if len(tri_a["verts"]) != 3 or len(tri_b["verts"]) != 3:
        return None
    if tri_a["material_index"] != tri_b["material_index"]:
        return None

    shared = set(tri_a["verts"]) & set(tri_b["verts"])
    if len(shared) != 2:
        return None

    payload_a = vertex_payload_map(tri_a, uv_tol)
    payload_b = vertex_payload_map(tri_b, uv_tol)
    if payload_a is None or payload_b is None:
        return None

    for vid in shared:
        pa, uva = payload_a[vid]
        pb, uvb = payload_b[vid]
        if (pa - pb).length > EPS or not nearly_equal_vec2(uva, uvb, uv_tol):
            return None

    cycle = build_boundary_cycle_from_tri_pair(tri_a, tri_b)
    if cycle is None:
        return None

    payload = dict(payload_a)
    payload.update(payload_b)
    positions = [payload[vid][0] for vid in cycle]
    uvs = [payload[vid][1] for vid in cycle]

    if face_area(positions) <= EPS:
        return None

    tri_n_a = safe_normal(*tri_a["positions"], tri_a["positions"][0])
    tri_n_b = safe_normal(*tri_b["positions"], tri_b["positions"][0])
    if tri_n_a.length <= EPS or tri_n_b.length <= EPS:
        return None

    dot = max(-1.0, min(1.0, tri_n_a.dot(tri_n_b)))
    angle = math.degrees(math.acos(dot))
    if angle > normal_tol_deg:
        return None

    quad_n = safe_normal(positions[0], positions[1], positions[2], positions[3])
    avg_n = (tri_n_a + tri_n_b)
    if avg_n.length <= EPS or quad_n.length <= EPS:
        return None
    avg_n.normalize()
    if quad_n.dot(avg_n) < 0.0:
        positions.reverse()
        uvs.reverse()
        cycle.reverse()
        quad_n = safe_normal(positions[0], positions[1], positions[2], positions[3])

    # Convexity check
    signs = []
    for i in range(4):
        a = positions[i]
        b = positions[(i + 1) % 4]
        c = positions[(i + 2) % 4]
        cross = (b - a).cross(c - b)
        signs.append(cross.dot(quad_n))
    if min(signs) < -1e-5:
        return None

    return {
        "verts": cycle,
        "positions": positions,
        "uvs": uvs,
        "material_index": tri_a["material_index"],
        "is_boundary_like": tri_a["is_boundary_like"] or tri_b["is_boundary_like"],
    }



def collect_export_faces(obj_eval, axis_fix, flip_v, triangulate_ngons, merge_triangle_pairs, uv_tol, normal_tol_deg):
    mesh = obj_eval.to_mesh()
    try:
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bm.verts.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        uv_layer = bm.loops.layers.uv.active
        if uv_layer is None:
            raise RuntimeError(f"{obj_eval.name}: No active UV map found.")

        if triangulate_ngons:
            ngons = [f for f in bm.faces if len(f.verts) > 4]
            if ngons:
                bmesh.ops.triangulate(bm, faces=ngons)
                bm.faces.ensure_lookup_table()

        unsupported = [f for f in bm.faces if len(f.verts) not in (3, 4)]
        if unsupported:
            bmesh.ops.triangulate(bm, faces=unsupported)
            bm.faces.ensure_lookup_table()

        world = obj_eval.matrix_world.copy()
        records = [face_record_from_bmface(f, uv_layer, world, axis_fix, flip_v) for f in bm.faces if len(f.verts) in (3, 4)]

        if not merge_triangle_pairs:
            return records

        tri_candidates = [r for r in records if len(r["verts"]) == 3]
        quad_records = [r for r in records if len(r["verts"]) == 4]
        used = set()

        face_to_record = {id(r["face"]): r for r in tri_candidates}
        for record in tri_candidates:
            if id(record["face"]) in used:
                continue
            merged = None
            for edge in record["face"].edges:
                for linked in edge.link_faces:
                    if linked is record["face"]:
                        continue
                    other = face_to_record.get(id(linked))
                    if other is None or id(other["face"]) in used:
                        continue
                    merged = try_merge_tri_pair(record, other, uv_tol, normal_tol_deg)
                    if merged is not None:
                        used.add(id(record["face"]))
                        used.add(id(other["face"]))
                        quad_records.append(merged)
                        break
                if merged is not None:
                    break

        leftovers = [r for r in tri_candidates if id(r["face"]) not in used]
        return quad_records + leftovers
    finally:
        try:
            bm.free()
        except Exception:
            pass
        obj_eval.to_mesh_clear()


# ---------------- writer ----------------


def write_sbl_v2(path: str, header10, patches, extra_tail7=None, corners8=None):
    with open(path, "wb") as f:
        f.write(struct.pack("<I", 2))
        f.write(struct.pack("<10I", *[int(x) & 0xFFFFFFFF for x in header10]))

        for p in patches:
            a, b, c, d, material_id, auto_orient = p["patchHeader"]
            f.write(struct.pack("<6I", a, b, c, d, material_id, auto_orient))
            for (x, y, z, u, v) in p["cps"]:
                f.write(struct.pack("<5f", float(x), float(y), float(z), float(u), float(v)))

        if extra_tail7 is None:
            f.write(struct.pack("<I", 0))
            return

        if not corners8 or len(corners8) != 8:
            corners8 = [(0.0, 0.0, 0.0)] * 8

        f.write(struct.pack("<I", 1))
        for (x, y, z) in corners8:
            f.write(struct.pack("<3f", float(x), float(y), float(z)))
        f.write(struct.pack("<7I", *[int(v) & 0xFFFFFFFF for v in extra_tail7]))


# ---------------- operator ----------------


class ExportSBLV2Enhanced(bpy.types.Operator, ExportHelper):
    bl_idname = "export_scene.sbl_v2_enhanced"
    bl_label = "Export SBL v2 (Enhanced)"
    bl_options = {"PRESET"}

    filename_ext = ".sbl"
    filter_glob: StringProperty(default="*.sbl", options={"HIDDEN"})

    base_name: StringProperty(name="Base Name", default="custom_patch")

    material_id: IntProperty(
        name="Material ID",
        default=6,
        min=0,
        max=4095,
        description="Written into each patch header.",
    )

    backface_mode: EnumProperty(
        name="Backface Mode",
        items=[
            ("NONE", "None", "Do not duplicate backfaces."),
            ("BOUNDARY", "Boundary Only", "Duplicate only faces touching non-manifold/boundary edges."),
            ("ALL", "All Faces", "Duplicate every face as a reversed patch."),
        ],
        default="NONE",
    )

    apply_axis_fix: BoolProperty(
        name="Axis Fix (Blender Z-up -> Game Y-up)",
        default=True,
    )

    flip_winding_on_axis_fix: BoolProperty(
        name="Fix Winding When Axis Fix Enabled",
        default=True,
    )

    flip_v: BoolProperty(name="Flip V (UV)", default=False)

    force_constant_uv: BoolProperty(name="Force Constant UV (debug)", default=False)
    constant_u: FloatProperty(name="U", default=0.0, min=-10000.0, max=10000.0)
    constant_v: FloatProperty(name="V", default=0.0, min=-10000.0, max=10000.0)

    triangulate_ngons: BoolProperty(
        name="Triangulate NGons",
        default=True,
        description="Triangulates faces with more than 4 vertices before export.",
    )

    merge_triangle_pairs: BoolProperty(
        name="Merge Triangle Pairs Into Quads",
        default=True,
        description="Reduces waste by combining adjacent coplanar triangle pairs into a single quad patch when UVs are compatible.",
    )

    merge_normal_tolerance_deg: FloatProperty(
        name="Merge Normal Tolerance",
        default=2.0,
        min=0.0,
        max=45.0,
        description="Maximum angle between triangle normals to merge them into one quad.",
    )

    merge_uv_tolerance: FloatProperty(
        name="Merge UV Tolerance",
        default=0.0001,
        min=0.0,
        max=0.1,
        description="Maximum UV mismatch allowed on shared triangle-pair vertices.",
    )

    skip_degenerate_faces: BoolProperty(
        name="Skip Degenerate Faces",
        default=True,
        description="Skip zero-area faces instead of exporting junk patches.",
    )

    shift_to_origin: BoolProperty(
        name="Shift To Origin (Min -> 0)",
        default=True,
        description="Helps engines that expect geometry within header extents starting near 0.",
    )

    header_padding: FloatProperty(
        name="Header Padding",
        default=0.01,
        min=0.0,
        max=10.0,
        description="Small padding when computing header dims from extents.",
    )

    extra_record_mode: EnumProperty(
        name="V2 Extra Record",
        items=[
            ("NONE", "None", "Do not write the v2 0x7C extra record."),
            ("AABB", "AABB", "Write one AABB-shaped 0x7C extra record from the exported bounds."),
        ],
        default="AABB",
    )

    bounds_padding: FloatProperty(
        name="Bounds Padding",
        default=0.02,
        min=0.0,
        max=10.0,
        description="Expands the extra-record AABB slightly.",
    )

    extra_tail7: IntVectorProperty(
        name="Extra Tail (7x u32)",
        size=7,
        default=(63, 0, 0, 0, 0, 0, 0),
        min=0,
        max=0x7FFFFFFF,
        description="Raw tail written after the 8 AABB corners. First value is used by the game as a face/flags word; default 63 enables all six box faces.",
    )

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        box.prop(self, "base_name")
        box.prop(self, "material_id")

        box = layout.box()
        box.label(text="Geometry")
        box.prop(self, "backface_mode")
        box.prop(self, "triangulate_ngons")
        box.prop(self, "merge_triangle_pairs")
        if self.merge_triangle_pairs:
            box.prop(self, "merge_normal_tolerance_deg")
            box.prop(self, "merge_uv_tolerance")
        box.prop(self, "skip_degenerate_faces")

        box = layout.box()
        box.label(text="Transforms / UVs")
        box.prop(self, "apply_axis_fix")
        box.prop(self, "flip_winding_on_axis_fix")
        box.prop(self, "flip_v")
        box.prop(self, "force_constant_uv")
        if self.force_constant_uv:
            row = box.row(align=True)
            row.prop(self, "constant_u")
            row.prop(self, "constant_v")

        box = layout.box()
        box.label(text="Bounds / Header")
        box.prop(self, "shift_to_origin")
        box.prop(self, "header_padding")
        box.prop(self, "extra_record_mode")
        if self.extra_record_mode != "NONE":
            box.prop(self, "bounds_padding")
            box.prop(self, "extra_tail7")

    def execute(self, context):
        out_dir = os.path.dirname(self.filepath) if self.filepath else bpy.path.abspath("//")
        if not out_dir:
            out_dir = bpy.path.abspath("//")

        base = (self.base_name or "").strip()
        if not base:
            self.report({"ERROR"}, "Base Name cannot be empty.")
            return {"CANCELLED"}

        selected = [o for o in context.selected_objects if o.type == "MESH"]
        if not selected:
            self.report({"ERROR"}, "Select at least one mesh object.")
            return {"CANCELLED"}

        depsgraph = context.evaluated_depsgraph_get()
        patches = []
        all_points = []
        bounds_points = []
        skipped_faces = 0
        merged_pairs = 0

        for obj in selected:
            obj_eval = obj.evaluated_get(depsgraph)
            try:
                export_faces = collect_export_faces(
                    obj_eval=obj_eval,
                    axis_fix=self.apply_axis_fix,
                    flip_v=self.flip_v,
                    triangulate_ngons=self.triangulate_ngons,
                    merge_triangle_pairs=self.merge_triangle_pairs,
                    uv_tol=self.merge_uv_tolerance,
                    normal_tol_deg=self.merge_normal_tolerance_deg,
                )
            except RuntimeError as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}
            except Exception as exc:
                self.report({"ERROR"}, f"{obj.name}: export prep failed: {exc}")
                return {"CANCELLED"}

            if self.merge_triangle_pairs:
                tri_count = sum(1 for f in export_faces if len(f["verts"]) == 3)
                original_tri_count = 0
                mesh_temp = obj_eval.to_mesh()
                try:
                    original_tri_count = sum(1 for p in mesh_temp.polygons if len(p.vertices) == 3)
                finally:
                    obj_eval.to_mesh_clear()
                if original_tri_count > tri_count:
                    merged_pairs += (original_tri_count - tri_count) // 2

            for face_data in export_faces:
                pts = face_data["positions"]
                uvs = face_data["uvs"]
                if self.skip_degenerate_faces and face_area(pts) <= EPS:
                    skipped_faces += 1
                    continue

                if len(pts) == 3:
                    p00, p10, p11 = pts[0], pts[1], pts[2]
                    p01 = p00
                    uv00, uv10, uv11 = uvs[0], uvs[1], uvs[2]
                    uv01 = uv00
                elif len(pts) == 4:
                    p00, p10, p11, p01 = pts[0], pts[1], pts[2], pts[3]
                    uv00, uv10, uv11, uv01 = uvs[0], uvs[1], uvs[2], uvs[3]
                else:
                    skipped_faces += 1
                    continue

                if self.apply_axis_fix and self.flip_winding_on_axis_fix:
                    p10, p01 = p01, p10
                    uv10, uv01 = uv01, uv10

                cps = build_patch_cps(
                    p00, p10, p11, p01,
                    uv00, uv10, uv11, uv01,
                    override_uv=self.force_constant_uv,
                    ou=self.constant_u,
                    ov=self.constant_v,
                )

                for x, y, z, _, _ in cps:
                    v3 = Vector((x, y, z))
                    all_points.append(v3)
                    bounds_points.append(v3)

                patches.append({
                    "patchHeader": (1, 1, 1, 1, int(self.material_id), 0),
                    "cps": cps,
                })

                duplicate = False
                if self.backface_mode == "ALL":
                    duplicate = True
                elif self.backface_mode == "BOUNDARY":
                    duplicate = bool(face_data.get("is_boundary_like", False))

                if duplicate:
                    cps_back = build_patch_cps(
                        p00, p01, p11, p10,
                        uv00, uv01, uv11, uv10,
                        override_uv=self.force_constant_uv,
                        ou=self.constant_u,
                        ov=self.constant_v,
                    )
                    for x, y, z, _, _ in cps_back:
                        v3 = Vector((x, y, z))
                        all_points.append(v3)
                        bounds_points.append(v3)
                    patches.append({
                        "patchHeader": (1, 1, 1, 1, int(self.material_id), 0),
                        "cps": cps_back,
                    })

        if not patches:
            self.report({"ERROR"}, "No exportable faces found.")
            return {"CANCELLED"}

        shift = Vector((0.0, 0.0, 0.0))
        if self.shift_to_origin and all_points:
            mn, _ = aabb_from_points(all_points)
            shift = mn.copy()
            for surf in patches:
                new_cps = []
                for x, y, z, u, v in surf["cps"]:
                    p = Vector((x, y, z)) - shift
                    new_cps.append((p.x, p.y, p.z, u, v))
                surf["cps"] = new_cps
            bounds_points = [p - shift for p in bounds_points]

        mn2, mx2 = aabb_from_points(bounds_points)
        mx2 += Vector((self.header_padding, self.header_padding, self.header_padding))
        s0 = max(1, int(math.ceil(mx2.x + 1e-6)))
        s1 = max(1, int(math.ceil(mx2.y + 1e-6)))
        s2 = max(1, int(math.ceil(mx2.z + 1e-6)))

        header10 = [0] * 10
        header10[0] = s0
        header10[1] = s1
        header10[2] = s2
        header10[9] = len(patches)

        corners8 = None
        extra_tail7 = None
        if self.extra_record_mode == "AABB":
            corners8 = aabb_corners(bounds_points, padding=float(self.bounds_padding))
            extra_tail7 = tuple(int(v) for v in self.extra_tail7)

        out_path = os.path.join(out_dir, f"{base}.sbl")
        try:
            write_sbl_v2(out_path, header10, patches, extra_tail7=extra_tail7, corners8=corners8)
        except Exception as exc:
            self.report({"ERROR"}, f"Export failed: {exc}")
            return {"CANCELLED"}

        self.report(
            {"INFO"},
            f"Wrote {out_path} | patches={len(patches)} | header=({s0},{s1},{s2}) | skipped={skipped_faces} | tri-pairs merged≈{merged_pairs}",
        )
        return {"FINISHED"}


# ---------------- registration ----------------


def menu_func_export(self, context):
    self.layout.operator(ExportSBLV2Enhanced.bl_idname, text="SBL v2 (Enhanced) (.sbl)")


classes = (
    ExportSBLV2Enhanced,
)



def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)



def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
