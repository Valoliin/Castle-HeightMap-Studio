#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

echo "=== Castle HeightMap Studio - Build AppImage ==="

if [ ! -d ".venv" ]; then
    echo "Le .venv n'existe pas. Lance d'abord ./install_linux.sh"
    exit 1
fi

source .venv/bin/activate
python -m pip install --upgrade pyinstaller

rm -rf build dist AppDir

# L'AppImage utilise un build one-folder interne.
python -m PyInstaller \
    castle_heightmap_studio.py \
    --name CastleHeightMapStudio \
    --windowed \
    --clean \
    --noconfirm \
    --collect-all cadquery \
    --collect-all OCP \
    --collect-all casadi \
    --hidden-import casadi._casadi \
    --hidden-import _casadi \
    --collect-all matplotlib \
    --collect-submodules PIL \
    --hidden-import PIL.ImageTk \
    --hidden-import PIL._tkinter_finder \
    --additional-hooks-dir "build_tools/pyinstaller_hooks" \
    --runtime-hook "build_tools/rthook_casadi.py" \
    --add-data "docs:docs" \
    --add-data "assets:assets" \
    --add-data "examples:examples" \
    --add-data "update_config.json:."

mkdir -p AppDir/usr/bin
cp -a dist/CastleHeightMapStudio/. AppDir/usr/bin/
cp packaging/linux/AppRun AppDir/AppRun
cp packaging/linux/castle-heightmap-studio.desktop AppDir/castle-heightmap-studio.desktop
cp assets/castle_heightmap_studio.png AppDir/castle-heightmap-studio.png
chmod +x AppDir/AppRun

APPIMAGETOOL="$ROOT/build_tools/appimagetool-x86_64.AppImage"

if [ ! -x "$APPIMAGETOOL" ]; then
    echo "Téléchargement de appimagetool..."
    curl -L \
      "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage" \
      -o "$APPIMAGETOOL"
    chmod +x "$APPIMAGETOOL"
fi

mkdir -p dist
ARCH=x86_64 "$APPIMAGETOOL" --appimage-extract-and-run \
    AppDir \
    dist/CastleHeightMapStudio-x86_64.AppImage

echo "Self-test de l'AppImage..."
APPIMAGE_EXTRACT_AND_RUN=1 dist/CastleHeightMapStudio-x86_64.AppImage --self-test

echo
echo "AppImage créée : dist/CastleHeightMapStudio-x86_64.AppImage"
