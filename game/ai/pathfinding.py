"""Pathfinding A* sur la grille de tuiles, avec lissage du chemin.

Déplacements à 8 directions ; une diagonale n'est permise que si les deux tuiles adjacentes
sont libres (pas de « coupe-coin » à travers un angle de mur).
Fonctions pures : seule `tilemap.is_solid` / `tile_size` / `world_to_tile` est utilisée.
"""
from __future__ import annotations

import heapq
import math
from typing import Iterator, Sequence

import pygame

from game.world.raycast import has_clearance

Tile = tuple[int, int]

_SQRT2 = math.sqrt(2)
_STRAIGHT = ((1, 0), (-1, 0), (0, 1), (0, -1))
_DIAGONAL = ((1, 1), (1, -1), (-1, 1), (-1, -1))


def _octile(a: Tile, b: Tile) -> float:
    """Heuristique admissible et cohérente pour une grille à 8 directions."""
    dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
    return dx + dy + (_SQRT2 - 2) * min(dx, dy)


def _neighbors(tilemap, tile: Tile) -> Iterator[tuple[Tile, float]]:
    x, y = tile
    is_solid = tilemap.is_solid
    for dx, dy in _STRAIGHT:
        if not is_solid(x + dx, y + dy):
            yield (x + dx, y + dy), 1.0
    for dx, dy in _DIAGONAL:
        if not (is_solid(x + dx, y + dy) or is_solid(x + dx, y) or is_solid(x, y + dy)):
            yield (x + dx, y + dy), _SQRT2


def find_path(tilemap, start: Tile, goal: Tile) -> list[Tile]:
    """Plus court chemin de tuiles de `start` à `goal` (inclus), ou `[]` s'il n'y en a pas."""
    if tilemap.is_solid(*start) or tilemap.is_solid(*goal):
        return []
    if start == goal:
        return [start]
    if not tilemap.same_region(start, goal):  # sinon l'A* explorerait toute la zone pour rien
        return []

    cost = {start: 0.0}
    parent: dict[Tile, Tile] = {}
    closed: set[Tile] = set()
    frontier = [(_octile(start, goal), start)]
    while frontier:
        _, current = heapq.heappop(frontier)
        if current == goal:
            path = [current]
            while current in parent:
                current = parent[current]
                path.append(current)
            path.reverse()
            return path
        if current in closed:  # doublon périmé laissé dans le tas
            continue
        closed.add(current)
        for neighbor, step in _neighbors(tilemap, current):
            new_cost = cost[current] + step
            if new_cost < cost.get(neighbor, math.inf):
                cost[neighbor] = new_cost
                parent[neighbor] = current
                heapq.heappush(frontier, (new_cost + _octile(neighbor, goal), neighbor))
    return []


def nearest_walkable(tilemap, tile: Tile, max_radius: int = 4) -> Tile | None:
    """Tuile libre la plus proche de `tile` (anneaux successifs), ou None si rien dans le rayon."""
    if not tilemap.is_solid(*tile):
        return tile
    best: Tile | None = None
    best_dist = math.inf
    for radius in range(1, max_radius + 1):
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if max(abs(dx), abs(dy)) != radius:
                    continue
                candidate = (tile[0] + dx, tile[1] + dy)
                dist = math.hypot(dx, dy)
                if dist < best_dist and not tilemap.is_solid(*candidate):
                    best, best_dist = candidate, dist
        if best is not None:  # premier anneau non vide : au pire quelques pixels d'écart avec le vrai plus proche
            return best
    return None


def smooth_path(tilemap, points: Sequence[pygame.Vector2], radius: float) -> list[pygame.Vector2]:
    """Supprime les points intermédiaires inutiles (« string pulling »).

    Depuis un point d'ancrage, on avance tant que le point suivant reste visible en ligne droite,
    puis on garde le dernier point visible comme nouvelle ancre : un seul passage, O(n) tests.
    `radius` est le rayon de l'entité : un raccourci n'est pris que si elle passe sans frôler un mur.
    """
    if len(points) <= 2:
        return list(points)
    smoothed = [points[0]]
    anchor = 0
    while anchor < len(points) - 1:
        far = anchor + 1  # le point voisin est toujours atteignable (c'est un pas de l'A*)
        while far + 1 < len(points) and has_clearance(tilemap, points[anchor], points[far + 1], radius):
            far += 1
        smoothed.append(points[far])
        anchor = far
    return smoothed


def plan_route(tilemap, start: pygame.Vector2, goal: pygame.Vector2, radius: float) -> list[pygame.Vector2] | None:
    """Chemin en coordonnées monde de `start` à `goal`, lissé.

    Renvoie la liste des points à rejoindre (sans la position de départ) :
    `[]` si l'on est déjà arrivé, `None` si `goal` est inaccessible.
    """
    ts = tilemap.tile_size
    start_tile = tilemap.world_to_tile(start.x, start.y)
    goal_tile = nearest_walkable(tilemap, tilemap.world_to_tile(goal.x, goal.y))
    if goal_tile is None:
        return None
    tiles = find_path(tilemap, start_tile, goal_tile)
    if not tiles:
        return None
    if len(tiles) == 1:
        return []
    centers = [pygame.Vector2((tx + 0.5) * ts, (ty + 0.5) * ts) for tx, ty in tiles]
    centers[0] = pygame.Vector2(start)  # on part de la vraie position, pas du centre de la tuile
    return smooth_path(tilemap, centers, radius)[1:]
