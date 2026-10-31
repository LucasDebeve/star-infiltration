"""Caméra 2D : suit une cible avec lissage, reste dans les limites du monde, et s'exprime un peu.

Elle prend de l'avance dans le sens du déplacement, se penche vers le curseur, zoome selon la situation (accroupi,
poursuite, piratage, capture) et tremble sous les chocs (alerte, coupure de courant, portes). Tout est lissé et
indépendant de la cadence d'images. `offset`/`world_to_screen` incluent la secousse ; le zoom est une mise à l'échelle
de l'image finale, que la scène applique (voir `zoom_point` / `screen_to_world` pour passer d'un repère à l'autre).
"""
import math

import pygame

from game.settings import (
    CAMERA_AIM_LEAN,
    CAMERA_AIM_MAX,
    CAMERA_LOOKAHEAD,
    CAMERA_LOOKAHEAD_SMOOTHING,
    CAMERA_SHAKE_MAX,
    CAMERA_SHAKE_SPEED,
    CAMERA_SMOOTHING,
    CAMERA_TRAUMA_DECAY,
    CAMERA_ZOOM_SMOOTHING,
    PLAYER_SPEED,
)


def _clamp_axis(value: float, view: float, world: float) -> float:
    if world <= view:  # monde plus petit que l'écran : on le centre
        return (world - view) / 2
    return max(0.0, min(value, world - view))


