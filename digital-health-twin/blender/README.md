# 3D asset: Blender

`build_human_twin.py` builds the twin's body in Blender from code and exports `frontend/public/models/human_twin.glb`. The asset is reproducible and can be reviewed like the rest of the code.

## Why separate named parts

The web app animates the body from live data, so each part is its own object with its origin at its joint:

| Object | Origin (pivot) | Driven by |
|---|---|---|
| `Head` | neck | temperature highlight |
| `Torso` | waist | state tint |
| `Arm_L`, `Arm_R` | shoulder | activity, swing |
| `Leg_L`, `Leg_R` | hip | activity, gait |
| `Heart` | heart centre | pulses at live heart rate |
| `Lung_L`, `Lung_R` | lung centre | expand at live breathing rate |

A single merged mesh could not be animated this way. The body is modelled with metaballs (smooth, organic joins), converted to meshes, decimated and shade-smoothed. The result is about 5.3k vertices and 0.13 MB.

## Rebuild or customise

```bash
# headless (Blender 3.6+ / 4.x on PATH)
blender -b -P blender/build_human_twin.py
# also save an editable .blend
blender -b -P blender/build_human_twin.py -- --blend blender/human_twin.blend
```

Or open Blender, go to **Scripting**, open `build_human_twin.py`, and press **Run Script**. The proportions are plain numbers in `build()`, so change the radii or positions and re-run. If you sculpt by hand instead, keep the object names and origins above, then use **File → Export → glTF 2.0 (.glb)** with *+Y Up* and *Apply Modifiers* to the same path.

The web app does not need Blender at runtime. If the GLB is missing it falls back to a procedural figure with the same part names (`frontend/src/twin3d/proceduralTwin.ts`).
