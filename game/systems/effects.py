"""Effets visuels de la scène de jeu : qui émet quelles particules, et quand.

`ParticleSystem` (ui/particles.py) sait créer et dessiner ; ici on décide : poussière sous les pas du joueur et des gardes
qui courent, étincelles pendant un piratage ou quand un champ de force bascule, fumée à la poupe des vaisseaux.
Les vaisseaux ne fument que s'ils sont assez près du joueur : inutile d'animer ce que personne ne voit.
"""
from __future__ import annotations

import math

import pygame

from game.ai.guard import GuardState
from game.settings import (
    AMBIENT_PARTICLE_SHARE,
    DUST_CHASE_INTERVAL,
    MOTE_RADIUS,
    MOTE_RATE,
    NOZZLE_SPACING,
    SMOKE_RANGE,
    SMOKE_RATE,
    SPARK_BURST,
    SPARK_COLORS,
    SPARK_RATE,
    VENT_BURST,
    VENT_RANGE,
    VENT_RATE,
    WIND_GUST_SPEED,
    WIND_LEAF_RATE,
    WIND_SAND_RATE,
)
from game.ui.particles import ParticleSystem, Pulse
from game.world.props import SHIP_KIND

# Direction du nez -> direction dans laquelle part l'échappement (vers la poupe).
EXHAUST = {"N": (0, 1), "S": (0, -1), "E": (-1, 0), "O": (1, 0)}
NOZZLE_OFFSET = 4  # px : la tuyère est juste derrière la coque


