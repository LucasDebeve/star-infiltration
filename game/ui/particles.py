"""Particules : poussière de pas, étincelles, fumée. Un petit système maison, sans dépendance à une fenêtre pour la logique.

Une particule vit `life` secondes, grandit de `size0` à `size1` et s'estompe. Deux familles se dessinent à deux moments :
    douces (poussière, fumée) : mélangées normalement, avant l'éclairage, donc assombries avec le décor ;
    lumineuses (étincelles) : ajoutées après l'éclairage (`BLEND_RGB_ADD`), donc elles brillent dans l'obscurité.
Le nombre de particules est plafonné (`PARTICLE_LIMIT`) : au-delà, les nouvelles sont ignorées.
"""

from __future__ import annotations

import math
import random

import pygame

from game.settings import DUST_COLOR, PARTICLE_LIMIT, SMOKE_COLOR

GLOW_LEVELS = 8  # paliers de luminosité d'une étincelle (peu de sprites à mettre en cache)


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "age", "life", "size0", "size1", "color", "alpha", "drag", "glow", "sway", "phase")

    def __init__(self, x, y, vx, vy, life, size0, size1, color, alpha, drag, glow, sway=None, phase=0.0) -> None:
        self.sway, self.phase = sway, phase  # (vitesse latérale maximale px/s, pulsation rad/s) : balancement horizontal symétrique
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.age, self.life = 0.0, life
        self.size0, self.size1 = size0, size1
        self.color, self.alpha, self.drag, self.glow = color, alpha, drag, glow

    @property
    def t(self) -> float:
        """Avancement de la vie, de 0 (naissance) à 1 (disparition)."""
        return min(1.0, self.age / self.life)

    @property
    def size(self) -> float:
        return self.size0 + (self.size1 - self.size0) * self.t

    @property
    def opacity(self) -> float:
        """Intensité (0..1) : elle s'installe en un instant puis décroît."""
        t = self.t
        return min(1.0, t * 8) * (1.0 - t) ** 1.5


class Pulse:
    """Cadence : `count(dt)` dit combien de particules émettre pendant `dt` pour `rate` par seconde (les restes se cumulent)."""

    def __init__(self, rate: float, rng: random.Random | None = None) -> None:
        self.rate = rate
        self._carry = (rng or random).random()  # déphasage : deux émetteurs ne tirent pas en même temps

    def count(self, dt: float) -> int:
        self._carry += self.rate * dt
        whole = int(self._carry)
        self._carry -= whole
        return whole


