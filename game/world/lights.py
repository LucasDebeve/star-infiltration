"""Sources de lumière : lampes de plafond placées automatiquement, scintillement, polygone d'ombres.

Logique pure (sans fenêtre) : le rendu est dans `game/ui/lighting.py`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pygame

from game.settings import LAMP_FLICKER_ONE_IN, LAMP_SPACING
from game.world.raycast import cast_ray

MIN_FREE_TILES_PER_BLOCK = 4  # pas de lampe dans un recoin
MIN_FREE_NEIGHBORS = 4  # une lampe ne colle pas à un mur (un couloir de 2 tuiles de large suffit)


@dataclass(frozen=True)
class Lamp:
    tile: tuple[int, int]
    color: tuple[int, int, int]
    flickers: bool
    phase: float  # déphasage : les lampes ne battent pas toutes ensemble

    def position(self, tile_size: int) -> pygame.Vector2:
        return pygame.Vector2((self.tile[0] + 0.5) * tile_size, (self.tile[1] + 0.5) * tile_size)


@dataclass(frozen=True)
class LightSpec:
    """Une lumière dynamique, décrite pour une image (le joueur, un garde, un terminal...)."""

    pos: pygame.Vector2
    radius: float
    color: tuple[int, int, int]
    intensity: float = 1.0
    shadowed: bool = False  # vrai : les murs arrêtent la lumière
    facing: float | None = None  # vrai cône (lampe torche) si renseigné, avec `fov`
    fov: float = 0.0


def _free_neighbors(tilemap, tx: int, ty: int) -> int:
    return sum(not tilemap.is_solid(tx + dx, ty + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if (dx, dy) != (0, 0))


def _tile_hash(tx: int, ty: int) -> int:
    """Mélange simple et stable (pas le `hash` de Python, qui varie) : sert à répartir les lampes défaillantes."""
    h = (tx * 374761393 + ty * 668265263) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return h ^ (h >> 16)


def place_ceiling_lamps(tilemap, spacing: int = LAMP_SPACING) -> list[Lamp]:
    """Une lampe par bloc de `spacing` × `spacing` tuiles, au plus dégagé des endroits du bloc (à égalité, le plus central).

    Déterministe : la même carte donne toujours les mêmes lampes (teinte par salle, scintillement fixe).
    """
    lamps = []
    tints = tilemap.theme.lamp_tints
    for by in range(0, tilemap.height, spacing):
        for bx in range(0, tilemap.width, spacing):
            cx, cy = bx + (spacing - 1) / 2, by + (spacing - 1) / 2
            free = [
                (x, y)
                for y in range(by, min(by + spacing, tilemap.height))
                for x in range(bx, min(bx + spacing, tilemap.width))
                if not tilemap.is_solid(x, y) and tilemap.field_at(x, y) is None  # pas de lampe dans un champ commutable
            ]
            if len(free) < MIN_FREE_TILES_PER_BLOCK:
                continue
            roomy = [t for t in free if _free_neighbors(tilemap, *t) >= MIN_FREE_NEIGHBORS]
            if not roomy:
                continue
            tile = min(roomy, key=lambda t: (-_free_neighbors(tilemap, *t), math.hypot(t[0] - cx, t[1] - cy), t))
            lamps.append(
                Lamp(
                    tile=tile,
                    color=tints[tilemap.region_of(*tile) % len(tints)],
                    flickers=_tile_hash(*tile) % LAMP_FLICKER_ONE_IN == 0,
                    phase=(tile[0] * 0.37 + tile[1] * 0.61) % math.tau,
                )
            )
    return lamps


def flicker_factor(lamp: Lamp, t: float) -> float:
    """Intensité (0..1) de la lampe à l'instant `t` : stable, sauf les lampes défaillantes qui s'éteignent par à-coups."""
    if not lamp.flickers:
        return 1.0
    noise = math.sin(t * 7.3 + lamp.phase) + math.sin(t * 12.1 + 2 * lamp.phase) + math.sin(t * 3.7 + 3 * lamp.phase)
    dip = max(0.0, min(1.0, noise - 1.6))  # n'arrive que quand les trois ondes s'alignent : rare et brutal
    return 1.0 - 0.85 * dip


def light_polygon(tilemap, center, radius: float, rays: int) -> list[tuple[float, float]]:
    """Contour (coordonnées monde) de la zone qu'éclaire une lumière : les murs arrêtent chaque rayon."""
    center = pygame.Vector2(center)
    points = []
    for i in range(rays):
        angle = math.tau * i / rays
        direction = (math.cos(angle), math.sin(angle))
        dist = cast_ray(tilemap, center, direction, radius, light=True)
        points.append((center.x + direction[0] * dist, center.y + direction[1] * dist))
    return points