def ship_nozzles(prop, tile_size: int) -> list[tuple[pygame.Vector2, pygame.Vector2]]:
    """Tuyères d'un vaisseau : (position, direction de l'échappement), réparties sur sa poupe (au moins une)."""
    direction = pygame.Vector2(EXHAUST[prop.facing])
    left, top = prop.x * tile_size, prop.y * tile_size
    width, height = prop.w * tile_size, prop.h * tile_size
    horizontal_rear = prop.facing in ("N", "S")  # la poupe est un bord horizontal
    length_tiles = prop.w if horizontal_rear else prop.h
    count = max(1, length_tiles // NOZZLE_SPACING)
    nozzles = []
    for i in range(count):
        along = (i + 0.5) / count
        if horizontal_rear:
            x = left + width * along
            y = (top + height + NOZZLE_OFFSET) if prop.facing == "N" else (top - NOZZLE_OFFSET)
        else:
            y = top + height * along
            x = (left - NOZZLE_OFFSET) if prop.facing == "E" else (left + width + NOZZLE_OFFSET)
        nozzles.append((pygame.Vector2(x, y), direction))
    return nozzles


def wind_strength(time: float) -> float:
    """Force du vent (0,15 à 1) à l'instant `time` : des rafales irrégulières, faites de deux rythmes qui se croisent."""
    a, b = WIND_GUST_SPEED
    gust = (0.5 + 0.5 * math.sin(time * a)) * (0.5 + 0.5 * math.sin(time * b + 1.0))
    return 0.15 + 0.85 * math.sqrt(gust)


def vent_active(vent, time: float) -> bool:
    """Une bouche souffle pendant `VENT_BURST` secondes au début de chacune de ses périodes."""
    return (time + vent.phase * vent.period) % vent.period < VENT_BURST


class Effects:
    def __init__(self, tilemap, seed: int | None = None, lamps=()) -> None:
        """`lamps` : (position, couleur) des lampes de plafond, dont les halos portent la poussière en suspension."""
        self.particles = ParticleSystem(seed)
        self.dust_color = tilemap.theme.dust
        rng = self.particles.rng
        ts = tilemap.tile_size
        self.nozzles = [
            (pos, direction, Pulse(SMOKE_RATE, rng))
            for prop in tilemap.props
            if prop.kind == SHIP_KIND
            for pos, direction in ship_nozzles(prop, ts)
        ]
        self._sparks = Pulse(1.0, rng)
        self._chase: dict[int, float] = {}
        self.theme = tilemap.theme
        self.time = 0.0
        self.vents = [(vent, pygame.Vector2(vent.center(ts)), Pulse(VENT_RATE, rng)) for vent in tilemap.vents]
        self._vent_was_active = [False] * len(self.vents)
        self.lamps = [(pygame.Vector2(pos), color) for pos, color in lamps]
        self._motes = [Pulse(MOTE_RATE, rng) for _ in self.lamps]
        self._wind = Pulse(0.0, rng)

    # --- Déclencheurs ----------------------------------------------------------
    def footstep(self, pos, stance: str) -> None:
        self.particles.dust(pos, running=stance == "run", color=self.dust_color)

    def hacking(self, kind: str, pos, progress: float, dt: float) -> None:
        """Étincelles pendant un piratage : de plus en plus nombreuses à mesure que le téléchargement avance."""
        low, high = SPARK_RATE
        self._sparks.rate = low + (high - low) * max(0.0, min(1.0, progress))
        count = self._sparks.count(dt)
        if count:
            self.particles.sparks(pos, count, SPARK_COLORS[kind], speed=110)

    def burst(self, kind: str, pos) -> None:
        self.particles.sparks(pos, SPARK_BURST[kind], SPARK_COLORS[kind])

    # --- Vie -------------------------------------------------------------------
    def update(self, dt: float, focus, guards=(), view: pygame.Rect | None = None, power_on: bool = True, off_lamps=()) -> list[pygame.Vector2]:
        """Fait vivre les effets. `focus` : le joueur. `view` : la zone visible, pour le vent et la poussière en suspension
        (sans elle, seuls les effets proches du joueur tournent). Renvoie les bouches qui viennent de s'ouvrir (pour le son)."""
        focus = pygame.Vector2(focus)
        self.time += dt
        for pos, direction, pulse in self.nozzles:
            if pos.distance_squared_to(focus) <= SMOKE_RANGE * SMOKE_RANGE:
                for _ in range(pulse.count(dt)):
                    self.particles.smoke(pos, direction)
        chasing = {id(g): g for g in guards if g.state is GuardState.CHASE and g.pos.distance_squared_to(focus) <= SMOKE_RANGE**2}
        self._chase = {key: left - dt for key, left in self._chase.items() if key in chasing}
        for key, guard in chasing.items():
            left = self._chase.get(key, 0.0)
            if left <= 0:
                self.particles.dust(guard.pos + pygame.Vector2(0, 6), running=True, color=self.dust_color)
                left = DUST_CHASE_INTERVAL
            self._chase[key] = left
        opened = self._update_vents(dt, focus)
        if view is not None:
            self._update_wind(dt, view)
            if power_on:
                self._update_motes(dt, view, off_lamps)
        self.particles.update(dt)
        return opened

    def _update_vents(self, dt: float, focus: pygame.Vector2) -> list[pygame.Vector2]:
        opened = []
        for i, (vent, pos, pulse) in enumerate(self.vents):
            near = pos.distance_squared_to(focus) <= VENT_RANGE * VENT_RANGE
            active = near and vent_active(vent, self.time)
            if active and not self._vent_was_active[i]:
                opened.append(pos)
            self._vent_was_active[i] = active
            if active:
                for _ in range(pulse.count(dt)):
                    if self.particles.has_room(AMBIENT_PARTICLE_SHARE):
                        self.particles.steam(pos, vent.direction, self.theme.vent_color)
        return opened

    def _update_wind(self, dt: float, view: pygame.Rect) -> None:
        theme = self.theme
        if theme.wind is None:
            return
        strength = wind_strength(self.time)
        self._wind.rate = (WIND_SAND_RATE if theme.wind_kind == "sand" else WIND_LEAF_RATE) * strength
        wind = pygame.Vector2(theme.wind).normalize()
        rng = self.particles.rng
        for _ in range(self._wind.count(dt)):
            if not self.particles.has_room(AMBIENT_PARTICLE_SHARE):
                return
            pos = (rng.uniform(view.left, view.right), rng.uniform(view.top - 30, view.bottom))
            if theme.wind_kind == "sand":
                self.particles.sand(pos, wind, strength, theme.wind_color)
            else:
                color = rng.choice(theme.detail) if theme.detail else theme.wind_color
                self.particles.leaf(pos, wind, strength, color)

    def _update_motes(self, dt: float, view: pygame.Rect, off_lamps=()) -> None:
        rng = self.particles.rng
        reach = view.inflate(2 * MOTE_RADIUS, 2 * MOTE_RADIUS)
        for i, ((pos, color), pulse) in enumerate(zip(self.lamps, self._motes)):
            if i in off_lamps or not reach.collidepoint(pos):  # pas de poussière dans la lumière d'une lampe éteinte
                continue
            for _ in range(pulse.count(dt)):
                if not self.particles.has_room(AMBIENT_PARTICLE_SHARE):
                    return
                angle, radius = rng.uniform(0, math.tau), MOTE_RADIUS * math.sqrt(rng.random())
                self.particles.mote(pos + pygame.Vector2(math.cos(angle), math.sin(angle)) * radius, tuple(round(c * 0.6) for c in color))

    # --- Dessin ----------------------------------------------------------------
    def draw_soft(self, surface, camera) -> None:
        self.particles.draw_soft(surface, camera)

    def draw_glow(self, surface, camera) -> None:
        self.particles.draw_glow(surface, camera)
