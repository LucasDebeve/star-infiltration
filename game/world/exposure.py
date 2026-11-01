"""Éclairement d'un point et visibilité qui en découle : dans l'ombre, on est moins repérable.

Mêmes lampes et même décroissance que le rendu (`ui/lighting.py`), mais calculé en un seul point, sans fenêtre : c'est ce
que lisent les gardes et les caméras (via `Player.light_factor`). Les murs arrêtent la lumière (ligne de vue lampe-point).
"""

from __future__ import annotations

import pygame

from game.settings import (
    AMBIENT_BLACKOUT,
    LIGHT_FALLOFF,
    VISIBILITY_FACTORS,
    VISIBILITY_LIT_MARGIN,
    VISIBILITY_SHADOW_MARGIN,
)
from game.world.raycast import line_of_sight

SHADOW, DIM, LIT = "shadow", "dim", "lit"


def luminance(color) -> float:
    """Clarté perçue (0..1) d'une couleur RVB."""
    return (0.2126 * color[0] + 0.7152 * color[1] + 0.0722 * color[2]) / 255.0


def falloff(distance: float, radius: float) -> float:
    return 0.0 if distance >= radius else (1.0 - distance / radius) ** LIGHT_FALLOFF


def light_at(tilemap, pos, base: float, sources) -> float:
    """Éclairement (0..1) en `pos`. `base` : clarté ambiante. `sources` : (position, rayon, couleur, intensité) de chaque lumière."""
    pos = pygame.Vector2(pos)
    total = base
    for source_pos, radius, color, intensity in sources:
        source_pos = pygame.Vector2(source_pos)
        distance = source_pos.distance_to(pos)
        if intensity <= 0 or distance >= radius:
            continue
        if line_of_sight(tilemap, source_pos, pos, light=True):
            total += luminance(color) * intensity * falloff(distance, radius)
    return min(1.0, total)


def visibility_factor(light: float) -> float:
    """Multiplicateur de la vitesse de détection : du noir complet (le plus discret) à la pleine lumière (le plus voyant)."""
    floor = luminance(AMBIENT_BLACKOUT)
    t = max(0.0, min(1.0, (light - floor) / (1.0 - floor)))
    dark, bright = VISIBILITY_FACTORS
    return dark + (bright - dark) * t


def visibility_zone(light: float, base: float) -> str:
    """Ombre, pénombre ou pleine lumière : ce que le HUD annonce. `base` : la clarté ambiante de la carte (sans aucune lampe)."""
    if light <= base + VISIBILITY_SHADOW_MARGIN:
        return SHADOW
    return LIT if light >= base + VISIBILITY_LIT_MARGIN else DIM
