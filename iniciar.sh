#!/usr/bin/env bash
cd "$(dirname "$0")"
command -v ffmpeg >/dev/null || { echo "Instala ffmpeg (Mac: brew install ffmpeg | Linux: sudo apt install ffmpeg)"; exit 1; }
command -v deno >/dev/null || echo "Aviso: instala Deno (curl -fsSL https://deno.land/install.sh | sh) si YouTube da error."
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q -U -r requirements.txt
python app.py
