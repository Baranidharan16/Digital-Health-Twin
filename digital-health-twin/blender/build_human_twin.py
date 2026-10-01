"""Build the Human Health Digital Twin 3D asset in Blender and export it as GLB.

The web app drives this model from live data, so the model is built from
*separate, named objects* rather than one merged mesh:

    Head      temperature highlight region
    Torso     overall state tint
    Arm_L/R   activity animation (origin at the shoulder joint)
    Leg_L/R   activity animation (origin at the hip joint)
    Heart     pulses at the live heart rate
    Lung_L/R  expand and contract at the live respiratory rate

Run it in any of these ways (Blender 3.6+ / 4.x):

1. Blender GUI: Scripting workspace -> Open this file -> Run Script.
2. Headless:    blender -b -P blender/build_human_twin.py
3. Custom path: blender -b -P blender/build_human_twin.py -- --out my.glb --blend twin.blend

By default the GLB is written to frontend/public/models/human_twin.glb.
The web app works without this file (it falls back to a procedural figure),
so Blender is only needed to (re)build or customise the asset.

Coordinates: Blender is Z-up, metres, subject faces -Y (towards the front
view camera); subject's left is +X. The glTF exporter converts to Y-up.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

MB_RESOLUTION = 0.018  # metaball polygonization step (m); smaller = smoother/heavier
THRESHOLD = 0.6


# --------------------------------------------------------------------- utils
def parse_args() -> tuple[Path, Path | None]:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    try:
        here = Path(__file__).resolve().parent
    except NameError:  # running from Blender's text editor without a saved file
        here = Path(bpy.path.abspath("//")) if bpy.data.filepath else Path.cwd()
    out = here.parent / "frontend" / "public" / "models" / "human_twin.glb"
    blend = None
    for i, arg in enumerate(argv):
        if arg == "--out" and i + 1 < len(argv):
            out = Path(argv[i + 1]).resolve()
        if arg == "--blend" and i + 1 < len(argv):
            blend = Path(argv[i + 1]).resolve()
    return out, blend


def clear_scene() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for collection in (bpy.data.meshes, bpy.data.metaballs, bpy.data.materials):
        for block in list(collection):
            collection.remove(block)


def material(name: str, rgba: tuple[float, float, float, float], roughness: float = 0.5) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = rgba
    bsdf.inputs["Roughness"].default_value = roughness
    if rgba[3] < 1.0:
        bsdf.inputs["Alpha"].default_value = rgba[3]
        mat.blend_method = "BLEND"
    return mat


def lerp(a: Vector, b: Vector, t: float) -> Vector:
    return a + (b - a) * t


class Part:
    """A metaball object whose elements blend into one smooth surface."""

    def __init__(self, family: str) -> None:
        data = bpy.data.metaballs.new(family)
        data.resolution = MB_RESOLUTION
        data.render_resolution = MB_RESOLUTION
        data.threshold = THRESHOLD
        self.obj = bpy.data.objects.new(family, data)  # unique prefix = own metaball family
        bpy.context.scene.collection.objects.link(self.obj)
        self.data = data

    def ball(self, at: tuple[float, float, float] | Vector, radius: float, scale=(1.0, 1.0, 1.0)) -> None:
        el = self.data.elements.new(type="ELLIPSOID" if scale != (1.0, 1.0, 1.0) else "BALL")
        el.co = Vector(at)
        el.radius = radius
        if el.type == "ELLIPSOID":
            el.size_x, el.size_y, el.size_z = scale
        el.stiffness = 2.0

    def chain(self, points: list[tuple[Vector, float]], spacing: float = 0.03) -> None:
        """Balls along a polyline with linearly interpolated radii (limbs)."""
        for (p0, r0), (p1, r1) in zip(points, points[1:]):
            n = max(int((p1 - p0).length / spacing), 1)
            for i in range(n + (1 if (p1, r1) == points[-1] else 0)):
                t = i / n
                self.ball(lerp(p0, p1, t), r0 + (r1 - r0) * t)

    def to_mesh(self, name: str, pivot: Vector, mat: bpy.types.Material, decimate: float = 1.0) -> bpy.types.Object:
        bpy.ops.object.select_all(action="DESELECT")
        self.obj.select_set(True)
        bpy.context.view_layer.objects.active = self.obj
        bpy.ops.object.convert(target="MESH")
        mesh_obj = bpy.context.view_layer.objects.active
        mesh_obj.name = name
        mesh_obj.data.name = name
        if decimate < 1.0:
            mod = mesh_obj.modifiers.new("decimate", "DECIMATE")
            mod.ratio = decimate
            bpy.ops.object.modifier_apply(modifier=mod.name)
        bpy.ops.object.shade_smooth()
        bpy.context.scene.cursor.location = pivot
        bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
        mesh_obj.data.materials.clear()
        mesh_obj.data.materials.append(mat)
        return mesh_obj


# ------------------------------------------------------------------ anatomy
V = Vector


def build() -> list[bpy.types.Object]:
    skin = material("TwinSkin", (0.72, 0.80, 0.85, 0.28), roughness=0.35)
    heart_mat = material("TwinHeart", (0.71, 0.21, 0.25, 1.0), roughness=0.4)
    lung_mat = material("TwinLung", (0.85, 0.55, 0.58, 1.0), roughness=0.6)

    objects = []

    head = Part("mbHead")
    head.ball((0, 0, 1.635), 0.16, (0.8, 0.9, 1.0))
    head.ball((0, -0.012, 1.56), 0.1)  # jaw
    head.ball((0, 0, 1.49), 0.085)  # neck
    head.ball((0, 0, 1.445), 0.095)
    objects.append(head.to_mesh("Head", V((0, 0, 1.47)), skin, decimate=0.6))

    torso = Part("mbTorso")
    torso.ball((0, 0, 1.37), 0.26, (1.25, 0.66, 0.62))  # shoulders / upper chest
    torso.ball((0, -0.01, 1.26), 0.26, (1.08, 0.68, 0.8))  # chest
    torso.ball((0, 0, 1.13), 0.24, (0.92, 0.62, 0.75))  # abdomen
    torso.ball((0, 0, 1.01), 0.25, (0.98, 0.64, 0.7))  # waist
    torso.ball((0, 0.005, 0.92), 0.26, (1.06, 0.68, 0.62))  # pelvis
    objects.append(torso.to_mesh("Torso", V((0, 0, 1.0)), skin, decimate=0.6))

    for side, sx in (("L", 1.0), ("R", -1.0)):
        shoulder = V((0.2 * sx, 0, 1.39))
        arm = Part(f"mbArm{side}")
        arm.chain(
            [
                (shoulder, 0.085),
                (V((0.25 * sx, 0.005, 1.13)), 0.066),  # elbow
                (V((0.28 * sx, -0.01, 0.89)), 0.052),  # wrist
                (V((0.29 * sx, -0.015, 0.82)), 0.062),  # hand
            ]
        )
        objects.append(arm.to_mesh(f"Arm_{side}", shoulder, skin, decimate=0.6))

        hip = V((0.095 * sx, 0, 0.9))
        leg = Part(f"mbLeg{side}")
        leg.chain(
            [
                (hip, 0.125),
                (V((0.1 * sx, 0, 0.5)), 0.085),  # knee
                (V((0.1 * sx, 0.01, 0.1)), 0.062),  # ankle
            ]
        )
        leg.ball((0.1 * sx, -0.05, 0.045), 0.075, (0.75, 1.6, 0.55))  # foot
        objects.append(leg.to_mesh(f"Leg_{side}", hip, skin, decimate=0.6))

    for side, sx in (("L", 1.0), ("R", -1.0)):
        lung = Part(f"mbLung{side}")
        lung.ball((0.08 * sx, 0.01, 1.32), 0.135, (0.6, 0.7, 1.15))
        lung.ball((0.09 * sx, 0.015, 1.235), 0.12, (0.68, 0.72, 0.8))
        center = V((0.08 * sx, 0.005, 1.29))
        objects.append(lung.to_mesh(f"Lung_{side}", center, lung_mat))

    heart = Part("mbHeart")
    heart.ball((0.018, -0.055, 1.285), 0.06, (1.0, 0.85, 1.0))
    heart.ball((0.04, -0.06, 1.255), 0.05)
    heart.ball((0.05, -0.065, 1.22), 0.03)  # apex, pointing to subject's left
    objects.append(heart.to_mesh("Heart", V((0.03, -0.06, 1.26)), heart_mat))

    # Organs sit behind the translucent skin in the hierarchy root so the web
    # app can address every part by name.
    root = bpy.data.objects.new("HumanTwin", None)
    bpy.context.scene.collection.objects.link(root)
    for obj in objects:
        obj.parent = root
    return objects


def export(out: Path, blend: Path | None) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    bpy.ops.export_scene.gltf(
        filepath=str(out),
        export_format="GLB",
        export_yup=True,
        export_apply=True,
        export_cameras=False,
        export_lights=False,
        export_animations=False,
    )
    if blend is not None:
        blend.parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(blend))


def main() -> None:
    out, blend = parse_args()
    clear_scene()
    objects = build()
    export(out, blend)
    verts = sum(len(o.data.vertices) for o in objects)
    print(f"[human_twin] exported {len(objects)} parts ({verts} vertices) -> {out}")
    print("[human_twin] parts:", ", ".join(sorted(o.name for o in objects)))


if __name__ == "__main__":
    main()
