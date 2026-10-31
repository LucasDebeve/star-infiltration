"""Le prisonnier : captif dans sa cellule, il se délivre (maintenir E, une fois la cellule ouverte) puis suit le joueur jusqu'à la sortie."""
from __future__ import annotations

import math

import pygame

from game.ai.pathfinding import plan_route
from game.ai.steering import PathFollower
from game.entities.entity import Entity
from game.settings import (
    PRISONER_FOLLOW_DISTANCE,
    PRISONER_FREE_TIME,
    PRISONER_NOISE,
    PRISONER_REACH,
    PRISONER_REPATH,
    PRISONER_SIZE,
    PRISONER_SPEED,
    STRIDE_BLEND,
    STRIDE_RATE,
)
from game.systems.interaction import InteractionContext, Prompt
from game.ui.sprites import draw_prisoner


class Prisoner(Entity):
    reach = PRISONER_REACH
    hold_time = PRISONER_FREE_TIME

    def __init__(self, x: float, y: float) -> None:
        super().__init__(x, y, PRISONER_SIZE, PRISONER_SIZE)
        self.freed = False
        self.facing = pygame.Vector2(0, 1)
        self.follower = PathFollower()
        self.walk_phase = 0.0
        self.stride = 0.0
        self._repath = 0.0
        self._age = 0.0

    # --- Interaction ---------------------------------------------------------
    @property
    def anchor(self) -> pygame.Vector2:
        return self.pos

    def distance_to(self, point: pygame.Vector2) -> float:
        return self.pos.distance_to(point)

    def prompt(self, inventory) -> Prompt | None:
        return None if self.freed else Prompt("Libérer le prisonnier (maintenir)")

    def interact(self, ctx: InteractionContext) -> None:
        self.freed = True
        ctx.events.emit("prisoner_freed", prisoner=self)
        ctx.events.emit("noise", pos=pygame.Vector2(self.pos), radius=PRISONER_NOISE)  # les liens qui cèdent

    # --- Vie -------------------------------------------------------------------
    def update(self, dt: float, tilemap=None, leader: pygame.Vector2 | None = None) -> None:
        """Libéré, il suit `leader` (le joueur) par un chemin A*, à la vitesse de la marche : s'il se trouve bloqué (champ de force
        fermé), il attend. Captif, il ne bouge pas."""
        self._age += dt
        before = pygame.Vector2(self.pos)
        if self.freed and tilemap is not None and leader is not None:
            self._follow(dt, tilemap, leader)
        moved = self.pos.distance_to(before)
        self.walk_phase = (self.walk_phase + moved * STRIDE_RATE) % math.tau
        self.stride += ((1.0 if moved > 0 else 0.0) - self.stride) * min(1.0, dt * STRIDE_BLEND)

    def _follow(self, dt: float, tilemap, leader: pygame.Vector2) -> None:
        if self.pos.distance_to(leader) <= PRISONER_FOLLOW_DISTANCE:
            self.follower.clear()
            self._turn_to(leader - self.pos)
            return
        self._repath -= dt
        if self._repath <= 0 or self.follower.finished:
            self._repath = PRISONER_REPATH
            self.follower.set_path(plan_route(tilemap, self.pos, leader, self.width / 2) or [])
        step = self.follower.step(self.pos, PRISONER_SPEED * dt)
        if step.length_squared() > 0:
            self.move(step, tilemap)
            self._turn_to(step)

    def _turn_to(self, direction: pygame.Vector2) -> None:
        if direction.length_squared() > 1e-6:
            self.facing = direction.normalize()

    def draw(self, surface: pygame.Surface, camera) -> None:
        draw_prisoner(surface, camera.world_to_screen(self.pos), self.facing, not self.freed, self.walk_phase, self.stride, self._age)
