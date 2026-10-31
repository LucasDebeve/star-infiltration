"""Éclairage dynamique : lumière ambiante + lampes de plafond + lumières mobiles, multipliés sur la scène.

Principe : on construit une « carte de lumière » en demi-résolution, remplie de la lumière ambiante, puis
on y ajoute (BLEND_RGB_ADD) chaque lumière sous forme d'un dégradé radial découpé par le polygone de ce
que les murs laissent éclairer. La carte est ensuite agrandie (ce qui adoucit les bords) et multipliée
(BLEND_RGB_MULT) sur l'image : ce qui n'est pas éclairé s'assombrit.

Optimisations : les lampes fixes ont leur sprite d'ombre mis en cache (invalidé quand une porte s'ouvre),
décliné en paliers d'intensité pour le scintillement ; seules les lumières proches de l'écran sont dessinées.
"""
from __future__ import annotations

import math
from collections import OrderedDict
from functools import lru_cache

import pygame

from game.ai.perception import vision_points
from game.settings import (
    ALARM_FADE_TIME,
    ALARM_PULSE_SPEED,
    AMBIENT_ALARM,
    AMBIENT_BLACKOUT,
    GUARD_VISION_RAYS,
    LAMP_ALARM_COLOR,
    LAMP_FADE_TIME,
    LAMP_RADIUS,
    LAMP_RAYS,
    LIGHT_DOWNSCALE,
    LIGHT_FALLOFF,
    LIGHTING_ENABLED,
    POWER_FADE_TIME,
)
from game.world.exposure import luminance
from game.world.lights import LightSpec, flicker_factor, light_polygon, place_ceiling_lamps

INTENSITY_LADDER = (1.0, 0.85, 0.7, 0.55, 0.4, 0.28, 0.16, 0.06)  # paliers d'intensité des lampes (scintillement)
MAX_CACHED_SPRITES = 256
GRADIENT_STEPS = 28
GRADIENT_FALLOFF = LIGHT_FALLOFF  # plus grand = lumière plus concentrée au centre (partagé avec la détection)
DYNAMIC_RAYS = 48  # précision des ombres des lumières mobiles
COLOR_QUANTUM = 3  # bits ignorés dans les couleurs de dégradés : borne le nombre de sprites en cache
AMBIENT_ALARM_STRENGTH = 0.85
AMBIENT_ALARM_PULSE = 0.4  # part de l'ambiance d'alerte qui pulse


