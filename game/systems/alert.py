"""Alerte globale : déclenchée par la première poursuite, elle lance un compte à rebours de verrouillage,
alerte les gardes par radio et fait arriver des renforts.

Une fois donnée, l'alerte ne se lève plus : il faut s'échapper avant la fin du chronomètre.
Événements émis sur l'`EventBus` : `alert_raised(pos)`, `reinforcements_arrived(count)`, `lockdown()`.
Logique pure : le système ne dessine rien et crée les gardes sans les ajouter lui-même au jeu.
"""
from __future__ import annotations

import pygame

from game.ai.guard import Guard, GuardState
from game.difficulty import Difficulty, get_difficulty
from game.settings import (
    ALERT_RESPONDERS,
    DEFAULT_DIFFICULTY,
    RADIO_INTERVAL,
    REINFORCE_FIRST_DELAY,
    REINFORCE_HIDE_DISTANCE,
    REINFORCE_INTERVAL,
    REINFORCE_MAX,
    REINFORCE_MIN_DISTANCE,
    REINFORCE_PER_WAVE,
)
from game.world.raycast import line_of_sight


def choose_spawns(tilemap, tiles, player_pos: pygame.Vector2, count: int) -> list[tuple[int, int]]:
    """Points d'arrivée pour une vague : au plus `count`, distincts, du plus proche au plus éloigné.

    Sont écartés les points trop près du joueur, ceux qu'il verrait apparaître (en vue directe, à l'écran)
    et ceux d'où l'on ne peut pas l'atteindre : un renfort bloqué derrière une porte ne sert à rien.
    """
    player_tile = tilemap.world_to_tile(player_pos.x, player_pos.y)
    ts = tilemap.tile_size
    candidates = []
    for tile in tiles:
        if not tilemap.same_region(tile, player_tile):
            continue
        center = pygame.Vector2((tile[0] + 0.5) * ts, (tile[1] + 0.5) * ts)
        distance = center.distance_to(player_pos)
        on_screen = distance <= REINFORCE_HIDE_DISTANCE and line_of_sight(tilemap, center, player_pos)
        if distance < REINFORCE_MIN_DISTANCE or on_screen:
            continue
        candidates.append((distance, tile))
    return [tile for _, tile in sorted(candidates)[:count]]


class AlertSystem:
    def __init__(
        self,
        events,
        tilemap,
        reinforcement_tiles: list[tuple[int, int]],
        post_tile: tuple[int, int] | None,
        difficulty: Difficulty | None = None,
    ) -> None:
        self.events = events
        self.difficulty = difficulty or get_difficulty(DEFAULT_DIFFICULTY)
        self.tilemap = tilemap
        self.reinforcement_tiles = list(reinforcement_tiles)
        self.post_tile = post_tile  # là où les renforts montent la garde (la sortie)
        self.active = False
        self.locked_down = False
        self.time_left = self.difficulty.lockdown_time
        self.last_known: pygame.Vector2 | None = None  # dernière position du joueur signalée par radio
        self.reinforcement_count = 0
        self.waves = 0  # vagues effectivement arrivées
        self._radio_timer = 0.0
        self._wave_timer = 0.0

    def update(self, dt: float, guards: list[Guard], player) -> list[Guard]:
        """Fait avancer l'alerte ; renvoie les nouveaux gardes (renforts) que la scène doit ajouter au jeu."""
        if not self.active:
            if any(g.state is GuardState.CHASE for g in guards):
                self._raise(guards, player)
            return []
        if self.locked_down:
            return []

        self.time_left = max(0.0, self.time_left - dt)
        if self.time_left == 0:
            self.locked_down = True
            self.events.emit("lockdown")
            return []

        self._radio_timer -= dt
        if any(g.sees_target for g in guards):  # quelqu'un a le joueur en vue : il le signale
            self.last_known = pygame.Vector2(player.pos)
            if self._radio_timer <= 0:
                self._radio_timer = RADIO_INTERVAL
                self._broadcast(guards)

        if self.waves >= self.difficulty.waves:
            return []
        self._wave_timer -= dt
        if self._wave_timer > 0:
            return []
        arrivals = self._spawn_wave(guards, player)
        # Rien n'a pu arriver (joueur en vue des points d'arrivée, effectif au maximum) : on réessaie vite.
        self._wave_timer = REINFORCE_INTERVAL if arrivals else RADIO_INTERVAL
        return arrivals

    # --- Étapes --------------------------------------------------------------
    def _raise(self, guards: list[Guard], player) -> None:
        self.active = True
        self.time_left = self.difficulty.lockdown_time
        self.last_known = pygame.Vector2(player.pos)
        self._radio_timer = RADIO_INTERVAL
        self._wave_timer = REINFORCE_FIRST_DELAY
        for guard in guards:
            guard.alerted = True
        self._broadcast(guards)
        self.events.emit("alert_raised", pos=pygame.Vector2(player.pos))

    def _broadcast(self, guards: list[Guard]) -> None:
        """Message radio : les gardes les plus proches de `last_known` (hors poursuite) y vont enquêter."""
        listeners = [g for g in guards if g.state is not GuardState.CHASE]
        listeners.sort(key=lambda g: g.pos.distance_squared_to(self.last_known))
        for guard in listeners[:ALERT_RESPONDERS]:
            guard.alarm(self.tilemap, self.last_known)

    def _spawn_wave(self, guards: list[Guard], player) -> list[Guard]:
        room = REINFORCE_MAX - sum(g.is_reinforcement for g in guards)
        count = min(REINFORCE_PER_WAVE, room)
        if count <= 0 or self.post_tile is None:
            return []
        tiles = choose_spawns(self.tilemap, self.reinforcement_tiles, player.pos, count)
        arrivals = [Guard.reinforcement(self.tilemap, tile, self.post_tile, self.difficulty.reinforcement_stay) for tile in tiles]
        for guard in arrivals:
            guard.sensitivity = self.difficulty.detect
            guard.alarm(self.tilemap, self.last_known)  # ils savent où aller dès leur arrivée
        self.reinforcement_count += len(arrivals)
        if arrivals:
            self.waves += 1
            self.events.emit("reinforcements_arrived", count=len(arrivals))
        return arrivals
