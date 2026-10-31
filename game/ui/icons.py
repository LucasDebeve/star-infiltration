"""Icônes d'objets dessinées à la volée (pas d'image à charger) et halo lumineux."""
from __future__ import annotations

from functools import lru_cache

import pygame

from game.items import Item, ItemKind
from game.settings import COLORS

GLOW_MAX_ALPHA = 90
GLOW_STEPS = 8


def item_color(item: Item) -> tuple[int, int, int]:
    if item.kind is ItemKind.KEYCARD:
        return COLORS[f"badge_{item.level}"]
    if item.kind is ItemKind.UNIFORM:
        return COLORS["uniform"]
    return COLORS["item_data" if item.kind is ItemKind.DATA else "item_decoy"]


@lru_cache(maxsize=64)
def _glow_surface(radius: int, color: tuple[int, int, int]) -> pygame.Surface:
    """Disque dégradé : cercles concentriques de plus en plus opaques vers le centre."""
    surf = pygame.Surface((2 * radius, 2 * radius), pygame.SRCALPHA)
    for i in range(GLOW_STEPS):
        t = (i + 1) / GLOW_STEPS
        pygame.draw.circle(surf, (*color, round(GLOW_MAX_ALPHA * t * t)), (radius, radius), round(radius * (1 - i / GLOW_STEPS)))
    return surf


def draw_glow(surface: pygame.Surface, center: tuple[int, int], radius: int, color: tuple[int, int, int]) -> None:
    surf = _glow_surface(radius, tuple(color))
    surface.blit(surf, surf.get_rect(center=center))


def draw_item_icon(surface: pygame.Surface, item: Item, center: tuple[int, int], size: int) -> None:
    """Dessine l'icône de `item` dans un carré de côté `size` centré sur `center`."""
    color = item_color(item)
    outline = COLORS["player_outline"]
    cx, cy = center
    if item.kind is ItemKind.KEYCARD:
        card = pygame.Rect(0, 0, size, round(size * 0.7))
        card.center = center
        pygame.draw.rect(surface, COLORS["item_body"], card, border_radius=3)
        pygame.draw.rect(surface, color, (card.x, card.y + 2, card.w, max(2, card.h // 4)))  # bande magnétique
        chip = pygame.Rect(card.x + 3, card.centery + 1, max(3, card.w // 4), max(3, card.h // 4))
        pygame.draw.rect(surface, color, chip, border_radius=1)
        for i in range(item.level):  # un point par niveau
            pygame.draw.circle(surface, color, (card.right - 4 - i * 4, card.bottom - 4), 1)
        pygame.draw.rect(surface, outline, card, 1, border_radius=3)
    elif item.kind is ItemKind.DATA:
        chip = pygame.Rect(0, 0, round(size * 0.7), round(size * 0.7))
        chip.center = center
        for i in range(3):  # broches
            offset = chip.y + 2 + i * (chip.h - 4) // 2
            pygame.draw.line(surface, color, (chip.x - 3, offset), (chip.x, offset), 1)
            pygame.draw.line(surface, color, (chip.right, offset), (chip.right + 3, offset), 1)
        pygame.draw.rect(surface, COLORS["item_body"], chip, border_radius=2)
        pygame.draw.rect(surface, color, chip.inflate(-6, -6), 1)
        pygame.draw.circle(surface, color, chip.center, 2)
        pygame.draw.rect(surface, outline, chip, 1, border_radius=2)
    elif item.kind is ItemKind.UNIFORM:  # tunique pliée : épaules, col, insigne
        body = pygame.Rect(0, 0, round(size * 0.78), round(size * 0.74))
        body.center = (cx, cy + 1)
        shoulders = [(body.x - 3, body.y + 5), (body.x + 4, body.y), (body.right - 4, body.y), (body.right + 3, body.y + 5), (body.right - 1, body.y + 9),
                     (body.right - 1, body.bottom), (body.x + 1, body.bottom), (body.x + 1, body.y + 9)]
        pygame.draw.polygon(surface, color, shoulders)
        pygame.draw.polygon(surface, outline, shoulders, 1)
        pygame.draw.polygon(surface, _lighter(color), [(cx - 3, body.y), (cx + 3, body.y), (cx, body.y + 5)])  # col
        pygame.draw.line(surface, outline, (cx, body.y + 5), (cx, body.bottom - 1), 1)  # patte de boutonnage
        pygame.draw.rect(surface, COLORS["status_alert"], (cx + 3, body.y + 8, 3, 3))  # insigne
    else:  # leurre : boîtier rond, voyant et ondes
        radius = max(3, size // 3)
        pygame.draw.circle(surface, COLORS["item_body"], (cx, cy + 1), radius)
        pygame.draw.circle(surface, color, (cx, cy + 1), max(2, radius - 3))
        pygame.draw.circle(surface, outline, (cx, cy + 1), radius, 1)
        for r in (radius + 2, radius + 5):
            rect = pygame.Rect(0, 0, 2 * r, 2 * r)
            rect.center = (cx, cy + 1)
            pygame.draw.arc(surface, color, rect, 0.6, 1.0 + 0.6, 1)
            pygame.draw.arc(surface, color, rect, 3.74, 4.34 + 0.6, 1)


def _lighter(color: tuple[int, int, int]) -> tuple[int, int, int]:
    return tuple(min(255, c + 60) for c in color)
