"""Mode développeur : outils de test (jouer n'importe quel niveau, invincibilité, fantôme, raccourcis d'objectif).

Il n'existe qu'en développement : on l'active avec `python main.py --dev` (ou la variable d'environnement `STAR_INFILTRATION_DEV=1`),
et **jamais** dans un exécutable empaqueté ni dans la version web. Les parties lancées depuis le menu développeur ne comptent pas
pour la progression (elles n'ont pas de mission : pas de score, pas d'enregistrement). Logique pure, sans fenêtre.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import pygame

DEV_ENV = "STAR_INFILTRATION_DEV"
# Touches des outils en jeu (en plus de F3 « debug » et F4 « éclairage », qui existent pour tous).
DEV_KEYS = {
    "invincible": pygame.K_F5,
    "ghost": pygame.K_F6,
    "loadout": pygame.K_F7,
    "objective": pygame.K_F8,
    "goto_goal": pygame.K_F9,
    "goto_exit": pygame.K_F10,
}
DEV_LABELS = {
    "invincible": "invincible",
    "ghost": "fantôme",
    "loadout": "équipement complet",
    "objective": "objectif accompli",
    "goto_goal": "aller à l'objectif",
    "goto_exit": "aller à la sortie",
}


def dev_allowed() -> bool:
    """Faux dans un exécutable empaqueté et dans le navigateur : le mode développeur n'y est pas livré."""
    return not getattr(sys, "frozen", False) and sys.platform != "emscripten"


def dev_requested(flag: bool = False, environ=None) -> bool:
    """Vrai si le mode développeur est demandé (option `--dev` ou variable d'environnement) et permis."""
    environ = os.environ if environ is None else environ
    wanted = flag or environ.get(DEV_ENV, "").strip().lower() in ("1", "true", "yes", "oui", "on")
    return wanted and dev_allowed()


@dataclass
class DevTools:
    invincible: bool = False  # les gardes ne capturent plus
    ghost: bool = False  # gardes et caméras ne voient ni n'entendent le joueur

    def toggle(self, name: str) -> bool:
        setattr(self, name, not getattr(self, name))
        return getattr(self, name)

    def active(self) -> list[str]:
        return [DEV_LABELS[name] for name in ("invincible", "ghost") if getattr(self, name)]
