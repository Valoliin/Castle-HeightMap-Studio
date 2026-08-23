#!/usr/bin/env bash
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

echo "=== Castle HeightMap Studio v4.1 ==="
sudo apt update
sudo apt install -y python3-tk python3-venv

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

echo
echo "Installation terminee."
echo "Lance le logiciel avec : ./run.sh"
