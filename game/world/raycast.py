"""Lancer de rayons sur la grille de tuiles (parcours DDA d'Amanatides & Woo).

Sert à la vision des gardes (ligne de vue bloquée par les murs), à la propagation du bruit, à la lumière
et au lissage des chemins. Fonctions pures : aucune dépendance à une fenêtre.

Deux notions d'obstacle :
    opaque (par défaut)  arrête la vue, la lumière et le bruit : murs, portes fermées, caisses, vaisseaux ;
    solide (`solid=True`) arrête le corps : tout l'opaque, plus le champ de force, que l'on voit à travers.
Un déplacement (dégagement d'un garde, lancer d'un leurre) utilise le solide ; la perception, l'opaque ; la lumière
(`light=True`) l'opaque sauf les vaisseaux, qu'elle survole : sans cela chaque vaisseau projetterait l'ombre d'un rectangle plein.
"""
from __future__ import annotations

import math
from typing import Iterator

import pygame


def traverse(tile_size: int, ox: float, oy: float, dx: float, dy: float, max_dist: float) -> Iterator[tuple[int, int, float]]:
    """Tuiles traversées par le rayon, dans l'ordre, avec la distance à laquelle il y entre.

    La tuile de départ est toujours produite (distance 0). Un rayon qui frôle exactement un coin
    ne touche pas les tuiles voisines de ce coin.
    """
    tx, ty = math.floor(ox / tile_size), math.floor(oy / tile_size)
    length = math.hypot(dx, dy)
    if length == 0:
        yield tx, ty, 0.0
        return
    dx, dy = dx / length, dy / length

    step_x, step_y = (1 if dx > 0 else -1), (1 if dy > 0 else -1)
    # Distance à parcourir pour franchir une tuile entière sur chaque axe, puis jusqu'à la prochaine frontière.
    delta_x = tile_size / abs(dx) if dx else math.inf
    delta_y = tile_size / abs(dy) if dy else math.inf
    next_x = ((tx + (step_x > 0)) * tile_size - ox) / dx if dx else math.inf
    next_y = ((ty + (step_y > 0)) * tile_size - oy) / dy if dy else math.inf

    dist = 0.0
    while dist <= max_dist:
        yield tx, ty, dist
        if next_x < next_y:
            dist = next_x
            next_x += delta_x
            tx += step_x
        else:
            dist = next_y
            next_y += delta_y
            ty += step_y


def cast_ray(tilemap, origin, direction, max_dist: float, *, solid: bool = False, light: bool = False) -> float:
    """Distance jusqu'au premier obstacle (ou `max_dist` si la voie est libre). `solid` : le champ de force en est un ;
    `light` : on suit la lumière, que les vaisseaux (bas, posés au sol) n'arrêtent pas."""
    blocks = tilemap.blocks_light if light else tilemap.is_solid if solid else tilemap.is_opaque
    for tx, ty, dist in traverse(tilemap.tile_size, origin[0], origin[1], direction[0], direction[1], max_dist):
        if blocks(tx, ty):
            return min(dist, max_dist)
    return max_dist


def line_of_sight(tilemap, a, b, *, solid: bool = False, light: bool = False) -> bool:
    """Vrai si rien n'arrête le segment [a, b] : par défaut la vue (le champ de force est transparent)."""
    a, b = pygame.Vector2(a), pygame.Vector2(b)
    dist = a.distance_to(b)
    return cast_ray(tilemap, a, b - a, dist, solid=solid, light=light) >= dist


def has_clearance(tilemap, a, b, radius: float) -> bool:
    """Vrai si un disque de rayon `radius` peut aller de `a` à `b` en ligne droite (il s'agit d'un déplacement :
    le champ de force le bloque).

    On teste le segment central et deux segments décalés latéralement de `radius`.
    """
    a, b = pygame.Vector2(a), pygame.Vector2(b)
    axis = b - a
    if axis.length_squared() == 0:
        return not tilemap.is_solid(*tilemap.world_to_tile(a.x, a.y))
    side = pygame.Vector2(-axis.y, axis.x).normalize() * radius
    return all(line_of_sight(tilemap, a + k * side, b + k * side, solid=True) for k in (0, 1, -1))


def count_solid_tiles(tilemap, a, b) -> int:
    """Nombre de tuiles opaques traversées par le segment [a, b] (pour atténuer le bruit : le champ de force n'étouffe rien)."""
    a, b = pygame.Vector2(a), pygame.Vector2(b)
    delta = b - a
    dist = delta.length()
    return sum(
        1
        for tx, ty, _ in traverse(tilemap.tile_size, a.x, a.y, delta.x, delta.y, dist)
        if tilemap.is_opaque(tx, ty)
    )
