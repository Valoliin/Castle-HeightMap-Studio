#!/usr/bin/env bash
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"
if [ ! -d ".venv" ]; then
    echo "L'environnement .venv n'existe pas. Lance d'abord ./install_linux.sh"
    exit 1
fi
source .venv/bin/activate
python castle_heightmap_studio.py
