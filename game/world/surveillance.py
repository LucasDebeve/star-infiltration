"""Caméras de surveillance : leur déclaration dans la carte (directive `@camera`). Données pures.

    @camera x,y -> N|E|S|O [groupe] [amplitude]
x,y est la tuile de **mur** qui porte la caméra ; la direction est celle où elle regarde (O = ouest) ; le groupe est une
lettre (a par défaut) que les terminaux désignent (`@terminal ... cameras:a`) ; l'amplitude du balayage est en degrés
de chaque côté de l'axe (42 par défaut).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from game.settings import CAMERA_SWEEP

DIRECTIONS = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "O": (-1, 0)}
DEFAULT_GROUP = "a"
MAX_SWEEP = 85.0  # degrés : au-delà, la caméra se retournerait vers son propre mur


@dataclass(frozen=True)
class CameraSpec:
    tile: tuple[int, int]
    facing: str
    group: str = DEFAULT_GROUP
    sweep: float = math.degrees(CAMERA_SWEEP)  # degrés de chaque côté de l'axe


def parse_camera(tile: tuple[int, int], rest: str) -> CameraSpec:
    """Lit `N [groupe] [amplitude]` (ValueError en français si c'est illisible)."""
    tokens = rest.split()
    if not tokens or tokens[0] not in DIRECTIONS:
        raise ValueError(f"direction attendue parmi {', '.join(DIRECTIONS)} (N, E, S ou O)")
    group, sweep = DEFAULT_GROUP, math.degrees(CAMERA_SWEEP)
    for token in tokens[1:]:
        if len(token) == 1 and token.isalpha() and token.islower():
            group = token
            continue
        try:
            sweep = float(token)
        except ValueError:
            raise ValueError(f"{token!r} n'est ni une lettre de groupe ni une amplitude en degrés") from None
        if not 0 <= sweep <= MAX_SWEEP:
            raise ValueError(f"amplitude {sweep:g}° hors de 0..{MAX_SWEEP:g}")
    return CameraSpec(tile, tokens[0], group, sweep)