def lerp_color(a, b, t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _quantize(color) -> tuple[int, int, int]:
    return tuple(max(0, min(255, round(c))) >> COLOR_QUANTUM << COLOR_QUANTUM for c in color)


@lru_cache(maxsize=256)
def _gradient(radius: int, color: tuple[int, int, int]) -> pygame.Surface:
    """Disque lumineux : cercles concentriques de plus en plus clairs vers le centre. Ne pas le modifier."""
    surf = pygame.Surface((2 * radius, 2 * radius), 0, 32)
    for k in range(GRADIENT_STEPS, 0, -1):
        brightness = (1 - (k - 0.5) / GRADIENT_STEPS) ** GRADIENT_FALLOFF
        pygame.draw.circle(surf, tuple(round(c * brightness) for c in color), (radius, radius), max(1, round(radius * k / GRADIENT_STEPS)))
    return surf


class Lighting:
    def __init__(self, tilemap) -> None:
        self.lamps = place_ceiling_lamps(tilemap)
        self._ambient = tilemap.ambient  # lumière de base : celle de la carte (`@ambient`) ou de son thème
        self.enabled = LIGHTING_ENABLED
        self._time = 0.0
        self._alarm = 0.0  # 0 = calme, 1 = alerte : fondu entre les deux ambiances
        self._alarm_on = False
        self._power = 1.0  # 1 = alimentation normale, 0 = coupée : fondu des lampes
        self._lamp_levels = [1.0] * len(self.lamps)  # 1 = allumée, 0 = éteinte (lumière coupée dans la salle) : fondu par lampe
        self._revision = tilemap.revision
        self._masks: dict[tuple[int, int], pygame.Surface] = {}
        self._sprites: OrderedDict[tuple, pygame.Surface] = OrderedDict()
        self._map: pygame.Surface | None = None  # carte de lumière (demi-résolution)
        self._full: pygame.Surface | None = None  # carte agrandie à la taille de l'écran

    # --- État ----------------------------------------------------------------
    def update(self, dt: float, alarm: bool, power: bool = True, off_lamps=()) -> None:
        """`off_lamps` : indices des lampes éteintes (lumière coupée depuis un terminal)."""
        self._time += dt
        step = dt / LAMP_FADE_TIME
        for i, level in enumerate(self._lamp_levels):
            self._lamp_levels[i] = max(0.0, level - step) if i in off_lamps else min(1.0, level + step)
        self._alarm_on = alarm
        fade = dt / POWER_FADE_TIME
        self._power = min(1.0, self._power + fade) if power else max(0.0, self._power - fade)
        step = dt / ALARM_FADE_TIME
        self._alarm = min(1.0, self._alarm + step) if alarm else max(0.0, self._alarm - step)

    # --- Éclairement en un point (détection) ----------------------------------
    def lamp_level(self, index: int) -> float:
        """Intensité actuelle (0..1) de la lampe `index` : courant, scintillement et lumière de sa salle compris."""
        return flicker_factor(self.lamps[index], self._time) * self._power * self._lamp_levels[index]

    def light_sources(self, tilemap) -> list[tuple]:
        """(position, rayon, couleur, intensité) des lampes de plafond allumées, tel que `exposure.light_at` les lit."""
        return [
            (lamp.position(tilemap.tile_size), LAMP_RADIUS, lamp.color, level)
            for i, lamp in enumerate(self.lamps)
            if (level := self.lamp_level(i)) > 0.01
        ]

    def base_light(self) -> float:
        """Clarté ambiante (0..1) : celle du thème, qui tombe au noir complet sans courant."""
        return luminance(lerp_color(AMBIENT_BLACKOUT, self._ambient, self._power))

    def toggle(self) -> None:
        self.enabled = not self.enabled

    def ambient(self) -> tuple[int, int, int]:
        """Lumière de base ; pendant l'alerte, elle vire au rouge en pulsant."""
        base = lerp_color(AMBIENT_BLACKOUT, self._ambient, self._power) if self._power < 1 else self._ambient
        if self._alarm <= 0 or self._power <= 0:  # sans courant, plus de gyrophares
            return base
        beat = 0.5 + 0.5 * math.sin(self._time * ALARM_PULSE_SPEED)
        alarm = tuple(c * (1 - AMBIENT_ALARM_PULSE + AMBIENT_ALARM_PULSE * beat) for c in AMBIENT_ALARM)
        return lerp_color(base, alarm, self._alarm * AMBIENT_ALARM_STRENGTH * self._power)

    # --- Rendu ---------------------------------------------------------------
    def draw(self, surface: pygame.Surface, camera, tilemap, lights: list[LightSpec]) -> None:
        """Assombrit `surface` sauf là où des lumières l'éclairent."""
        if not self.enabled:
            return
        self._sync(surface.get_size(), tilemap)
        light_map = self._map
        light_map.fill(self.ambient())

        reach = camera.visible_rect.inflate(2 * LAMP_RADIUS, 2 * LAMP_RADIUS)
        for i, lamp in enumerate(self.lamps if self._power > 0 else ()):
            pos = lamp.position(tilemap.tile_size)
            if reach.collidepoint(pos) and self._lamp_levels[i] > 0.01:
                self._add_lamp(light_map, camera, tilemap, lamp, pos, self._lamp_levels[i])
        for spec in lights:
            if camera.visible_rect.inflate(2 * spec.radius, 2 * spec.radius).collidepoint(spec.pos):
                self._add_dynamic(light_map, camera, tilemap, spec)

        pygame.transform.smoothscale(light_map, surface.get_size(), self._full)
        surface.blit(self._full, (0, 0), special_flags=pygame.BLEND_RGB_MULT)

    def _sync(self, size: tuple[int, int], tilemap) -> None:
        if tilemap.revision != self._revision:  # une porte s'est ouverte : les ombres ont changé
            self._revision = tilemap.revision
            self._masks.clear()
            self._sprites.clear()
        if self._full is None or self._full.get_size() != size:
            self._full = pygame.Surface(size, 0, 32)
            self._map = pygame.Surface((max(1, size[0] // LIGHT_DOWNSCALE), max(1, size[1] // LIGHT_DOWNSCALE)), 0, 32)

    # --- Lampes fixes --------------------------------------------------------
    def _add_lamp(self, light_map, camera, tilemap, lamp, pos: pygame.Vector2, room_level: float = 1.0) -> None:
        mix = round(self._alarm * 2) / 2  # 0, 0,5 ou 1 : peu de variantes de couleur à mettre en cache
        level = flicker_factor(lamp, self._time) * self._power * room_level
        if self._alarm > 0:  # gyrophare : l'intensité pulse, décalée d'une lampe à l'autre
            pulse = 0.55 + 0.45 * math.sin(self._time * ALARM_PULSE_SPEED + lamp.phase * 3)
            level *= 1 - self._alarm * (1 - pulse)
        step = min(range(len(INTENSITY_LADDER)), key=lambda i: abs(INTENSITY_LADDER[i] - level))
        sprite = self._lamp_sprite(tilemap, lamp, pos, mix, step)
        radius = sprite.get_width() // 2
        sx, sy = camera.world_to_screen(pos)
        light_map.blit(sprite, (sx // LIGHT_DOWNSCALE - radius, sy // LIGHT_DOWNSCALE - radius), special_flags=pygame.BLEND_RGB_ADD)

    def _lamp_sprite(self, tilemap, lamp, pos: pygame.Vector2, mix: float, step: int) -> pygame.Surface:
        key = (lamp.tile, mix, step)
        sprite = self._sprites.get(key)
        if sprite is not None:
            self._sprites.move_to_end(key)
            return sprite
        radius = LAMP_RADIUS // LIGHT_DOWNSCALE
        sprite = _gradient(radius, _quantize(lerp_color(lamp.color, LAMP_ALARM_COLOR, mix))).copy()
        sprite.blit(self._mask(tilemap, lamp, pos, radius), (0, 0), special_flags=pygame.BLEND_RGB_MULT)
        level = round(255 * INTENSITY_LADDER[step])
        sprite.fill((level, level, level), special_flags=pygame.BLEND_RGB_MULT)
        self._sprites[key] = sprite
        if len(self._sprites) > MAX_CACHED_SPRITES:
            self._sprites.popitem(last=False)
        return sprite

    def _mask(self, tilemap, lamp, pos: pygame.Vector2, radius: int) -> pygame.Surface:
        mask = self._masks.get(lamp.tile)
        if mask is None:
            polygon = light_polygon(tilemap, pos, LAMP_RADIUS, LAMP_RAYS)
            mask = self._polygon_mask(radius, pos, polygon)
            self._masks[lamp.tile] = mask
        return mask

    @staticmethod
    def _polygon_mask(radius: int, center: pygame.Vector2, polygon) -> pygame.Surface:
        """Surface noire avec le polygone en blanc, aux dimensions du dégradé (centre du polygone au centre)."""
        mask = pygame.Surface((2 * radius, 2 * radius), 0, 32)
        points = [((x - center.x) / LIGHT_DOWNSCALE + radius, (y - center.y) / LIGHT_DOWNSCALE + radius) for x, y in polygon]
        pygame.draw.polygon(mask, (255, 255, 255), points)
        return mask

    # --- Lumières mobiles ----------------------------------------------------
    def _add_dynamic(self, light_map, camera, tilemap, spec: LightSpec) -> None:
        radius = max(2, round(spec.radius / LIGHT_DOWNSCALE))
        sprite = _gradient(radius, _quantize(tuple(c * spec.intensity for c in spec.color)))
        if spec.facing is not None:  # lampe torche : cône
            polygon = [tuple(spec.pos), *vision_points(tilemap, spec.pos, spec.facing, spec.fov, spec.radius, GUARD_VISION_RAYS // 2)]
        elif spec.shadowed:
            polygon = light_polygon(tilemap, spec.pos, spec.radius, DYNAMIC_RAYS)
        else:
            polygon = None
        if polygon is not None:
            sprite = sprite.copy()
            sprite.blit(self._polygon_mask(radius, spec.pos, polygon), (0, 0), special_flags=pygame.BLEND_RGB_MULT)
        sx, sy = camera.world_to_screen(spec.pos)
        light_map.blit(sprite, (sx // LIGHT_DOWNSCALE - radius, sy // LIGHT_DOWNSCALE - radius), special_flags=pygame.BLEND_RGB_ADD)
