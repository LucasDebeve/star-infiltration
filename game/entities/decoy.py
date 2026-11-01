"""Leurre sonore : bipe à intervalle régulier et attire les gardes, puis s'éteint."""

from __future__ import annotations

import math

import pygame

from game.entities.entity import Entity
from game.settings import COLORS, DECOY_BEEP_INTERVAL, DECOY_DURATION, DECOY_SIZE

BLINK_SPEED = 14.0  # rad/s


class Decoy(Entity):
    def __init__(self, x: float, y: float) -> None:
        super().__init__(x, y, DECOY_SIZE, DECOY_SIZE)
        self.time_left = DECOY_DURATION
        self.made_beep = False  # vrai pendant l'image où il émet un bip
        self._beep_timer = 0.0  # le premier bip est immédiat

    @property
    def expired(self) -> bool:
        return self.time_left <= 0

    def update(self, dt: float, tilemap=None) -> None:
        self.made_beep = False
        if self.expired:
            return
        self.time_left -= dt
        self._beep_timer -= dt
        if self._beep_timer <= 0:
            self.made_beep = True
            self._beep_timer = DECOY_BEEP_INTERVAL

    def draw(self, surface: pygame.Surface, camera) -> None:
        cx, cy = camera.world_to_screen(self.pos)
        radius = self.width // 2
        lit = self.made_beep or math.sin(self.time_left * BLINK_SPEED) > 0.3
        color = COLORS["item_decoy"] if lit else COLORS["item_body"]
        pygame.draw.circle(surface, COLORS["shadow"], (cx + 1, cy + 2), radius)
        pygame.draw.circle(surface, COLORS["item_body"], (cx, cy), radius)
        pygame.draw.circle(surface, color, (cx, cy), radius - 3)
        pygame.draw.circle(surface, COLORS["player_outline"], (cx, cy), radius, 2)
