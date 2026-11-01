"""Zone d'extraction : on ne peut l'utiliser qu'une fois l'objectif de la mission accompli (par défaut, avec les données volées)."""

from __future__ import annotations

import math
from typing import Callable

import pygame

from game.entities.entity import Entity
from game.items import ItemKind
from game.settings import COLORS, EXIT_REACH
from game.systems.interaction import InteractionContext, Prompt

SIZE = 30
PULSE_SPEED = 4.0  # rad/s


class ExitPad(Entity):
    reach = EXIT_REACH
    hold_time = 0.0

    def __init__(self, x: float, y: float, ready: Callable | None = None, missing="Données requises", label: str = "Extraction") -> None:
        """`ready(inventory)` dit si l'objectif est accompli (par défaut : le joueur porte les données) ;
        `missing` est l'invite affichée tant qu'il ne l'est pas (un texte, ou une fonction qui le donne : il peut changer) ;
        `label` est l'invite quand on peut partir (« Embarquer » pour un vaisseau volé)."""
        super().__init__(x, y, SIZE, SIZE)
        self._ready = ready or self._has_data
        self._missing = missing
        self.label = label
        self._age = 0.0

    @property
    def anchor(self) -> pygame.Vector2:
        return self.pos

    def distance_to(self, point: pygame.Vector2) -> float:
        return self.pos.distance_to(point)

    @staticmethod
    def _has_data(inventory) -> bool:
        return inventory.count_kind(ItemKind.DATA) > 0

    @property
    def missing(self) -> str:
        return self._missing() if callable(self._missing) else self._missing

    def is_ready(self, inventory) -> bool:
        return bool(self._ready(inventory))

    def prompt(self, inventory) -> Prompt:
        if self.is_ready(inventory):
            return Prompt(self.label)
        return Prompt(self.missing, enabled=False)

    def interact(self, ctx: InteractionContext) -> None:
        ctx.events.emit("mission_complete")

    def update(self, dt: float, tilemap=None) -> None:
        self._age += dt

    def draw(self, surface: pygame.Surface, camera, ready: bool = False) -> None:
        cx, cy = camera.world_to_screen(self.pos)
        color = COLORS["exit_ready" if ready else "exit_idle"]
        half = self.width // 2
        pad = pygame.Rect(cx - half, cy - half, self.width, self.height)
        pygame.draw.rect(surface, tuple(c * 0.3 for c in color), pad, border_radius=5)
        pygame.draw.rect(surface, color, pad, 2, border_radius=5)
        pulse = 0.5 + 0.5 * math.sin(self._age * PULSE_SPEED) if ready else 0.0
        arrow = [(cx, cy - 8 + pulse * -2), (cx + 8, cy + 3), (cx + 3, cy + 3), (cx + 3, cy + 8), (cx - 3, cy + 8), (cx - 3, cy + 3), (cx - 8, cy + 3)]
        pygame.draw.polygon(surface, color, arrow)
