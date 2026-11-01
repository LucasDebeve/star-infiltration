"""Casier d'officier : on le fouille (maintenir E) pour y dérober un uniforme impérial."""

from __future__ import annotations

import pygame

from game.entities.entity import Entity
from game.items import Item, ItemKind
from game.settings import COLORS, LOCKER_NOISE, LOCKER_REACH, LOCKER_TIME
from game.systems.interaction import InteractionContext, Prompt

SIZE = 26


class Locker(Entity):
    reach = LOCKER_REACH
    hold_time = LOCKER_TIME

    def __init__(self, x: float, y: float) -> None:
        super().__init__(x, y, SIZE, SIZE)
        self.taken = False  # l'uniforme a été pris : le casier reste entrouvert, vide
        self._age = 0.0

    @property
    def anchor(self) -> pygame.Vector2:
        return self.pos

    def distance_to(self, point: pygame.Vector2) -> float:
        return self.pos.distance_to(point)

    def prompt(self, inventory) -> Prompt | None:
        return None if self.taken else Prompt("Fouiller le casier (maintenir)")

    def interact(self, ctx: InteractionContext) -> None:
        self.taken = True
        item = Item(ItemKind.UNIFORM)
        ctx.inventory.add(item)
        ctx.events.emit("item_picked", item=item)
        ctx.events.emit("uniform_stolen", locker=self)
        ctx.events.emit("noise", pos=pygame.Vector2(self.pos), radius=LOCKER_NOISE)  # les charnières grincent

    def update(self, dt: float, tilemap=None) -> None:
        self._age += dt

    def draw(self, surface: pygame.Surface, camera, progress: float = 0.0) -> None:
        body = pygame.Rect(0, 0, self.width, self.height)
        body.center = camera.world_to_screen(self.pos)
        metal, edge = COLORS["door_metal"], COLORS["player_outline"]
        pygame.draw.rect(surface, COLORS["shadow"], body.move(2, 3), border_radius=3)
        pygame.draw.rect(surface, metal, body, border_radius=3)
        pygame.draw.rect(surface, edge, body, 2, border_radius=3)
        if self.taken:  # porte entrouverte : une fente sombre et un pan de battant
            slot = body.inflate(-10, -6)
            pygame.draw.rect(surface, COLORS["terminal_body"], slot)
            pygame.draw.polygon(surface, COLORS["door_metal_light"], [(slot.right, slot.y), (slot.right + 5, slot.y + 3), (slot.right + 5, slot.bottom - 1), (slot.right, slot.bottom)])
            return
        for i in range(3):  # fentes d'aération
            y = body.y + 5 + i * 3
            pygame.draw.line(surface, _dim(metal), (body.x + 5, y), (body.right - 6, y), 1)
        pygame.draw.line(surface, edge, (body.centerx, body.y + 3), (body.centerx, body.bottom - 3), 1)  # jonction des deux portes
        lamp = COLORS["uniform"]
        pygame.draw.rect(surface, lamp, (body.right - 9, body.centery + 2, 4, 6))  # poignée
        if progress > 0:  # barre de fouille
            bar = pygame.Rect(body.x + 2, body.bottom - 5, round((body.w - 4) * progress), 3)
            pygame.draw.rect(surface, COLORS["terminal_screen"], bar)


def _dim(color):
    return tuple(round(c * 0.6) for c in color)
