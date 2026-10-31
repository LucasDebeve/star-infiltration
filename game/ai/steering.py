"""Outils de déplacement pour l'IA : suivi de chemin et rotation progressive.

Fonctions et classes pures (sans fenêtre) : faciles à tester.
"""
from __future__ import annotations

import math
from collections import deque
from typing import Iterable

import pygame

from game.settings import PATH_ARRIVE_TOLERANCE


def angle_difference(target: float, current: float) -> float:
    """Plus petit écart signé (radians, dans [-π, π]) pour passer de `current` à `target`."""
    return (target - current + math.pi) % math.tau - math.pi


def rotate_towards(current: float, target: float, max_step: float) -> float:
    """Tourne `current` vers `target` d'au plus `max_step` radians, par le chemin le plus court."""
    diff = angle_difference(target, current)
    if abs(diff) <= max_step:
        return target
    return current + math.copysign(max_step, diff)


class PathFollower:
    """Suit une suite de points monde, du premier au dernier."""

    def __init__(self, tolerance: float = PATH_ARRIVE_TOLERANCE) -> None:
        self.tolerance = tolerance
        self.waypoints: deque[pygame.Vector2] = deque()

    @property
    def finished(self) -> bool:
        return not self.waypoints

    def set_path(self, points: Iterable[pygame.Vector2]) -> None:
        self.waypoints = deque(pygame.Vector2(p) for p in points)

    def clear(self) -> None:
        self.waypoints.clear()

    def step(self, pos: pygame.Vector2, max_distance: float) -> pygame.Vector2:
        """Déplacement (au plus `max_distance`) vers le point courant ; ne dépasse jamais le point."""
        self._drop_reached(pos)
        if not self.waypoints:
            return pygame.Vector2()
        offset = self.waypoints[0] - pos
        if offset.length() > max_distance:
            offset.scale_to_length(max_distance)
        self._drop_reached(pos + offset)
        return offset

    def _drop_reached(self, pos: pygame.Vector2) -> None:
        while self.waypoints and pos.distance_to(self.waypoints[0]) <= self.tolerance:
            self.waypoints.popleft()
