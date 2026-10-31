"""Console de la salle de contrôle : maintenir E quelques secondes pour couper l'alimentation (objectif « couper l'alimentation »)
ou pour désactiver les rayons tracteurs et les attaches des vaisseaux (objectif « voler un vaisseau »)."""
from __future__ import annotations

import math

import pygame

from game.entities.entity import Entity
from game.settings import COLORS, POWER_CUT_NOISE, POWER_CUT_TIME, SHIP_RELEASE_NOISE, SHIP_RELEASE_TIME, TERMINAL_REACH
from game.systems.interaction import InteractionContext, Prompt

SIZE = 26
BLINK_SPEED = 4.0  # rad/s
LEVERS = 3  # nombre de leviers dessinés sur la console


POWER, RELEASE = "power", "release"
PROMPTS = {POWER: "Couper l'alimentation (maintenir)", RELEASE: "Libérer les vaisseaux (maintenir)"}
EVENTS = {POWER: "power_cut", RELEASE: "ships_released"}
NOISES = {POWER: POWER_CUT_NOISE, RELEASE: SHIP_RELEASE_NOISE}
HOLD_TIMES = {POWER: POWER_CUT_TIME, RELEASE: SHIP_RELEASE_TIME}


class PowerConsole(Entity):
    reach = TERMINAL_REACH

    def __init__(self, x: float, y: float, kind: str = POWER) -> None:
        """`kind` : `POWER` (couper l'alimentation) ou `RELEASE` (libérer les vaisseaux de leurs rayons tracteurs et attaches)."""
        super().__init__(x, y, SIZE, SIZE)
        self.kind = kind
        self.hold_time = HOLD_TIMES[kind]
        self.cut = False  # l'action a été faite (alimentation coupée, ou vaisseaux libérés)
        self._age = 0.0

    @property
    def anchor(self) -> pygame.Vector2:
        return self.pos

    def distance_to(self, point: pygame.Vector2) -> float:
        return self.pos.distance_to(point)

    def prompt(self, inventory) -> Prompt | None:
        return None if self.cut else Prompt(PROMPTS[self.kind])

    def interact(self, ctx: InteractionContext) -> None:
        self.cut = True
        ctx.events.emit(EVENTS[self.kind], console=self)
        ctx.events.emit("noise", pos=pygame.Vector2(self.pos), radius=NOISES[self.kind])  # le claquement des disjoncteurs ou des attaches

    def update(self, dt: float, tilemap=None) -> None:
        self._age += dt

    def draw(self, surface: pygame.Surface, camera, progress: float = 0.0) -> None:
        body = pygame.Rect(0, 0, self.width, self.height)
        body.center = camera.world_to_screen(self.pos)
        color = COLORS["console_dead" if self.cut else "console_live"]
        pygame.draw.rect(surface, COLORS["shadow"], body.move(2, 3), border_radius=4)
        pygame.draw.rect(surface, COLORS["terminal_body"], body, border_radius=4)
        pygame.draw.rect(surface, COLORS["player_outline"], body, 2, border_radius=4)

        panel = body.inflate(-8, -8)
        pygame.draw.rect(surface, tuple(c * 0.22 for c in color), panel, border_radius=2)
        slot = panel.w // LEVERS
        blink = 0.5 + 0.5 * math.sin(self._age * BLINK_SPEED)
        for i in range(LEVERS):  # des leviers : relevés en marche, abaissés une fois coupé (et tirés pendant l'action)
            x = panel.x + slot * i + slot // 2
            up = 0.0 if self.cut else 1.0 - progress
            top = panel.y + 3
            handle_y = top + 2 + round((1 - up) * (panel.h - 10))
            pygame.draw.line(surface, COLORS["player_outline"], (x, top), (x, panel.bottom - 3), 2)
            lamp = tuple(round(c * (0.4 if self.cut else 0.55 + 0.45 * blink)) for c in color)
            pygame.draw.circle(surface, lamp, (x, handle_y), 3)
        pygame.draw.rect(surface, color, panel, 1, border_radius=2)
