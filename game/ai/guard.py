"""Le garde : patrouille, repère le joueur à la vue ou à l'oreille, enquête, poursuit.

États :
    PATROL       suit son itinéraire (A* entre les points), marque une pause à chaque point
    INVESTIGATE  va (A*) vers l'endroit d'un bruit ou de la dernière position connue du joueur
    SEARCH       fouille sur place en balayant du regard, puis reprend sa patrouille
    CHASE        poursuit le joueur ; l'abandonne après quelques secondes sans le voir

En alerte globale (`alerted`), il repère plus vite et se déplace plus vite ; `alarm` le dépêche sur
la dernière position connue du joueur. Un renfort est un garde qui arrive en cours d'alerte : il enquête
d'abord là où on lui indique, puis garde la sortie.

La détection n'est pas instantanée : tant que le joueur est dans le cône, la « méfiance »
(`awareness`, de 0 à 1) monte, plus vite de près et quand le joueur court. À 1, c'est la poursuite.
"""

from __future__ import annotations

import math
from enum import Enum

import pygame

from game.ai.pathfinding import plan_route
from game.ai.perception import can_see, hears, most_open_angle
from game.ai.steering import PathFollower, rotate_towards
from game.entities.entity import Entity
from game.settings import (
    ALERT_DETECT_MULT,
    ALERT_SPEED_MULT,
    COLORS,
    GUARD_AWARENESS_AFTER_CHASE,
    GUARD_AWARENESS_DECAY,
    GUARD_CATCH_DISTANCE,
    GUARD_DETECT_CLOSE_BONUS,
    GUARD_DETECT_TIME,
    GUARD_FOV,
    GUARD_LOSE_SIGHT_TIME,
    GUARD_REPATH_INTERVAL,
    GUARD_SEARCH_SWEEP,
    GUARD_SEARCH_TIME,
    GUARD_SIZE,
    GUARD_SPEED,
    GUARD_TURN_SPEED,
    GUARD_VISION_RANGE,
    GUARD_WAIT_TIME,
    REINFORCE_STAY_TIME,
    STRIDE_BLEND,
    STRIDE_RATE,
)
from game.ui.sprites import draw_guard
from game.world.raycast import has_clearance


def _detectability(target, distance: float) -> float:
    """Vitesse de détection de `target` vue de `distance` px (le déguisement la fait dépendre de la distance ; les autres cibles, non)."""
    at = getattr(target, "detectability_at", None)
    return at(distance) if at is not None else target.detectability


class GuardState(Enum):
    PATROL = "patrol"
    INVESTIGATE = "investigate"
    SEARCH = "search"
    CHASE = "chase"

    @property
    def threat(self) -> int:
        """0 = calme, 1 = soupçonneux, 2 = en alerte (sert au HUD)."""
        return _THREAT[self]


_THREAT = {GuardState.PATROL: 0, GuardState.INVESTIGATE: 1, GuardState.SEARCH: 1, GuardState.CHASE: 2}


