"""Perception des gardes : vue (cône + lancer de rayons) et ouïe (rayon de bruit atténué par les murs).

Fonctions pures : tout est passé en paramètres, rien n'est lu dans `settings` à l'intérieur.
"""

from __future__ import annotations

import math

import pygame

from game.ai.steering import angle_difference
from game.settings import HEARING_WALL_PENALTY
from game.world.raycast import cast_ray, count_solid_tiles, line_of_sight


def can_see(tilemap, eye, facing: float, fov: float, view_range: float, point) -> bool:
    """Vrai si `point` est dans le cône (portée, angle) et qu'aucun mur ne s'interpose.

    `facing` et `fov` sont en radians ; `fov` est l'ouverture totale du cône.
    """
    eye, point = pygame.Vector2(eye), pygame.Vector2(point)
    offset = point - eye
    dist_sq = offset.length_squared()
    if dist_sq > view_range * view_range:
        return False
    if dist_sq > 0 and abs(angle_difference(math.atan2(offset.y, offset.x), facing)) > fov / 2:
        return False
    return line_of_sight(tilemap, eye, point)


def hears(tilemap, listener, source, radius: float, wall_penalty: float = HEARING_WALL_PENALTY) -> bool:
    """Vrai si un bruit de rayon `radius` émis en `source` parvient à `listener`.

    Chaque tuile solide traversée « coûte » `wall_penalty` pixels de portée en plus de la distance.
    """
    if radius <= 0:
        return False
    listener, source = pygame.Vector2(listener), pygame.Vector2(source)
    dist = listener.distance_to(source)
    if dist > radius:  # sortie rapide : le plus souvent, le garde est simplement trop loin
        return False
    return dist + wall_penalty * count_solid_tiles(tilemap, listener, source) <= radius


def vision_points(tilemap, eye, facing: float, fov: float, view_range: float, rays: int) -> list[tuple[float, float]]:
    """Contour du cône de vision : un point par rayon, arrêté au premier mur (pour le dessin)."""
    eye = pygame.Vector2(eye)
    rays = max(2, rays)
    points = []
    for i in range(rays):
        angle = facing - fov / 2 + fov * i / (rays - 1)
        direction = (math.cos(angle), math.sin(angle))
        dist = cast_ray(tilemap, eye, direction, view_range)
        points.append((eye.x + direction[0] * dist, eye.y + direction[1] * dist))
    return points


def most_open_angle(tilemap, origin, max_dist: float, directions: int = 8) -> float:
    """Angle (radians) de la direction la plus dégagée : orientation naturelle d'une sentinelle."""
    best_angle, best_dist = 0.0, -1.0
    for i in range(directions):
        angle = math.tau * i / directions
        dist = cast_ray(tilemap, origin, (math.cos(angle), math.sin(angle)), max_dist)
        if dist > best_dist:
            best_angle, best_dist = angle, dist
    return best_angle
