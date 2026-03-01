#!/usr/bin/env bash
set -euo pipefail

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .[dev]
cp -n .env.example .env || true

echo "Setup complete. Activate with: source .venv/bin/activate"
