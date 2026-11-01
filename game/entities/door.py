"""Porte : un groupe de tuiles `D` (ou `J`, porte de cellule à barreaux) qui s'ouvre avec le bon badge, et coulisse à l'écran.

La logique est immédiate : à l'activation, les tuiles deviennent praticables. L'animation (deux vantaux qui
rentrent dans les murs) est purement visuelle, pour ne jamais retarder le joueur.
"""

from __future__ import annotations

import math

import pygame

from game.core import bindings
from game.settings import COLORS, DOOR_NOISE, DOOR_OPEN_TIME, DOOR_REACH
from game.systems.interaction import InteractionContext, Prompt

INSET = 3  # marge des vantaux dans l'épaisseur de la porte
POST_THICKNESS = 6  # montants aux deux extrémités
CHEVRON_WIDTH = 6
CHEVRON_MIN_LENGTH = 14  # en dessous, le vantail est trop court pour porter des chevrons
LAMP_RADIUS = 4
LOCKED_BLINK_SPEED = 5.0  # rad/s : le voyant d'une porte verrouillée pulse


def ease_out(t: float) -> float:
    """Départ vif, arrivée douce."""
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


class Door:
    reach = DOOR_REACH
    hold_time = 0.0

    def __init__(self, tiles: list[tuple[int, int]], level: int, tile_size: int, cell: bool = False, staff: bool = False) -> None:
        self.tiles = list(tiles)
        self.staff = staff  # porte du personnel : seul un uniforme enfilé l'ouvre
        self.cell = cell  # porte de cellule : à barreaux, on voit à travers
        self.level = level  # niveau de badge requis (0 = aucun)
        self.is_open = False
        self.progress = 0.0  # avancement visuel de l'ouverture : 0 fermée, 1 entièrement rentrée
        self._centers = [pygame.Vector2((x + 0.5) * tile_size, (y + 0.5) * tile_size) for x, y in tiles]
        self.anchor = sum(self._centers, pygame.Vector2()) / len(self._centers)
        xs, ys = [t[0] for t in tiles], [t[1] for t in tiles]
        self.rect = pygame.Rect(min(xs) * tile_size, min(ys) * tile_size, (max(xs) - min(xs) + 1) * tile_size, (max(ys) - min(ys) + 1) * tile_size)
        self.horizontal = self.rect.w >= self.rect.h  # vrai : les vantaux coulissent de gauche à droite (passage nord-sud)

    # --- Interaction ---------------------------------------------------------
    def distance_to(self, point: pygame.Vector2) -> float:
        return min(point.distance_to(c) for c in self._centers)

    def prompt(self, inventory) -> Prompt | None:
        if self.is_open:
            return None
        if self.staff:  # le lecteur du poste de contrôle regarde ce qu'on porte, pas ce qu'on a dans le sac
            if inventory.uniform_worn:
                return Prompt("Passer le contrôle")
            if inventory.has_uniform:
                return Prompt(f"Enfilez l'uniforme ({bindings.label('disguise')})", enabled=False)
            return Prompt("Réservé au personnel : uniforme requis", enabled=False)
        if self.cell and self.level == 0:  # verrou électronique : seul un terminal sait l'ouvrir
            return Prompt("Cellule verrouillée : terminal requis", enabled=False)
        if inventory.has_keycard(self.level):
            return Prompt("Déverrouiller la cellule" if self.cell else "Ouvrir")
        return Prompt(f"Badge niv. {self.level} requis", enabled=False)

    def interact(self, ctx: InteractionContext) -> None:
        ctx.tilemap.open_door(self.tiles)
        self.is_open = True
        ctx.events.emit("door_opened", door=self)
        # Une porte qui coulisse s'entend : les gardes proches viennent voir.
        ctx.events.emit("noise", pos=pygame.Vector2(self.anchor), radius=DOOR_NOISE)

    # --- Animation -----------------------------------------------------------
    def update(self, dt: float) -> None:
        if self.is_open and self.progress < 1.0:
            self.progress = min(1.0, self.progress + dt / DOOR_OPEN_TIME)

    @property
    def opening(self) -> bool:
        return self.is_open and self.progress < 1.0

    # --- Dessin --------------------------------------------------------------
    def draw(self, surface: pygame.Surface, camera, unlocked: bool = True) -> None:
        """`unlocked` : le joueur possède le badge (le voyant passe du rouge à la couleur de la porte)."""
        rect = pygame.Rect(camera.world_to_screen(self.rect.topleft), self.rect.size)
        accent = COLORS["uniform"] if self.staff else COLORS[f"badge_{self.level}"]
        self._draw_posts(surface, rect)
        shown = 1.0 - ease_out(self.progress)  # part des vantaux encore visible
        if shown > 0.02:
            half = (rect.w if self.horizontal else rect.h) / 2
            length = max(1, round(half * shown))
            for first in (True, False):
                leaf = self._leaf_rect(rect, length, first)
                if self.cell:
                    self._draw_bars(surface, leaf)
                else:
                    self._draw_leaf(surface, leaf, accent, first, length)
        self._draw_lamp(surface, rect, accent, unlocked)

    def _leaf_rect(self, rect: pygame.Rect, length: int, first: bool) -> pygame.Rect:
        """Vantail de `length` px collé à une extrémité (il rentre dans le mur en rétrécissant)."""
        if self.horizontal:
            x = rect.x if first else rect.right - length
            return pygame.Rect(x, rect.y + INSET, length, rect.h - 2 * INSET)
        y = rect.y if first else rect.bottom - length
        return pygame.Rect(rect.x + INSET, y, rect.w - 2 * INSET, length)

    def _draw_bars(self, surface: pygame.Surface, leaf: pygame.Rect) -> None:
        """Vantail à barreaux d'une cellule : deux rails et des barres, comme les barreaux fixes qui l'encadrent."""
        metal, edge = COLORS["cell_bars"], COLORS["player_outline"]
        if self.horizontal:
            for y in (leaf.y + 1, leaf.bottom - 4):
                pygame.draw.rect(surface, metal, (leaf.x, y, leaf.w, 3))
            for x in range(leaf.x + 2, leaf.right - 1, 7):
                pygame.draw.line(surface, edge, (x, leaf.y + 1), (x, leaf.bottom - 2), 4)
                pygame.draw.line(surface, metal, (x, leaf.y + 1), (x, leaf.bottom - 2), 2)
        else:
            for x in (leaf.x + 1, leaf.right - 4):
                pygame.draw.rect(surface, metal, (x, leaf.y, 3, leaf.h))
            for y in range(leaf.y + 2, leaf.bottom - 1, 7):
                pygame.draw.line(surface, edge, (leaf.x + 1, y), (leaf.right - 2, y), 4)
                pygame.draw.line(surface, metal, (leaf.x + 1, y), (leaf.right - 2, y), 2)

    def _draw_posts(self, surface: pygame.Surface, rect: pygame.Rect) -> None:
        """Montants métalliques de part et d'autre du passage, dans l'épaisseur du mur."""
        frame, edge = COLORS["door_frame"], COLORS["player_outline"]
        for first in (True, False):
            if self.horizontal:
                post = pygame.Rect(rect.x if first else rect.right - POST_THICKNESS, rect.y, POST_THICKNESS, rect.h)
            else:
                post = pygame.Rect(rect.x, rect.y if first else rect.bottom - POST_THICKNESS, rect.w, POST_THICKNESS)
            pygame.draw.rect(surface, frame, post)
            pygame.draw.rect(surface, edge, post, 1)

    def _draw_leaf(self, surface: pygame.Surface, leaf: pygame.Rect, accent, first: bool, length: int) -> None:
        metal, light, edge = COLORS["door_metal"], COLORS["door_metal_light"], COLORS["player_outline"]
        pygame.draw.rect(surface, metal, leaf)
        # Reflets : haut et gauche clairs, bas et droite sombres.
        pygame.draw.line(surface, light, leaf.topleft, leaf.topright, 1)
        pygame.draw.line(surface, light, leaf.topleft, leaf.bottomleft, 1)
        pygame.draw.line(surface, COLORS["door_frame"], leaf.bottomleft, leaf.bottomright, 1)
        pygame.draw.line(surface, COLORS["door_frame"], leaf.topright, leaf.bottomright, 1)
        # Liseré de couleur sur le bord qui rencontre l'autre vantail.
        if self.horizontal:
            seam = pygame.Rect(leaf.right - 3 if first else leaf.x, leaf.y, 3, leaf.h)
        else:
            seam = pygame.Rect(leaf.x, leaf.bottom - 3 if first else leaf.y, leaf.w, 3)
        pygame.draw.rect(surface, accent, seam)
        if length >= CHEVRON_MIN_LENGTH:
            self._draw_chevrons(surface, leaf, first)
        pygame.draw.rect(surface, edge, leaf, 1)

    def _draw_chevrons(self, surface: pygame.Surface, leaf: pygame.Rect, first: bool) -> None:
        """Une bande de danger en biais près du bord central."""
        hazard = COLORS["hazard_yellow"]
        if self.horizontal:
            x = leaf.right - 6 - CHEVRON_WIDTH if first else leaf.x + 6
            pygame.draw.polygon(surface, hazard, [(x, leaf.bottom - 3), (x + CHEVRON_WIDTH // 2, leaf.bottom - 3), (x + CHEVRON_WIDTH, leaf.y + 3), (x + CHEVRON_WIDTH // 2, leaf.y + 3)])
        else:
            y = leaf.bottom - 6 - CHEVRON_WIDTH if first else leaf.y + 6
            pygame.draw.polygon(surface, hazard, [(leaf.x + 3, y), (leaf.x + 3, y + CHEVRON_WIDTH // 2), (leaf.right - 3, y + CHEVRON_WIDTH), (leaf.right - 3, y + CHEVRON_WIDTH // 2)])

    def _draw_lamp(self, surface: pygame.Surface, rect: pygame.Rect, accent, unlocked: bool) -> None:
        """Voyant au centre du passage : rouge qui pulse (verrouillée), couleur du badge (prête), blanc (en train de s'ouvrir), vert (ouverte)."""
        ticks = pygame.time.get_ticks() / 1000
        if self.opening:
            color = (255, 255, 255)
        elif self.is_open:
            color = COLORS["status_calm"]
        elif unlocked:
            color = accent
        else:
            pulse = 0.55 + 0.45 * math.sin(ticks * LOCKED_BLINK_SPEED)
            color = tuple(round(c * pulse) for c in COLORS["door_locked"])
        center = rect.center
        pygame.draw.circle(surface, COLORS["player_outline"], center, LAMP_RADIUS + 2)
        pygame.draw.circle(surface, color, center, LAMP_RADIUS)
        pygame.draw.circle(surface, tuple(min(255, c + 90) for c in color), (center[0] - 1, center[1] - 1), 1)
        if self.level > 0 and not self.is_open:  # un petit repère par niveau de badge, à côté du voyant
            for i in range(self.level):
                offset = (i - (self.level - 1) / 2) * 8
                x, y = (center[0] + offset, center[1] + LAMP_RADIUS + 7) if self.horizontal else (center[0] + LAMP_RADIUS + 7, center[1] + offset)
                pygame.draw.rect(surface, accent, (round(x) - 2, round(y) - 2, 4, 4))


def build_doors(tilemap) -> list[Door]:
    return [Door(tiles, level, tilemap.tile_size, cell=all(t in tilemap.cell_doors for t in tiles), staff=all(t in tilemap.uniform_doors for t in tiles)) for tiles, level in tilemap.door_groups()]
