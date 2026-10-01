"""Build the realistic anatomical twin (GLB) from BodyParts3D in Blender.

Source data
-----------
BodyParts3D, (c) The Database Center for Life Science, licensed under
CC Attribution-Share Alike 2.1 Japan (https://creativecommons.org/licenses/by-sa/2.1/jp/).
Mitsuhashi N. et al., "BodyParts3D: 3D structure database for anatomical
concepts", Nucleic Acids Res. 2009;37:D782-5. https://doi.org/10.1093/nar/gkn613

The meshes are segmented from real CT/MRI-based anatomy of one adult male
(about 930 structures). Download them first with:

    python scripts/fetch_bodyparts3d.py            # -> .cache/bodyparts3d/

What this script does
---------------------
1. Classifies every structure into a body system from its anatomical
   (FMA) name: skin, skeleton, muscles, brain, heart, lungs, airway,
   diaphragm, arteries, veins, digestive organs, urinary organs.
2. Simplifies each structure (decimation) to a per-group triangle budget
   so the whole body runs smoothly in a browser.
3. Joins each group into ONE named object whose origin is its own centre,
   so the web app can pulse the heart, inflate the lungs, move the
   diaphragm, light up muscles, etc. from live data.
4. Converts millimetres to metres, puts the feet at y = 0, and exports a
   Draco-compressed GLB plus a manifest of which structures went where.

Run
---
    blender -b -P blender/build_anatomy_twin.py -- --source .cache/bodyparts3d
    # options: --out frontend/public/models/anatomy_twin.glb  --quality 1.0  --blend anatomy.blend

Coordinates: Blender Z-up; subject faces -Y; subject's left is +X.
The glTF exporter converts to Y-up (subject faces +Z in three.js).
"""

from __future__ import annotations

import csv
import json
import sys
from collections import OrderedDict, defaultdict
from pathlib import Path

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# ------------------------------------------------------------------ grouping
# Order matters: the first matching rule wins.
# (group name, keywords in the lower-cased FMA name, triangle budget, material)
GROUPS: list[tuple[str, list[str], int, str]] = [
    ("Skin", ["skin"], 70_000, "skin"),
    # Brain before Heart: brain ventricles must not match the heart's "ventricle".
    ("Brain", ["cerebr", "gyrus", "brain", "cerebell", "thalam", "pons", "medulla oblongata", "hippocamp",
               "corpus callosum", "lobule", "insula", "fornix", "caudate", "putamen", "amygdala", "hypothal",
               "hemisphere", "choroid plexus", "peduncle", "precuneus", "cuneus", "lingual", "fusiform",
               "pallid", "claustrum", "spinal cord", "temporal pole", "frontal pole", "occipital pole",
               "white matter", "ventricle of brain", "pineal", "pituitary", "optic chiasm", "commissure",
               "septum pellucidum", "habenula", "mammillary", "tuber cinereum", "internal capsule", "colliculus",
               "interpeduncular", "lamina terminalis", "interventricular foramen",
               "lateral ventricle", "third ventricle", "fourth ventricle"], 35_000, "brain"),
    ("Heart", ["heart", "atrium", "ventricle", "valve", "coronary", "papillary", "septum of heart", "chordae"], 30_000, "heart"),
    ("Lung_R", ["lobe of right lung"], 12_000, "lung"),
    ("Lung_L", ["lobe of left lung"], 12_000, "lung"),
    ("Airway", ["trachea", "bronch", "larynx", "thyroid cartilage"], 5_000, "airway"),
    ("Diaphragm", ["diaphragm"], 5_000, "muscle"),
    ("Liver", ["liver", "gallbladder", "bile", "hepatic duct", "cystic duct"], 8_000, "liver"),
    ("Stomach", ["stomach", "esophag"], 6_000, "stomach"),
    ("Intestines", ["intestin", "colon", "duoden", "jejun", "ileum", "cecum", "rectum", "appendix", "sigmoid", "anal", "taenia"], 22_000, "intestine"),
    ("Pancreas", ["pancrea"], 3_000, "pancreas"),
    ("Spleen", ["spleen"], 3_000, "spleen"),
    ("Kidney_R", ["right kidney", "right ureter", "right adrenal", "right suprarenal", "right renal pelvis"], 4_000, "kidney"),
    ("Kidney_L", ["left kidney", "left ureter", "left adrenal", "left suprarenal", "left renal pelvis"], 4_000, "kidney"),
    ("Bladder", ["bladder", "urethra", "prostate"], 2_500, "bladder"),
    ("Arteries", ["artery", "aorta", "arterial", "brachiocephalic trunk", "celiac trunk", "pulmonary trunk"], 24_000, "artery"),
    ("Veins", ["vein", "vena cava", "venous", "sinus"], 18_000, "vein"),
    ("Skeleton", ["bone", "vertebra", "rib", "femur", "tibia", "fibula", "humerus", "radius", "ulna", "scapula",
                  "clavicle", "sternum", "sacrum", "coccyx", "patella", "skull", "mandible", "maxilla", "phalanx",
                  "metacarpal", "metatarsal", "carpal", "tarsal", "calcaneus", "talus", "cartilage", "hyoid",
                  "atlas", "axis", "manubrium", "cranium", "hip", "ilium", "ischium", "pubi", "intervertebral",
                  "disk", "tooth", "teeth", "trapezium", "trapezoid", "capitate", "hamate", "lunate", "scaphoid",
                  "pisiform", "triquetr", "cuboid", "cuneiform", "navicular", "sesamoid", "xiphoid", "ethmoid",
                  "sphenoid", "occipital bone", "parietal bone", "temporal bone", "frontal bone", "nasal bone",
                  "zygomatic", "vomer", "palatine", "lacrimal", "concha", "costal"], 110_000, "bone"),
    ("Muscles", ["muscle", "tendon", "fascia", "aponeurosis", "linea alba", "retinaculum", "ligament"], 110_000, "muscle"),
]
# Structures with no keyword match but a side ("Long head of right biceps brachii")
# or a muscle-part word are muscles in BodyParts3D.
SIDED_FALLBACK = "Muscles"
MUSCLE_HINTS = ["right ", "left ", "head of", "part of", "belly", "lumbrical", "interosse", "set of",
                "orbicularis", "masseter", "pterygoid", "rotator", "levator", "intertransvers", "interspinal"]