class Guard(Entity):
    def __init__(self, route: list[pygame.Vector2], angle: float = 0.0) -> None:
        if not route:
            raise ValueError("Un garde a besoin d'au moins un point de poste")
        super().__init__(route[0].x, route[0].y, GUARD_SIZE, GUARD_SIZE)
        self.route = [pygame.Vector2(p) for p in route]
        self.route_index = 0
        self.angle = angle  # orientation du regard, en radians
        self.home_angle = angle  # regard d'une sentinelle à son poste
        self.state = GuardState.PATROL
        self.awareness = 0.0
        self.sees_target = False
        self.walk_phase = 0.0  # cycle de marche (rad) : avance avec la distance parcourue, le dessin balance jambes et bras
        self.stride = 0.0  # 0 à l'arrêt, 1 en marche (fondu)
        self._age = 0.0
        self.alerted = False  # alerte globale en cours : vigilance et vitesse accrues
        self.sensitivity = 1.0  # réglage de difficulté : multiplie la vitesse de détection
        self.is_reinforcement = False
        self.lifetime: float | None = None  # temps restant avant de se retirer (renforts seulement)
        self.destination: pygame.Vector2 | None = None  # dernier lieu suspect
        self.follower = PathFollower()

        self._wait_timer = 0.0
        self._search_time = 0.0
        self._search_base = angle
        self._lose_sight_timer = 0.0
        self._repath_timer = 0.0

    @classmethod
    def from_spawn(cls, tilemap, spawn) -> Guard:
        """Garde placé sur un 'G' de la carte, avec l'itinéraire déclaré par `@patrol`."""
        ts = tilemap.tile_size
        route = [pygame.Vector2((tx + 0.5) * ts, (ty + 0.5) * ts) for tx, ty in tilemap.route_for(spawn)]
        if len(route) > 1:
            first_leg = route[1] - route[0]
            angle = math.atan2(first_leg.y, first_leg.x)
        else:
            angle = most_open_angle(tilemap, route[0], GUARD_VISION_RANGE)
        return cls(route, angle)

    @classmethod
    def reinforcement(cls, tilemap, spawn_tile: tuple[int, int], post_tile: tuple[int, int], stay: float = REINFORCE_STAY_TIME) -> Guard:
        """Renfort arrivé en `spawn_tile` ; une fois sa fouille finie, il patrouille entre son arrivée et `post_tile`."""
        ts = tilemap.tile_size
        route = [pygame.Vector2((tx + 0.5) * ts, (ty + 0.5) * ts) for tx, ty in (spawn_tile, post_tile)]
        leg = route[1] - route[0]
        guard = cls(route, math.atan2(leg.y, leg.x) if leg.length_squared() else 0.0)
        guard.alerted = True
        guard.is_reinforcement = True
        guard.lifetime = stay
        return guard

    # --- Propriétés ----------------------------------------------------------
    @property
    def facing(self) -> pygame.Vector2:
        return pygame.Vector2(math.cos(self.angle), math.sin(self.angle))

    @property
    def _radius(self) -> float:
        return self.width / 2

    @property
    def expired(self) -> bool:
        """Vrai si un renfort a fini son temps de présence ; il ne se retire jamais en pleine poursuite."""
        return self.lifetime is not None and self.lifetime <= 0 and self.state is not GuardState.CHASE

    def can_catch(self, target) -> bool:
        """Un garde en poursuite attrape le joueur dès qu'il le touche."""
        return self.state is GuardState.CHASE and self.pos.distance_to(target.pos) <= GUARD_CATCH_DISTANCE

    # --- Alerte radio --------------------------------------------------------
    def alarm(self, tilemap, point: pygame.Vector2) -> bool:
        """Message radio : le joueur a été vu en `point`. Va y enquêter (sauf en pleine poursuite)."""
        return self.state is not GuardState.CHASE and self._investigate(tilemap, point)

    # --- Ouïe ----------------------------------------------------------------
    def hear(self, tilemap, source: pygame.Vector2, radius: float) -> bool:
        """Réagit à un bruit : va enquêter s'il l'entend et peut l'atteindre. Renvoie vrai si c'est le cas."""
        if self.state is GuardState.CHASE or not hears(tilemap, self.pos, source, radius):
            return False
        already_there = self.state is GuardState.INVESTIGATE and self.destination is not None and self.destination.distance_to(source) < tilemap.tile_size
        return already_there or self._investigate(tilemap, source)

    # --- Boucle --------------------------------------------------------------
    def update(self, dt: float, tilemap, target=None) -> None:
        """`target` : le joueur (ou toute entité à repérer) ; il doit exposer `pos` et `detectability`."""
        if self.lifetime is not None:
            self.lifetime = max(0.0, self.lifetime - dt)
        before = pygame.Vector2(self.pos)
        seen = target is not None and can_see(tilemap, self.pos, self.angle, GUARD_FOV, GUARD_VISION_RANGE, target.pos)
        if seen and _detectability(target, self.pos.distance_to(target.pos)) <= 0:
            seen = False  # un officier en uniforme dans son champ de vision ne retient pas son attention : la patrouille continue
        self.sees_target = seen
        self._update_awareness(dt, target, seen)

        if self.awareness >= 1 and self.state is not GuardState.CHASE:
            self._start_chase(target)

        if self.state is GuardState.CHASE:
            self._update_chase(dt, tilemap, target, seen)
        elif seen:  # il a un doute : il s'arrête et fixe le joueur le temps de trancher
            self._look_at(target.pos, dt)
        elif self.state is GuardState.PATROL:
            self._update_patrol(dt, tilemap)
        elif self.state is GuardState.INVESTIGATE:
            self._update_investigate(dt, tilemap)
        else:
            self._update_search(dt, tilemap)
        self._animate(dt, self.pos.distance_to(before))

    def _animate(self, dt: float, moved: float) -> None:
        self._age += dt
        self.walk_phase = (self.walk_phase + moved * STRIDE_RATE) % math.tau
        self.stride += ((1.0 if moved > 0 else 0.0) - self.stride) * min(1.0, dt * STRIDE_BLEND)

    # --- Méfiance ------------------------------------------------------------
    def _update_awareness(self, dt: float, target, seen: bool) -> None:
        if seen:
            distance = self.pos.distance_to(target.pos)
            closeness = 1 - distance / GUARD_VISION_RANGE
            rate = (1 + GUARD_DETECT_CLOSE_BONUS * closeness) * _detectability(target, distance) * self._alert_factor(ALERT_DETECT_MULT) * self.sensitivity / GUARD_DETECT_TIME
            self.awareness = min(1.0, self.awareness + rate * dt)
        elif self.state is not GuardState.CHASE:
            self.awareness = max(0.0, self.awareness - GUARD_AWARENESS_DECAY * dt)

    def _alert_factor(self, factor: float) -> float:
        return factor if self.alerted else 1.0

    def _speed(self, kind: str) -> float:
        """Vitesse selon l'état ; l'alerte accélère tout sauf la poursuite (déjà à fond)."""
        return GUARD_SPEED[kind] * (1.0 if kind == "chase" else self._alert_factor(ALERT_SPEED_MULT))

    # --- États ---------------------------------------------------------------
    def _update_patrol(self, dt: float, tilemap) -> None:
        if not self.follower.finished:
            self._walk(dt, tilemap, self._speed("patrol"))
            if self.follower.finished:
                self._wait_timer = GUARD_WAIT_TIME
            return
        if len(self.route) == 1:  # sentinelle : reprend son regard d'origine
            self._turn_to(self.home_angle, dt)
        self._wait_timer -= dt
        if self._wait_timer <= 0:
            self.route_index = (self.route_index + 1) % len(self.route)
            self._head_to(tilemap, self.route[self.route_index])

    def _update_investigate(self, dt: float, tilemap) -> None:
        self._walk(dt, tilemap, self._speed("investigate"))
        if self.follower.finished:
            self.state = GuardState.SEARCH
            self._search_time = 0.0
            self._search_base = self.angle

    def _update_search(self, dt: float, tilemap) -> None:
        self._search_time += dt
        sweep = GUARD_SEARCH_SWEEP * math.sin(math.tau * self._search_time / GUARD_SEARCH_TIME)
        self._turn_to(self._search_base + sweep, dt)
        if self._search_time >= GUARD_SEARCH_TIME:
            self._resume_patrol(tilemap)

    def _update_chase(self, dt: float, tilemap, target, seen: bool) -> None:
        if seen:
            self._lose_sight_timer = 0.0
            self.destination = pygame.Vector2(target.pos)
            self.awareness = 1.0
            self._chase_path(dt, tilemap, target)
        else:
            self._lose_sight_timer += dt
            if self._lose_sight_timer >= GUARD_LOSE_SIGHT_TIME:
                self._give_up_chase(tilemap)
                return
        if seen and self.follower.finished:
            self._look_at(target.pos, dt)
        else:
            self._walk(dt, tilemap, self._speed("chase"))

    def _start_chase(self, target) -> None:
        self.state = GuardState.CHASE
        self.awareness = 1.0
        self._lose_sight_timer = 0.0
        self._repath_timer = 0.0
        if target is not None:
            self.destination = pygame.Vector2(target.pos)

    def _chase_path(self, dt: float, tilemap, target) -> None:
        """Foncer droit sur le joueur si la voie est libre, sinon A* (recalculé à intervalle limité)."""
        if has_clearance(tilemap, self.pos, target.pos, self._radius):
            self.follower.set_path([target.pos])
            return
        self._repath_timer -= dt
        if self._repath_timer <= 0:
            self._repath_timer = GUARD_REPATH_INTERVAL
            self.follower.set_path(plan_route(tilemap, self.pos, target.pos, self._radius) or [])

    def _give_up_chase(self, tilemap) -> None:
        self.awareness = GUARD_AWARENESS_AFTER_CHASE
        if self.destination is None or not self._investigate(tilemap, self.destination):
            self._resume_patrol(tilemap)

    # --- Transitions ---------------------------------------------------------
    def _investigate(self, tilemap, point: pygame.Vector2) -> bool:
        path = plan_route(tilemap, self.pos, point, self._radius)
        if path is None:  # inaccessible (zone fermée) : on n'y va pas
            return False
        self.state = GuardState.INVESTIGATE
        self.destination = pygame.Vector2(point)
        self.follower.set_path(path)
        return True

    def _resume_patrol(self, tilemap) -> None:
        self.state = GuardState.PATROL
        self._head_to(tilemap, self.route[self.route_index])

    def _head_to(self, tilemap, point: pygame.Vector2) -> None:
        self.follower.set_path(plan_route(tilemap, self.pos, point, self._radius) or [])
        if self.follower.finished:  # déjà sur place (ou point inaccessible) : on marque la pause
            self._wait_timer = GUARD_WAIT_TIME

    # --- Mouvement -----------------------------------------------------------
    def _walk(self, dt: float, tilemap, speed: float) -> None:
        delta = self.follower.step(self.pos, speed * dt)
        if delta.length_squared() > 0:
            self._turn_to(math.atan2(delta.y, delta.x), dt)
            self.move(delta, tilemap)

    def _turn_to(self, angle: float, dt: float) -> None:
        self.angle = rotate_towards(self.angle, angle, GUARD_TURN_SPEED * dt)

    def _look_at(self, point: pygame.Vector2, dt: float) -> None:
        offset = point - self.pos
        if offset.length_squared() > 0:
            self._turn_to(math.atan2(offset.y, offset.x), dt)

    # --- Dessin --------------------------------------------------------------
    def draw(self, surface: pygame.Surface, camera) -> None:
        center = camera.world_to_screen(self.pos)
        color = COLORS[f"guard_{self.state.value}"]
        draw_guard(
            surface,
            center,
            self.facing,
            color,
            self.walk_phase,
            self.stride,
            aiming=self.state is GuardState.CHASE,
            reinforcement=self.is_reinforcement,
            time=self._age,
        )
        if self.is_reinforcement:  # anneau bleu : on reconnaît les renforts au premier coup d'œil
            pygame.draw.circle(surface, COLORS["guard_reinforcement"], center, round(self._radius) + 3, 2)
