#!/usr/bin/env python3
from pathlib import Path
import os
import shutil
import sys

try:
    import PyInstaller.__main__
except ImportError:
    raise SystemExit("PyInstaller n'est pas installé. Lance pip install pyinstaller.")

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
BUILD = ROOT / "build"

for p in [DIST, BUILD]:
    if p.exists():
        shutil.rmtree(p)

sep = os.pathsep

args = [
    str(ROOT / "castle_heightmap_studio.py"),
    "--name=CastleHeightMapStudio",
    "--onefile",
    "--windowed",
    "--clean",
    "--noconfirm",
    "--collect-all=cadquery",
    "--collect-all=OCP",
    "--collect-all=matplotlib",
    f"--add-data={ROOT / 'docs'}{sep}docs",
    f"--add-data={ROOT / 'assets'}{sep}assets",
    f"--add-data={ROOT / 'examples'}{sep}examples",
    f"--add-data={ROOT / 'update_config.json'}{sep}.",
]

if sys.platform.startswith("win"):
    args.append(f"--icon={ROOT / 'assets' / 'castle_heightmap_studio.ico'}")
else:
    args.append(f"--icon={ROOT / 'assets' / 'castle_heightmap_studio.png'}")

PyInstaller.__main__.run(args)
