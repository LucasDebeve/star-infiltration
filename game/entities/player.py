"""Le joueur : déplacement à trois postures (accroupi / marche / course) et visée à la souris."""
from __future__ import annotations

import math
from enum import Enum

import pygame

from game.core.input import InputState
from game.entities.entity import Entity
from game.settings import (
    DISGUISE_CLOSE_FACTOR,
    DISGUISE_RANGE,
    FOOTSTEP_INTERVAL,
    PLAYER_DETECTABILITY,
    PLAYER_NOISE,
    PLAYER_SIZE,
    PLAYER_SPEED,
    STRIDE_BLEND,
    STRIDE_RATE,
)
from game.ui.sprites import draw_player


class Stance(Enum):
    CROUCH = "crouch"
    WALK = "walk"
    RUN = "run"


class Player(Entity):
    def __init__(self, x: float, y: float) -> None:
        super().__init__(x, y, PLAYER_SIZE, PLAYER_SIZE)
        self.stance = Stance.WALK
        self.facing = pygame.Vector2(1, 0)
        self.is_moving = False
        self.made_step = False  # vrai pendant l'image où un pas audible est émis
        self._step_timer = 0.0
        self.walk_phase = 0.0  # cycle de marche (rad), avance avec la distance parcourue : le dessin balance jambes et bras
        self.stride = 0.0  # 0 à l'arrêt, 1 en marche : fondu des jambes pour qu'elles se figent doucement
        self._age = 0.0
        self.ghost = False  # mode développeur : invisible et silencieux
        self.disguised = False  # en uniforme *et* sans alerte générale : les gardes ne le reconnaissent plus de loin (voir `detectability_at`)
        self.light_factor = 1.0  # visibilité due à l'éclairage (voir `world/exposure.py`) : fixée par la scène à chaque image

    @property
    def speed(self) -> float:
        return PLAYER_SPEED[self.stance.value]

    @property
    def noise_radius(self) -> float:
        """Distance à laquelle les gardes entendront le joueur (nul à l'arrêt ou accroupi)."""
        return PLAYER_NOISE[self.stance.value] if self.is_moving else 0

    @property
    def detectability(self) -> float:
        """Facteur de vitesse de détection : accroupi < marche < course, et dans l'ombre < en pleine lumière."""
        return 0.0 if self.ghost else PLAYER_DETECTABILITY[self.stance.value] * self.light_factor

    def detectability_at(self, distance: float) -> float:
        """Vitesse de détection par un observateur à `distance` px (garde ou caméra). En uniforme, à pas ordinaire, on passe pour
        un membre du personnel : personne ne se méfie de loin, et de près on se méfie à peine. Courir ou s'accroupir trahit :
        on retombe alors dans la détection classique (sans le bénéfice de la discrétion de la posture)."""
        base = self.detectability
        if self.ghost:
            return 0.0
        if not self.disguised:
            return base
        if self.stance is not Stance.WALK:
            return PLAYER_DETECTABILITY[self.stance.value if self.stance is Stance.RUN else "walk"] * self.light_factor
        return 0.0 if distance > DISGUISE_RANGE else base * DISGUISE_CLOSE_FACTOR

    @property
    def heard_radius(self) -> float:
        """Rayon (px) auquel les gardes entendent le joueur : un officier qui marche fait un bruit normal, que personne ne relève."""
        return 0 if self.ghost or (self.disguised and self.stance is Stance.WALK) else self.noise_radius

    def update(
        self,
        dt: float,
        tilemap,
        inp: InputState | None = None,
        aim_world: pygame.Vector2 | None = None,
    ) -> None:
        inp = inp or InputState()

        if inp.crouch:  # l'accroupi est prioritaire sur la course
            self.stance = Stance.CROUCH
        elif inp.run:
            self.stance = Stance.RUN
        else:
            self.stance = Stance.WALK

        direction = pygame.Vector2(inp.move)
        if direction.length_squared() > 1:  # la diagonale ne doit pas être plus rapide
            direction.normalize_ip()
        self.is_moving = direction.length_squared() > 0

        before = pygame.Vector2(self.pos)
        if self.is_moving:
            self.move(direction * self.speed * dt, tilemap)
        self._update_footsteps(dt)
        self._animate(dt, self.pos.distance_to(before))

        # Orientation : vers la souris si elle est assez loin, sinon vers la direction de marche.
        aim = (aim_world - self.pos) if aim_world is not None else pygame.Vector2()
        if aim.length_squared() > 4:
            self.facing = aim.normalize()
        elif self.is_moving:
            self.facing = direction.normalize()

    def _animate(self, dt: float, moved: float) -> None:
        """La foulée avance avec la distance réellement parcourue (contre un mur, le personnage ne piétine pas dans le vide)."""
        self._age += dt
        self.walk_phase = (self.walk_phase + moved * STRIDE_RATE) % math.tau
        target = 1.0 if moved > 0 else 0.0
        self.stride += (target - self.stride) * min(1.0, dt * STRIDE_BLEND)

    def _update_footsteps(self, dt: float) -> None:
        """Émet un pas audible à intervalle régulier tant qu'on se déplace bruyamment."""
        self.made_step = False
        if self.noise_radius <= 0:
            self._step_timer = 0.0  # le premier pas sonne dès qu'on repart
            return
        self._step_timer -= dt
        if self._step_timer <= 0:
            self.made_step = True
            self._step_timer = FOOTSTEP_INTERVAL[self.stance.value]

    def draw(self, surface: pygame.Surface, camera) -> None:
        draw_player(surface, camera.world_to_screen(self.pos), self.facing, self.stance.value, self.walk_phase, self.stride, self._age, self.disguised)