SKIP = ["eyeball", "lens", "cornea", "retina", "nerve", "ganglion", "lymph", "thymus", "penis",
        "corpus spongiosum", "corpus cavernosum", "hairs", "eyebrows", "gingiva", "labial part"]
SKIP_EXACT = {"ear"}

MATERIALS = {
    "skin": ((0.80, 0.69, 0.62, 0.22), 0.45),
    "heart": ((0.66, 0.12, 0.15, 1.0), 0.40),
    "lung": ((0.86, 0.56, 0.58, 1.0), 0.60),
    "airway": ((0.86, 0.80, 0.72, 1.0), 0.50),
    "brain": ((0.89, 0.74, 0.72, 1.0), 0.55),
    "liver": ((0.47, 0.17, 0.14, 1.0), 0.45),
    "stomach": ((0.84, 0.55, 0.47, 1.0), 0.50),
    "intestine": ((0.86, 0.62, 0.52, 1.0), 0.55),
    "pancreas": ((0.90, 0.75, 0.50, 1.0), 0.55),
    "spleen": ((0.45, 0.16, 0.22, 1.0), 0.45),
    "kidney": ((0.55, 0.20, 0.17, 1.0), 0.45),
    "bladder": ((0.88, 0.76, 0.48, 1.0), 0.50),
    "artery": ((0.75, 0.08, 0.10, 1.0), 0.40),
    "vein": ((0.18, 0.26, 0.62, 1.0), 0.40),
    "bone": ((0.91, 0.88, 0.80, 1.0), 0.70),
    "muscle": ((0.68, 0.24, 0.22, 1.0), 0.55),
}


def parse_args() -> tuple[Path, Path, float, Path | None]:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    opts = {"--source": str(ROOT / ".cache" / "bodyparts3d"),
            "--out": str(ROOT / "frontend" / "public" / "models" / "anatomy_twin.glb"),
            "--quality": "1.0", "--blend": ""}
    for i, arg in enumerate(argv):
        if arg in opts and i + 1 < len(argv):
            opts[arg] = argv[i + 1]
    return (Path(opts["--source"]).resolve(), Path(opts["--out"]).resolve(), float(opts["--quality"]),
            Path(opts["--blend"]).resolve() if opts["--blend"] else None)


def find_data_dir(source: Path) -> Path:
    for candidate in (source, source / "assets" / "BodyParts3D_data"):
        if (candidate / "stl").is_dir():
            return candidate
    raise SystemExit(f"BodyParts3D 'stl' folder not found under {source}. Run scripts/fetch_bodyparts3d.py first.")


