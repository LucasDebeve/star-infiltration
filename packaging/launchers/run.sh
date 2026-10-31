#!/bin/sh
# Lance le jeu depuis les sources (Linux, macOS). Crée un environnement virtuel au premier lancement.
cd "$(dirname "$0")" || exit 1
if [ ! -d .venv ]; then
  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt || exit 1
fi
exec .venv/bin/python main.py "$@"
