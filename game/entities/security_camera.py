"""Caméra de surveillance : un cône qui balaie, fixé à un mur. Elle repère le joueur comme un garde (méfiance qui monte),
mais ne bouge pas de sa place : elle prévient les gardes. Un terminal peut la désactiver quelque temps."""
from __future__ import annotations

import math

import pygame

from game.ai.perception import can_see
from game.settings import (
    CAMERA_ALARM_TIME,
    CAMERA_AWARENESS_DECAY,
    CAMERA_DETECT_TIME,
    CAMERA_FOV,
    CAMERA_MOUNT,
    CAMERA_RANGE,
    CAMERA_SWEEP_PERIOD,
    COLORS,
    GUARD_DETECT_CLOSE_BONUS,
)

FACING_ANGLES = {"N": -math.pi / 2, "E": 0.0, "S": math.pi / 2, "O": math.pi}  # O = ouest, comme pour les vaisseaux
FACING_VECTORS = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "O": (-1, 0)}


class SecurityCamera:
    def __init__(self, spec, tile_size: int) -> None:
        self.spec = spec
        self.group = spec.group
        dx, dy = FACING_VECTORS[spec.facing]
        self.mount = pygame.Vector2((spec.tile[0] + 0.5) * tile_size, (spec.tile[1] + 0.5) * tile_size)  # centre du mur qui la porte
        self.pos = self.mount + pygame.Vector2(dx, dy) * tile_size * CAMERA_MOUNT  # d'où elle voit : un peu en avant du mur
        self.base_angle = FACING_ANGLES[spec.facing]
        self.sweep = math.radians(spec.sweep)
        self.angle = self.base_angle
        self.phase = (spec.tile[0] * 0.37 + spec.tile[1] * 0.61) % math.tau  # elles ne balayent pas toutes ensemble
        self.time = 0.0
        self.awareness = 0.0
        self.sees_target = False
        self.alarm_left = 0.0  # temps pendant lequel elle reste « en alerte » après avoir repéré le joueur
        self.off_left = 0.0  # temps de désactivation restant

    @property
    def active(self) -> bool:
        return self.off_left <= 0

    @property
    def alarmed(self) -> bool:
        return self.alarm_left > 0

    def disable(self, seconds: float) -> None:
        self.off_left = max(self.off_left, seconds)
        self.awareness = 0.0
        self.sees_target = False
        self.alarm_left = 0.0

    def update(self, dt: float, tilemap, target) -> bool:
        """Avance d'un pas. Renvoie vrai quand elle vient de repérer le joueur (la scène prévient alors les gardes)."""
        self.time += dt
        if not self.active:
            self.off_left = max(0.0, self.off_left - dt)
            self.sees_target = False
            return False
        self.alarm_left = max(0.0, self.alarm_left - dt)
        self.angle = self.base_angle + self.sweep * math.sin(math.tau * self.time / CAMERA_SWEEP_PERIOD + self.phase)
        seen = target is not None and can_see(tilemap, self.pos, self.angle, CAMERA_FOV, CAMERA_RANGE, target.pos)
        if seen:
            at = getattr(target, "detectability_at", None)
            seen = (at(self.pos.distance_to(target.pos)) if at is not None else target.detectability) > 0  # un uniforme n'intéresse pas la caméra
        self.sees_target = seen
        if not seen:
            self.awareness = max(0.0, self.awareness - CAMERA_AWARENESS_DECAY * dt)
            return False
        closeness = 1 - self.pos.distance_to(target.pos) / CAMERA_RANGE
        distance = self.pos.distance_to(target.pos)
        at = getattr(target, "detectability_at", None)
        rate = (1 + GUARD_DETECT_CLOSE_BONUS * closeness) * (at(distance) if at is not None else target.detectability) / CAMERA_DETECT_TIME
        self.awareness = min(1.0, self.awareness + rate * dt)
        if self.awareness >= 1.0 and self.alarm_left <= 0:
            self.alarm_left = CAMERA_ALARM_TIME
            return True
        return False

    # --- Dessin ----------------------------------------------------------------------
    def draw(self, surface: pygame.Surface, camera, time: float) -> None:
        x, y = camera.world_to_screen(self.pos)
        mx, my = camera.world_to_screen(self.mount)
        color = COLORS["status_alert"] if self.alarmed else COLORS["cone_patrol"]
        if not self.active:
            color = COLORS["panel_border"]
        pygame.draw.line(surface, COLORS["player_outline"], (mx, my), (x, y), 5)  # le bras de fixation
        pygame.draw.circle(surface, COLORS["shadow"], (x + 1, y + 2), 7)
        pygame.draw.circle(surface, COLORS["door_metal"], (x, y), 7)
        pygame.draw.circle(surface, COLORS["player_outline"], (x, y), 7, 2)
        lens = (x + round(math.cos(self.angle) * 3), y + round(math.sin(self.angle) * 3))
        pygame.draw.circle(surface, color, lens, 3)
        if self.active and int(time * 2 + self.phase) % 2 == 0:
            pygame.draw.circle(surface, COLORS["status_alert"] if self.alarmed else COLORS["status_calm"], (x - 4, y - 5), 1)
