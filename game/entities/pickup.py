"""Objet posé au sol, ramassé en le touchant."""
from __future__ import annotations

import math

import pygame

from game.entities.entity import Entity
from game.items import Item
from game.settings import PICKUP_SIZE
from game.ui.icons import draw_glow, draw_item_icon, item_color

BOB_AMPLITUDE = 2.5  # px
BOB_SPEED = 3.0  # rad/s
GLOW_RADIUS = 20


class Pickup(Entity):
    def __init__(self, x: float, y: float, item: Item) -> None:
        super().__init__(x, y, PICKUP_SIZE, PICKUP_SIZE)
        self.item = item
        self._age = (x * 0.013 + y * 0.007) % math.tau  # déphasage : les objets ne flottent pas en chœur

    def update(self, dt: float, tilemap=None) -> None:
        self._age += dt

    def draw(self, surface: pygame.Surface, camera) -> None:
        cx, cy = camera.world_to_screen(self.pos)
        bob = math.sin(self._age * BOB_SPEED) * BOB_AMPLITUDE
        draw_glow(surface, (cx, cy + 3), GLOW_RADIUS, item_color(self.item))
        draw_item_icon(surface, self.item, (cx, round(cy + bob)), self.width + 4)
