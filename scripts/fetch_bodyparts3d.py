"""Download the BodyParts3D anatomy meshes used to build the 3D twin.

The built model (frontend/public/models/anatomy_twin.glb) is already in the
repository, so you only need this to REBUILD or customise it in Blender.

Source: BodyParts3D 3.0, (c) The Database Center for Life Science (DBCLS),
CC Attribution-Share Alike 2.1 Japan. Mirror used:
https://github.com/Kevin-Mattheus-Moerman/BodyParts3D (STL conversion of the
original OBJ files). About 1 GB download.

Usage (from the repository root; needs git):
    python scripts/fetch_bodyparts3d.py            # -> .cache/bodyparts3d/
then:
    blender -b -P blender/build_anatomy_twin.py -- --source .cache/bodyparts3d
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO = "https://github.com/Kevin-Mattheus-Moerman/BodyParts3D"
ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / ".cache" / "bodyparts3d"
DATA = "assets/BodyParts3D_data"


def run(*args: str, cwd: Path | None = None) -> None:
    print("+", " ".join(args))
    subprocess.run(args, cwd=cwd, check=True)


def main() -> None:
    if (DEST / "stl").is_dir() and any((DEST / "stl").glob("*.stl")):
        print(f"already downloaded: {DEST}")
        return
    clone = ROOT / ".cache" / "bp3d-src"
    if clone.exists():
        shutil.rmtree(clone)
    clone.parent.mkdir(parents=True, exist_ok=True)
    run("git", "clone", "--depth", "1", "--filter=blob:none", "--sparse", REPO, str(clone))
    run("git", "sparse-checkout", "set", "--no-cone",
        f"{DATA}/stl/*.stl", f"{DATA}/FMA.csv", f"{DATA}/composite_parts.txt", f"{DATA}/LICENSE_content",
        cwd=clone)
    DEST.mkdir(parents=True, exist_ok=True)
    src = clone / DATA
    for item in ("FMA.csv", "composite_parts.txt", "LICENSE_content"):
        shutil.copy2(src / item, DEST / item)
    if (DEST / "stl").exists():
        shutil.rmtree(DEST / "stl")
    shutil.move(str(src / "stl"), str(DEST / "stl"))
    shutil.rmtree(clone)
    print(f"done: {len(list((DEST / 'stl').glob('*.stl')))} meshes in {DEST}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(f"download failed: {exc}")
