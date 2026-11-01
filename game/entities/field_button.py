"""Bouton de champs de force : chaque pression inverse l'état de tous les champs auxquels il est lié."""

from __future__ import annotations

import pygame

from game.settings import BUTTON_COOLDOWN, BUTTON_REACH, COLORS
from game.systems.interaction import InteractionContext, Prompt
from game.world.switch_fields import ButtonSpec

PLATE_INSET = 5
RING_WIDTH = 3
ARROW = 4  # demi-hauteur des deux petites flèches qui évoquent « inverser »


class FieldButton:
    reach = BUTTON_REACH
    hold_time = 0.0

    def __init__(self, spec: ButtonSpec, tile_size: int) -> None:
        self.spec = spec
        self.id = spec.id
        self.pos = pygame.Vector2((spec.tile[0] + 0.5) * tile_size, (spec.tile[1] + 0.5) * tile_size)
        self.anchor = self.pos
        self.tile_size = tile_size
        self.cooldown = 0.0  # temps restant avant de pouvoir le réactionner
        self.color = COLORS[f"link_{spec.color}"]

    # --- Interaction ---------------------------------------------------------
    def distance_to(self, point: pygame.Vector2) -> float:
        return self.pos.distance_to(point)

    def prompt(self, inventory) -> Prompt:
        return Prompt("Actionner")

    def interact(self, ctx: InteractionContext) -> None:
        """Inverse tous les champs liés. Un délai anti-répétition évite de les faire clignoter à coups d'appuis."""
        if self.cooldown > 0:
            return
        self.cooldown = BUTTON_COOLDOWN
        ctx.events.emit("button_pressed", button=self.id)
        for field_id in self.spec.fields:
            field = ctx.tilemap.toggle_field(field_id)
            ctx.events.emit("field_toggled", field=field_id, active=field.target)

    def update(self, dt: float, tilemap=None) -> None:
        self.cooldown = max(0.0, self.cooldown - dt)

    # --- Dessin --------------------------------------------------------------
    def draw(self, surface: pygame.Surface, camera) -> None:
        plate = pygame.Rect(0, 0, self.tile_size - 2 * PLATE_INSET, self.tile_size - 2 * PLATE_INSET)
        plate.center = camera.world_to_screen(self.pos)
        pressed = self.cooldown > 0
        if pressed:
            plate.move_ip(0, 1)  # enfoncé
        edge = COLORS["player_outline"]
        pygame.draw.rect(surface, COLORS["shadow"], plate.move(1, 2), border_radius=6)
        pygame.draw.rect(surface, COLORS["door_metal"], plate, border_radius=6)
        pygame.draw.rect(surface, tuple(c * (0.35 if pressed else 1.0) for c in self.color), plate.inflate(-6, -6), RING_WIDTH, border_radius=4)
        pygame.draw.rect(surface, edge, plate, 2, border_radius=6)
        cx, cy = plate.center
        lamp = tuple(c * (0.3 if pressed else 1.0) for c in self.color)
        pygame.draw.polygon(surface, lamp, [(cx - 8, cy), (cx - 3, cy - ARROW), (cx - 3, cy + ARROW)])  # deux flèches opposées : « inverser »
        pygame.draw.polygon(surface, lamp, [(cx + 8, cy), (cx + 3, cy - ARROW), (cx + 3, cy + ARROW)])