def load_names(data_dir: Path) -> dict[str, str]:
    names: dict[str, str] = {}
    with open(data_dir / "FMA.csv", encoding="utf-8") as fh:
        for row in csv.reader(fh):
            if row and row[0].isdigit():
                names["FMA" + row[0]] = row[1]
    composite = data_dir / "composite_parts.txt"
    if composite.exists():
        for line in composite.read_text(encoding="utf-8").splitlines()[1:]:
            parts = line.split("\t")
            if len(parts) == 4:
                names.setdefault(parts[0], parts[1])
                names.setdefault(parts[2], parts[3])
    return names


def classify(name: str) -> str | None:
    n = name.lower()
    if n in SKIP_EXACT or any(s in n for s in SKIP):
        return None
    for group, keys, _, _ in GROUPS:
        if any(k in n for k in keys):
            return group
    if any(h in n for h in MUSCLE_HINTS):
        return SIDED_FALLBACK
    return None


# ------------------------------------------------------------------ blender
def clear_scene() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.materials):
        for block in list(coll):
            coll.remove(block)


def make_material(key: str) -> bpy.types.Material:
    rgba, rough = MATERIALS[key]
    mat = bpy.data.materials.new(f"M_{key}")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = rgba
    bsdf.inputs["Roughness"].default_value = rough
    if rgba[3] < 1:
        bsdf.inputs["Alpha"].default_value = rgba[3]
        mat.blend_method = "BLEND"
    return mat


def import_stl(path: Path) -> bpy.types.Object:
    if hasattr(bpy.ops.wm, "stl_import"):
        bpy.ops.wm.stl_import(filepath=str(path))
    else:  # Blender < 4.1
        bpy.ops.import_mesh.stl(filepath=str(path))
    return bpy.context.selected_objects[0]


def decimate(obj: bpy.types.Object, ratio: float) -> None:
    if ratio >= 0.999:
        return
    mod = obj.modifiers.new("decimate", "DECIMATE")
    mod.ratio = max(ratio, 0.002)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=mod.name)


def build_group(group: str, files: list[Path], budget: int, mat: bpy.types.Material) -> bpy.types.Object:
    objs = []
    for f in files:
        bpy.ops.object.select_all(action="DESELECT")
        objs.append(import_stl(f))
    total = sum(len(o.data.polygons) for o in objs)
    ratio = budget / max(total, 1)
    for o in objs:
        decimate(o, ratio)
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.name = obj.data.name = group
    # mm -> m and centre the body: x symmetric, y around the torso, feet at z = 0
    obj.scale = (0.001, 0.001, 0.001)
    obj.location = (0.0, 0.096, 0.0135)
    bpy.ops.object.transform_apply(location=True, rotation=False, scale=True)
    bpy.ops.object.shade_smooth()
    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    print(f"[anatomy] {group:<11} {len(files):4d} parts {total:>9,d} -> {len(obj.data.polygons):>7,d} tris")
    return obj


def main() -> None:
    source, out, quality, blend = parse_args()
    data_dir = find_data_dir(source)
    names = load_names(data_dir)
    budgets = {g: int(b * quality) for g, _, b, _ in GROUPS}
    mat_keys = {g: m for g, _, _, m in GROUPS}

    groups: dict[str, list[Path]] = defaultdict(list)
    manifest: dict[str, list[dict[str, str]]] = OrderedDict((g, []) for g, *_ in GROUPS)
    skipped = []
    for stl in sorted((data_dir / "stl").glob("*.stl")):
        fid = stl.stem
        name = names.get(fid, "")
        group = classify(name) if name else None
        if group is None:
            skipped.append({"id": fid, "name": name or "?"})
            continue
        groups[group].append(stl)
        manifest[group].append({"id": fid, "name": name})

    clear_scene()
    root = bpy.data.objects.new("AnatomyTwin", None)
    bpy.context.scene.collection.objects.link(root)
    materials = {k: make_material(k) for k in MATERIALS}
    for group, *_ in GROUPS:
        if groups.get(group):
            obj = build_group(group, groups[group], budgets[group], materials[mat_keys[group]])
            obj.parent = root

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
        export_draco_mesh_compression_enable=True,
        export_draco_mesh_compression_level=7,
        export_draco_position_quantization=14,
        export_draco_normal_quantization=10,
    )
    manifest_path = HERE / "anatomy_manifest.json"
    manifest_path.write_text(json.dumps(
        {"source": "BodyParts3D 3.0 (c) DBCLS, CC BY-SA 2.1 JP",
         "groups": {g: {"count": len(v), "structures": v} for g, v in manifest.items()},
         "skipped": skipped}, indent=1), encoding="utf-8")
    if blend:
        bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    print(f"[anatomy] wrote {out} ({out.stat().st_size / 1e6:.1f} MB); manifest {manifest_path}")


if __name__ == "__main__":
    main()
