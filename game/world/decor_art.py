"""Dessin animé du décor mural (les lanternes, qui brûlent même sans courant) et des grilles de vapeur.

Tout dépend du temps : rien n'est mis en cache.
"""
from __future__ import annotations

import math

import pygame

from game.settings import COLORS

GRILLE = (22, 26, 34)
GRILLE_EDGE = (58, 64, 78)


def lantern_flicker(phase: float, time: float) -> float:
    """Intensité (0.75..1) d'une flamme : deux sinusoïdes inégales, jamais synchrones d'une lanterne à l'autre."""
    return 0.875 + 0.125 * (math.sin(time * 9.0 + phase * 40) * 0.6 + math.sin(time * 5.3 + phase * 17) * 0.4)


def _shade(color, factor):
    return tuple(max(0, min(255, round(c * factor))) for c in color)


def draw_decor(surface: pygame.Surface, decor, rect: pygame.Rect, color, time: float) -> None:
    """Dessine une lanterne sur la tuile de mur `rect` (déjà à l'écran), un peu vers le passage qu'elle éclaire."""
    fx, fy = decor.face
    _draw_lantern(surface, (rect.centerx + fx * 4, rect.centery + fy * 4), decor, color, time)


def _draw_lantern(surface, center, decor, color, time) -> None:
    level = lantern_flicker(decor.phase, time)
    pygame.draw.circle(surface, COLORS["player_outline"], center, 8)
    pygame.draw.circle(surface, _shade(color, 0.55 * level), center, 7)
    pygame.draw.circle(surface, _shade(color, level), center, 5)
    pygame.draw.circle(surface, (255, 250, 230), center, 2)


def draw_vent(surface: pygame.Surface, rect: pygame.Rect, direction) -> None:
    """Grille d'aération au sol : des lattes sombres, dans le sens du jet."""
    grille = rect.inflate(-10, -10)
    pygame.draw.rect(surface, GRILLE, grille, border_radius=2)
    horizontal = direction[0] == 0  # le jet part vers le haut ou le bas : lattes horizontales
    for i in range(1, 4):
        if horizontal:
            y = grille.y + i * grille.h // 4
            pygame.draw.line(surface, GRILLE_EDGE, (grille.x + 1, y), (grille.right - 2, y), 1)
        else:
            x = grille.x + i * grille.w // 4
            pygame.draw.line(surface, GRILLE_EDGE, (x, grille.y + 1), (x, grille.bottom - 2), 1)
    pygame.draw.rect(surface, GRILLE_EDGE, grille, 1, border_radius=2)