class ParticleSystem:
    def __init__(self, seed: int | None = None, limit: int = PARTICLE_LIMIT) -> None:
        self.rng = random.Random(seed)
        self.limit = limit
        self.particles: list[Particle] = []
        self._soft: dict[tuple, pygame.Surface] = {}
        self._glow: dict[tuple, pygame.Surface] = {}

    def __len__(self) -> int:
        return len(self.particles)

    def clear(self) -> None:
        self.particles.clear()

    # --- Émission ------------------------------------------------------------
    def emit(self, pos, velocity, life, size0, size1, color, alpha=255, drag=0.0, glow=False, sway=None) -> bool:
        if len(self.particles) >= self.limit:
            return False
        phase = self.rng.uniform(0, math.tau) if sway else 0.0
        self.particles.append(Particle(pos[0], pos[1], velocity[0], velocity[1], life, size0, size1, color, alpha, drag, glow, sway, phase))
        return True

    def has_room(self, share: float) -> bool:
        """Reste-t-il de la place pour du décor (qui n'occupe que `share` du plafond : les étincelles passent avant) ?"""
        return len(self.particles) < self.limit * share

    def dust(self, pos, running: bool, color=DUST_COLOR) -> None:
        """Petit nuage soulevé par un pas : plus gros et plus nombreux quand on court."""
        for _ in range(3 if running else 1):
            angle = self.rng.uniform(0, math.tau)
            speed = self.rng.uniform(8, 26 if running else 14)
            self.emit(
                (pos[0] + self.rng.uniform(-3, 3), pos[1] + self.rng.uniform(-2, 4)),
                (math.cos(angle) * speed, math.sin(angle) * speed),
                self.rng.uniform(0.4, 0.7),
                2.0,
                self.rng.uniform(5, 8) if running else self.rng.uniform(3, 5),
                color,
                alpha=140 if running else 90,
                drag=3.0,
            )

    def sparks(self, pos, count: int, color, speed: float = 150.0) -> None:
        """Gerbe d'étincelles qui jaillissent dans toutes les directions et retombent en s'éteignant."""
        for _ in range(count):
            angle = self.rng.uniform(0, math.tau)
            v = self.rng.uniform(0.3, 1.0) * speed
            self.emit(
                pos,
                (math.cos(angle) * v, math.sin(angle) * v),
                self.rng.uniform(0.18, 0.45),
                2.0,
                0.8,
                color,
                drag=2.6,
                glow=True,
            )

    def smoke(self, pos, direction, spread: float = 0.35) -> None:
        """Volute de fumée qui s'éloigne de la tuyère dans `direction` (vecteur unitaire), en grossissant."""
        angle = math.atan2(direction[1], direction[0]) + self.rng.uniform(-spread, spread)
        speed = self.rng.uniform(16, 34)
        self.emit(
            (pos[0] + self.rng.uniform(-2, 2), pos[1] + self.rng.uniform(-2, 2)),
            (math.cos(angle) * speed, math.sin(angle) * speed),
            self.rng.uniform(1.3, 2.2),
            3.0,
            self.rng.uniform(16, 24),
            SMOKE_COLOR,
            alpha=150,
            drag=0.9,
        )

    def steam(self, pos, direction, color) -> None:
        """Volute de vapeur ou de brume qui jaillit d'une bouche dans `direction` puis se dissipe en grossissant."""
        angle = math.atan2(direction[1], direction[0]) + self.rng.uniform(-0.45, 0.45)
        speed = self.rng.uniform(26, 62)
        self.emit(
            (pos[0] + self.rng.uniform(-5, 5), pos[1] + self.rng.uniform(-5, 5)),
            (math.cos(angle) * speed, math.sin(angle) * speed),
            self.rng.uniform(0.8, 1.4),
            3.0,
            self.rng.uniform(13, 20),
            color,
            alpha=125,
            drag=1.7,
        )

    def sand(self, pos, wind, strength: float, color) -> None:
        """Grain de sable emporté par le vent (plus vite et plus loin dans une rafale)."""
        speed = self.rng.uniform(120, 230) * (0.5 + 0.5 * strength)
        self.emit(
            pos,
            (wind[0] * speed, wind[1] * speed + self.rng.uniform(-14, 14)),
            self.rng.uniform(1.2, 2.2),
            1.0,
            1.0,
            color,
            alpha=150,
        )

    def leaf(self, pos, wind, strength: float, color) -> None:
        """Feuille qui tombe en se balançant, poussée par le vent."""
        self.emit(
            pos,
            (wind[0] * 26 * strength, self.rng.uniform(18, 34)),
            self.rng.uniform(3.5, 5.5),
            2.0,
            2.0,
            color,
            alpha=210,
            sway=(self.rng.uniform(30, 55), self.rng.uniform(2.2, 3.6)),
        )

    def mote(self, pos, color) -> None:
        """Grain de poussière qui flotte dans la lumière : presque immobile, il dérive en se balançant. Additif."""
        self.emit(
            pos,
            (self.rng.uniform(-5, 5), self.rng.uniform(-6, 2)),
            self.rng.uniform(3.0, 5.0),
            1.0,
            1.0,
            color,
            glow=True,
            sway=(self.rng.uniform(5, 12), self.rng.uniform(0.9, 1.8)),
        )

    # --- Vie -----------------------------------------------------------------
    def update(self, dt: float) -> None:
        alive = []
        for p in self.particles:
            p.age += dt
            if p.age >= p.life:
                continue
            lateral = p.sway[0] * math.sin(p.age * p.sway[1] + p.phase) if p.sway else 0.0  # va-et-vient autour de la trajectoire
            p.x += (p.vx + lateral) * dt
            p.y += p.vy * dt
            slow = max(0.0, 1.0 - p.drag * dt)
            p.vx *= slow
            p.vy *= slow
            alive.append(p)
        self.particles = alive

    # --- Dessin --------------------------------------------------------------
    def draw_soft(self, surface: pygame.Surface, camera) -> None:
        """Poussière et fumée (avant l'éclairage)."""
        self._draw(surface, camera, glow=False)

    def draw_glow(self, surface: pygame.Surface, camera) -> None:
        """Étincelles (après l'éclairage, additives : elles brillent même dans le noir)."""
        self._draw(surface, camera, glow=True)

    def _draw(self, surface: pygame.Surface, camera, glow: bool) -> None:
        view = camera.visible_rect.inflate(40, 40)
        for p in self.particles:
            if p.glow is not glow or not view.collidepoint(p.x, p.y):
                continue
            radius = max(1, round(p.size))
            sx, sy = camera.world_to_screen((p.x, p.y))
            if glow:
                level = max(1, round(p.opacity * GLOW_LEVELS))
                sprite = self._glow_sprite(radius, p.color, level)
                surface.blit(sprite, (sx - radius, sy - radius), special_flags=pygame.BLEND_RGB_ADD)
            else:
                sprite = self._soft_sprite(radius, p.color)
                sprite.set_alpha(round(p.alpha * p.opacity))
                surface.blit(sprite, (sx - radius, sy - radius))

    def _soft_sprite(self, radius: int, color) -> pygame.Surface:
        key = (radius, color)
        sprite = self._soft.get(key)
        if sprite is None:
            sprite = pygame.Surface((2 * radius, 2 * radius), pygame.SRCALPHA)
            pygame.draw.circle(sprite, (*color, 110), (radius, radius), radius)  # bord doux
            pygame.draw.circle(sprite, (*color, 255), (radius, radius), max(1, radius * 2 // 3))
            self._soft[key] = sprite
        return sprite

    def _glow_sprite(self, radius: int, color, level: int) -> pygame.Surface:
        key = (radius, color, level)
        sprite = self._glow.get(key)
        if sprite is None:
            sprite = pygame.Surface((2 * radius, 2 * radius))
            pygame.draw.circle(sprite, tuple(c * level // GLOW_LEVELS for c in color), (radius, radius), radius)
            self._glow[key] = sprite
        return sprite
