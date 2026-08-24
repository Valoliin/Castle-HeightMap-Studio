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
HOOKS = ROOT / "build_tools" / "pyinstaller_hooks"
CASADI_RUNTIME_HOOK = ROOT / "build_tools" / "rthook_casadi.py"

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
    "--collect-all=casadi",
    "--hidden-import=casadi._casadi",
    "--hidden-import=_casadi",
    "--collect-all=matplotlib",
    f"--additional-hooks-dir={HOOKS}",
    f"--runtime-hook={CASADI_RUNTIME_HOOK}",
    f"--add-data={ROOT / 'docs'}{sep}docs",
    f"--add-data={ROOT / 'assets'}{sep}assets",
    f"--add-data={ROOT / 'examples'}{sep}examples",
    f"--add-data={ROOT / 'update_config.json'}{sep}.",
]

if sys.platform.startswith("win"):
    args.append(f"--icon={ROOT / 'assets' / 'castle_heightmap_studio.ico'}")
else:
    args.append(f"--icon={ROOT / 'assets' / 'castle_heightmap_studio.png'}")

# Fail early if the build environment itself cannot load the dependency.
try:
    import casadi
    import casadi._casadi
    import cadquery
    print(f"Build dependency check: CasADi {getattr(casadi, '__version__', '?')} OK")
    print(f"Build dependency check: CadQuery {getattr(cadquery, '__version__', '?')} OK")
except Exception as exc:
    raise SystemExit(f"Build dependency check failed: {exc!r}")

PyInstaller.__main__.run(args)