class Camera:
    def __init__(
        self,
        view_w: int,
        view_h: int,
        world_w: int,
        world_h: int,
        smoothing: float = CAMERA_SMOOTHING,
    ) -> None:
        self.view_size = pygame.Vector2(view_w, view_h)
        self.world_size = pygame.Vector2(world_w, world_h)
        self.smoothing = smoothing
        self.pos = pygame.Vector2()  # coin haut-gauche de la vue, en coordonnées monde
        self.lead = pygame.Vector2()  # avance actuelle (px) : déplacement + inclinaison vers le curseur
        self.zoom = 1.0
        self.zoom_target = 1.0
        self.pivot = self.view_size / 2  # point de l'écran qui reste fixe quand on zoome : le joueur (le centre par défaut)
        self.trauma = 0.0  # intensité de la secousse en cours (0..1)
        self.shake_enabled = True
        self.shake = pygame.Vector2()  # décalage de secousse du moment (px)
        self._clock = 0.0

    def goal_for(self, target: pygame.Vector2) -> pygame.Vector2:
        """Position de caméra qui centre `target`, bornée aux limites du monde."""
        return pygame.Vector2(
            _clamp_axis(target.x - self.view_size.x / 2, self.view_size.x, self.world_size.x),
            _clamp_axis(target.y - self.view_size.y / 2, self.view_size.y, self.world_size.y),
        )

    def snap_to(self, target: pygame.Vector2) -> None:
        """Placement immédiat (début de niveau, téléportation)."""
        self.pos = self.goal_for(target)

    def update(self, target: pygame.Vector2, dt: float, velocity=None, aim=None) -> None:
        """Avance d'un pas. `velocity` : vitesse du joueur (px/s) pour l'avance ; `aim` : curseur par rapport au centre
        de l'écran (px), pour l'inclinaison. Sans eux, la caméra se contente de suivre."""
        self._update_lead(dt, velocity, aim)
        goal = self.goal_for(pygame.Vector2(target) + self.lead)
        if self.smoothing <= 0:
            self.pos = goal
        else:  # lissage exponentiel indépendant du framerate
            self.pos += (goal - self.pos) * (1 - math.exp(-self.smoothing * dt))
        self.zoom += (self.zoom_target - self.zoom) * (1 - math.exp(-CAMERA_ZOOM_SMOOTHING * dt))
        self._update_shake(dt)

    def _update_lead(self, dt: float, velocity, aim) -> None:
        desired = pygame.Vector2()
        if velocity is not None:
            speed = pygame.Vector2(velocity)
            if speed.length_squared() > 1e-6:
                desired += speed.normalize() * CAMERA_LOOKAHEAD * min(1.0, speed.length() / PLAYER_SPEED["run"])
        if aim is not None:
            lean = pygame.Vector2(aim) * CAMERA_AIM_LEAN
            if lean.length() > CAMERA_AIM_MAX:
                lean.scale_to_length(CAMERA_AIM_MAX)
            desired += lean
        self.lead += (desired - self.lead) * (1 - math.exp(-CAMERA_LOOKAHEAD_SMOOTHING * dt))

    # --- Secousses -----------------------------------------------------------
    def add_trauma(self, amount: float) -> None:
        """Un choc : les secousses s'additionnent (bornées à 1) et s'apaisent d'elles-mêmes."""
        if self.shake_enabled:
            self.trauma = min(1.0, self.trauma + max(0.0, amount))

    def _update_shake(self, dt: float) -> None:
        self._clock += dt
        self.trauma = max(0.0, self.trauma - CAMERA_TRAUMA_DECAY * dt)
        if not self.shake_enabled or self.trauma <= 0:
            self.shake.update(0, 0)
            return
        amplitude = CAMERA_SHAKE_MAX * self.trauma**2  # le carré : les petits chocs restent discrets
        t = self._clock * CAMERA_SHAKE_SPEED
        self.shake.update(  # bruit pseudo-aléatoire continu (deux sinusoïdes déphasées par axe), déterministe
            amplitude * (math.sin(t * 1.0 + 0.3) + math.sin(t * 1.71 + 1.9)) / 2,
            amplitude * (math.sin(t * 1.13 + 2.2) + math.sin(t * 1.93 + 0.7)) / 2,
        )

    # --- Zoom ------------------------------------------------------------------
    def crop_rect(self) -> pygame.Rect:
        """Partie de l'image du monde qu'il faut agrandir pour obtenir le zoom, de sorte que `pivot` ne bouge pas."""
        w, h = round(self.view_size.x), round(self.view_size.y)
        cw, ch = round(w / self.zoom), round(h / self.zoom)
        keep = 1 - 1 / self.zoom
        left = max(0, min(w - cw, round(self.pivot.x * keep)))
        top = max(0, min(h - ch, round(self.pivot.y * keep)))
        return pygame.Rect(left, top, cw, ch)

    def follow_pivot(self, target) -> None:
        """Centre le zoom sur `target` (position monde, ici le joueur), là où il se trouve à l'écran : même au bord de la carte,
        où la caméra ne peut pas le centrer, il reste bien visible."""
        self.pivot.update(self.world_to_screen(target))

    def zoom_point(self, screen_point) -> tuple[float, float]:
        """Où atterrit à l'écran un point dessiné avant la mise à l'échelle du zoom (le zoom est centré sur `pivot`)."""
        cx, cy = self.pivot
        return cx + (screen_point[0] - cx) * self.zoom, cy + (screen_point[1] - cy) * self.zoom

    @property
    def offset(self) -> tuple[int, int]:
        """Décalage entier utilisé pour dessiner (évite le tremblement des sprites), secousse comprise."""
        return round(self.pos.x + self.shake.x), round(self.pos.y + self.shake.y)

    @property
    def visible_rect(self) -> pygame.Rect:
        ox, oy = self.offset
        return pygame.Rect(ox, oy, int(self.view_size.x), int(self.view_size.y))

    def world_to_screen(self, point) -> tuple[int, int]:
        ox, oy = self.offset
        return round(point[0] - ox), round(point[1] - oy)

    def screen_to_world(self, point) -> pygame.Vector2:
        """Point de l'écran (souris) -> monde, en tenant compte du zoom appliqué à l'image."""
        cx, cy = self.pivot
        point = (cx + (point[0] - cx) / self.zoom, cy + (point[1] - cy) / self.zoom)
        ox, oy = self.offset
        return pygame.Vector2(point[0] + ox, point[1] + oy)
