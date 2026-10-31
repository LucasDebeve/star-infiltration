"""Point d'entrée : `python main.py` (ou l'exécutable empaqueté).

Options : `--version` (affiche la version), `--check` (contrôle les cartes et les sons sans ouvrir de fenêtre),
`--portable` (enregistre préférences et progression à côté du jeu, dans un dossier `data/`),
`--dev` (mode développeur : menu pour jouer n'importe quel niveau, invincibilité... ; absent des exécutables livrés).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from game.core.preferences import HOME_ENV
from game.settings import TITLE, VERSION


def app_dir() -> Path:
    """Dossier du jeu : celui de l'exécutable empaqueté, sinon celui des sources."""
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="star-infiltration", description=f"{TITLE}, un jeu d'infiltration en vue de dessus.")
    parser.add_argument("--version", action="store_true", help="affiche la version et quitte")
    parser.add_argument("--check", action="store_true", help="contrôle la campagne, les cartes et les sons, puis quitte (code 1 en cas de problème)")
    parser.add_argument("--portable", action="store_true", help="enregistre préférences et progression dans le dossier `data/` à côté du jeu")
    parser.add_argument("--dev", action="store_true", help="mode développeur (menu des niveaux, outils de test) ; ignoré dans un exécutable empaqueté")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args([] if argv is None else argv)  # appelé sans arguments (tests, import), on ne lit pas ceux de l'appelant
    if args.version:
        print(f"{TITLE} {VERSION}")
        return 0
    if args.portable:
        os.environ.setdefault(HOME_ENV, str(app_dir() / "data"))
    if args.check:
        from game.selfcheck import run_checks

        problems = run_checks()
        for problem in problems:
            print(f"PROBLÈME : {problem}")
        print("Contrôle terminé : " + ("aucun problème." if not problems else f"{len(problems)} problème(s)."))
        return 1 if problems else 0

    from game.core.game import Game
    from game.dev import DevTools, dev_requested
    from game.scenes.main_menu import MainMenuScene

    game = Game(dev=DevTools() if dev_requested(args.dev) else None)
    game.scenes.push(MainMenuScene(game))
    game.run()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
