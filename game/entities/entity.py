"""Entité de base : position (centre), boîte de collision, déplacement avec collisions."""

from __future__ import annotations

import pygame

from game.world.collision import MoveResult, move_and_collide


class Entity:
    def __init__(self, x: float, y: float, width: float, height: float) -> None:
        self.pos = pygame.Vector2(x, y)  # centre de l'entité, en coordonnées monde
        self.width = width
        self.height = height

    @property
    def top_left(self) -> tuple[float, float]:
        return self.pos.x - self.width / 2, self.pos.y - self.height / 2

    @property
    def rect(self) -> pygame.Rect:
        """Boîte entière (pour l'affichage et le debug)."""
        x, y = self.top_left
        return pygame.Rect(round(x), round(y), round(self.width), round(self.height))

    def move(self, delta: pygame.Vector2, tilemap) -> MoveResult:
        """Déplace l'entité de `delta` en s'arrêtant contre les murs."""
        x, y = self.top_left
        result = move_and_collide(tilemap, x, y, self.width, self.height, delta.x, delta.y)
        self.pos.update(result.x + self.width / 2, result.y + self.height / 2)
        return result

    def update(self, dt: float, tilemap) -> None:
        """Logique propre à l'entité (surchargée par les sous-classes)."""

    def draw(self, surface: pygame.Surface, camera) -> None:
        """Dessin (surchargé par les sous-classes)."""
