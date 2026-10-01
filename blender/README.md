# 3D anatomical twin: Blender build

`build_anatomy_twin.py` builds `frontend/public/models/anatomy_twin.glb`, the realistic anatomy the dashboard renders, from **BodyParts3D**. BodyParts3D contains about 930 anatomical structures segmented from real scan data of one adult male (CC BY-SA 2.1 JP, © DBCLS).

The built GLB is already in the repository. You only need Blender to rebuild or customise it.

## What the script does

1. Reads every structure's anatomical (FMA) name and sorts it into a body system: skin, skeleton (320 bones and cartilages), muscles (about 400), brain, heart, left and right lungs, airway, diaphragm, arteries, veins, liver, stomach, intestines, pancreas, spleen, kidneys and bladder. Eyes, hair, nerves and similar structures are skipped.
2. Simplifies each structure to a per-group triangle budget (about 580k triangles for the whole body, from about 27 million).
3. Joins each group into **one named object with its origin at its own centre**, so the web app can address and animate it:

| Object | What drives it in the app |
|---|---|
| `Heart` | Beats at the live heart rate (scale pulse); status glow |
| `Arteries` | Pulse wave with each beat; colour follows SpO₂ when measured |
| `Lung_L`, `Lung_R` | Expand at the live breathing rate; status glow |
| `Diaphragm` | Moves down and up with each breath |
| `Muscles` | Glow with measured movement intensity |
| `Brain` | Glows during sleep |
| `Skin` | Warms when temperature is unusual (when measured) |
| `Veins`, `Airway`, `Skeleton`, `Liver`, `Stomach`, `Intestines`, `Pancreas`, `Spleen`, `Kidney_L`, `Kidney_R`, `Bladder` | Not monitored by wearables: anatomy only, never animated |

4. Converts millimetres to metres, puts the feet at height 0, and exports a Draco-compressed GLB (about 9 MB). The Draco decoder is bundled in `frontend/public/draco/`, so the app works offline. It also writes `anatomy_manifest.json`, listing every structure that went into each object (for attribution and review).

## Rebuild

```bash
python scripts/fetch_bodyparts3d.py                    # ~1 GB of STL meshes -> .cache/bodyparts3d
blender -b -P blender/build_anatomy_twin.py -- --source .cache/bodyparts3d
# options: --quality 0.5 (lighter model)  --blend anatomy.blend (save an editable scene)
```

Or open Blender, go to **Scripting**, open the script, and run it after editing `ROOT/.cache/bodyparts3d` if needed. To change what is shown, edit the `GROUPS` table (keywords, triangle budget and material per object). A full build takes 10–15 minutes on a laptop.

## Licence

The meshes and the derived GLB are under **CC BY-SA 2.1 JP**. Keep the attribution: "BodyParts3D, © The Database Center for Life Science, licensed under CC Attribution-Share Alike 2.1 Japan".
