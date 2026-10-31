"""Arrière-plans des menus : champ d'étoiles animé (menu principal) ou capture floutée du jeu (pause)."""
from __future__ import annotations

import math
import random

import pygame

from game.settings import COLORS, PAUSE_ZOOM, PAUSE_ZOOM_SPEED, SPACE_PARALLAX, SPACE_STAR_COUNT

STAR_COUNT = 140
BLUR_FACTOR = 8  # la capture est réduite de ce facteur puis agrandie : flou bon marché
DIM_ALPHA = 150
CRUISER_START = 640  # décalage initial du croiseur, en pixels


class Starfield:
    """Étoiles qui défilent lentement, scintillent, et un croiseur en silhouette qui dérive."""

    def __init__(self, size: tuple[int, int], seed: int = 7, ship: bool = True) -> None:
        rng = random.Random(seed)  # fixe : le fond est identique à chaque lancement
        self.size = size
        self.ship = ship  # montrer le croiseur qui dérive (pas pour le générique, qui ne veut que des étoiles)
        self.stars = [
            [rng.uniform(0, size[0]), rng.uniform(0, size[1]), rng.uniform(4, 26), rng.choice((1, 1, 1, 2)), rng.uniform(0, math.tau)]
            for _ in range(STAR_COUNT)
        ]
        self.time = 0.0

    def update(self, dt: float) -> None:
        self.time += dt
        for star in self.stars:
            star[0] = (star[0] - star[2] * dt) % self.size[0]

    def draw(self, surface: pygame.Surface) -> None:
        w, h = surface.get_size()
        surface.fill(COLORS["background"])
        for x, y, speed, radius, phase in self.stars:
            level = round(110 + 100 * (0.5 + 0.5 * math.sin(self.time * 1.6 + phase)) * min(1.0, speed / 12))
            pygame.draw.circle(surface, (level, level, min(255, level + 25)), (round(x * w / self.size[0]), round(y * h / self.size[1])), radius)
        if self.ship:
            self._draw_cruiser(surface)

    def _draw_cruiser(self, surface: pygame.Surface) -> None:
        """Un croiseur en forme de coin, sombre, qui traverse très lentement l'écran."""
        w, h = surface.get_size()
        cx = (self.time * 9 + CRUISER_START) % (w + 700) - 350  # visible dès l'ouverture du menu
        cy = h * 0.62 + 14 * math.sin(self.time * 0.2)
        hull = [(cx - 330, cy), (cx + 280, cy - 26), (cx + 330, cy), (cx + 280, cy + 26)]
        pygame.draw.polygon(surface, (24, 28, 40), hull)
        pygame.draw.polygon(surface, (46, 52, 70), hull, 2)
        pygame.draw.polygon(surface, (30, 36, 50), [(cx - 120, cy), (cx + 40, cy - 12), (cx + 40, cy + 12)])
        for i in range(6):  # moteurs
            glow = 120 + round(60 * math.sin(self.time * 3 + i))
            pygame.draw.circle(surface, (glow // 2, glow, 255), (round(cx - 332), round(cy - 15 + i * 6)), 3)


class SnapshotBackdrop:
    """Image figée du jeu, floutée et assombrie, qui se rapproche très lentement (la pause « respire »)."""

    def __init__(self, frame: pygame.Surface) -> None:
        w, h = frame.get_size()
        small = pygame.transform.smoothscale(frame, (max(1, w // BLUR_FACTOR), max(1, h // BLUR_FACTOR)))
        self.image = pygame.transform.smoothscale(small, (w, h))
        veil = pygame.Surface((w, h), pygame.SRCALPHA)
        veil.fill((*COLORS["background"], DIM_ALPHA))
        self.image.blit(veil, (0, 0))
        self.time = 0.0
        self._shown = self.image
        self._scale = 1.0

    @property
    def scale(self) -> float:
        """Échelle actuelle : de 1 à 1 + PAUSE_ZOOM, en décélérant."""
        return 1.0 + PAUSE_ZOOM * (1.0 - math.exp(-PAUSE_ZOOM_SPEED * self.time))

    def update(self, dt: float) -> None:
        self.time += dt
        scale = self.scale
        if scale - self._scale < 0.0015:  # le zoom a presque fini : inutile de recalculer l'image à chaque pas
            return
        self._scale = scale
        w, h = self.image.get_size()
        crop = pygame.Rect(0, 0, round(w / scale), round(h / scale))
        crop.center = (w // 2, h // 2)
        self._shown = pygame.transform.smoothscale(self.image.subsurface(crop), (w, h))

    def draw(self, surface: pygame.Surface) -> None:
        surface.blit(self._shown, (0, 0))


class SpaceLayer:
    """L'espace derrière les baies : étoiles à parallaxe (plus elles sont loin, moins elles suivent la caméra).

    Dessiné sous la carte : on ne le voit que là où la carte est vide (au-delà d'un champ de force).
    """

    def __init__(self, size: tuple[int, int], seed: int = 11) -> None:
        rng = random.Random(seed)
        self.size = size
        # (x, y, profondeur, rayon, phase) dans un espace de la taille de l'écran, qui se répète.
        self.stars = [
            (rng.uniform(0, size[0]), rng.uniform(0, size[1]), rng.choice(SPACE_PARALLAX), rng.choice((1, 1, 1, 2)), rng.uniform(0, math.tau))
            for _ in range(SPACE_STAR_COUNT)
        ]

    def draw(self, surface: pygame.Surface, camera, time: float = 0.0) -> None:
        w, h = self.size
        cam_x, cam_y = camera.offset
        for x, y, depth, radius, phase in self.stars:
            sx, sy = (x - cam_x * depth) % w, (y - cam_y * depth) % h
            level = round(120 + 110 * (0.5 + 0.5 * math.sin(time * 1.4 + phase)) * (0.45 + depth))
            pygame.draw.circle(surface, (level, level, min(255, level + 30)), (round(sx * surface.get_width() / w), round(sy * surface.get_height() / h)), radius)
