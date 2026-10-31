"""Dessin des tuiles de sol et de mur selon le thème, mis en cache (une petite surface par variante).

Les variantes sont choisies par un hachage de la position de la tuile : la même carte est toujours dessinée pareil,
et le décor n'a pas l'air d'un carrelage. Le thème impérial garde son damier d'origine.
"""
from __future__ import annotations

import random

import pygame

from game.world.themes import Theme

VARIANTS = 6
_cache: dict[tuple, pygame.Surface] = {}


def variant_of(tx: int, ty: int) -> int:
    """Variante (0..VARIANTS-1) de la tuile, déterministe."""
    return ((tx * 73856093) ^ (ty * 19349663)) % VARIANTS


def floor_tile(theme: Theme, size: int, tx: int, ty: int) -> pygame.Surface:
    variant = (tx + ty) % 2 if theme.floor_style == "deck" else variant_of(tx, ty)
    key = (theme.id, "floor", size, variant)
    tile = _cache.get(key)
    if tile is None:
        tile = _cache[key] = _build_floor(theme, size, variant)
    return tile


def wall_tile(theme: Theme, size: int, tx: int, ty: int) -> pygame.Surface:
    variant = 0 if theme.wall_style == "plate" else variant_of(tx, ty)
    key = (theme.id, "wall", size, variant)
    tile = _cache.get(key)
    if tile is None:
        tile = _cache[key] = _build_wall(theme, size, variant)
    return tile


def _shade(color, factor: float):
    return tuple(max(0, min(255, round(c * factor))) for c in color)


def _build_floor(theme: Theme, size: int, variant: int) -> pygame.Surface:
    tile = pygame.Surface((size, size))
    rng = random.Random(f"{theme.id}-floor-{variant}")
    if theme.floor_style == "deck":
        tile.fill(theme.floor_a if variant == 0 else theme.floor_b)
    elif theme.floor_style == "soil":
        tile.fill(_shade(theme.floor_a, rng.uniform(0.92, 1.08)))
        for _ in range(rng.randrange(5, 9)):  # feuilles, mousse, brindilles
            color = rng.choice(theme.detail)
            x, y = rng.randrange(size - 4), rng.randrange(size - 3)
            if rng.random() < 0.3:
                pygame.draw.line(tile, color, (x, y), (x + rng.randrange(3, 8), y + rng.randrange(-2, 3)), 1)
            else:
                pygame.draw.ellipse(tile, color, (x, y, rng.randrange(3, 7), rng.randrange(2, 5)))
    else:  # sable
        tile.fill(_shade(theme.floor_a, rng.uniform(0.95, 1.05)))
        for i in range(2):  # petites rides du vent
            y = size * (i + 1) // 3 + rng.randrange(-3, 4)
            pygame.draw.arc(tile, theme.detail[1], (rng.randrange(-8, 6), y, size, 8), 0.3, 2.9, 1)
        for _ in range(rng.randrange(3, 7)):  # cailloux
            pygame.draw.circle(tile, rng.choice(theme.detail), (rng.randrange(2, size - 2), rng.randrange(2, size - 2)), 1)
    return tile


def _build_wall(theme: Theme, size: int, variant: int) -> pygame.Surface:
    tile = pygame.Surface((size, size))
    rng = random.Random(f"{theme.id}-wall-{variant}")
    tile.fill(theme.wall)
    if theme.wall_style == "timber":
        for x in range(0, size, 8):  # rondins verticaux
            pygame.draw.line(tile, _shade(theme.wall, 0.72), (x, 0), (x, size), 1)
            pygame.draw.line(tile, _shade(theme.wall, 1.12), (x + 1, 0), (x + 1, size), 1)
        for _ in range(rng.randrange(1, 3)):  # nœuds du bois
            pygame.draw.circle(tile, _shade(theme.wall, 0.6), (rng.randrange(3, size - 3), rng.randrange(6, size - 6)), 2)
        for _ in range(rng.randrange(0, 3)):  # mousse au sommet
            pygame.draw.ellipse(tile, (58, 88, 44), (rng.randrange(0, size - 8), rng.randrange(1, 5), rng.randrange(5, 10), 3))
    elif theme.wall_style == "adobe":
        for y in (size // 3, 2 * size // 3):  # joints de briques de terre
            pygame.draw.line(tile, _shade(theme.wall, 0.86), (0, y), (size, y), 1)
            offset = rng.randrange(6, 16)
            for x in range(offset, size, 16):
                pygame.draw.line(tile, _shade(theme.wall, 0.86), (x, y - size // 3), (x, y), 1)
        if variant % 3 == 0:  # une fissure
            x = rng.randrange(6, size - 6)
            pygame.draw.lines(tile, _shade(theme.wall, 0.7), False, [(x, 6), (x + 2, 12), (x - 1, 18), (x + 1, 24)], 1)
    pygame.draw.rect(tile, theme.wall_top, (0, 0, size, 3))
    pygame.draw.rect(tile, theme.wall_shade, (0, size - 4, size, 4))
    return tile


def bars_tile(size: int, horizontal: bool) -> pygame.Surface:
    """Barreaux d'une cellule (transparents, posés sur le sol) : une ligne de barres entre deux rails, dans le sens de la ligne."""
    key = ("bars", size, horizontal)
    tile = _cache.get(key)
    if tile is None:
        tile = pygame.Surface((size, size), pygame.SRCALPHA)
        from game.settings import COLORS

        metal, dark = COLORS["cell_bars"], COLORS["player_outline"]
        mid = size // 2
        rail = (0, mid - 9, size, 4) if horizontal else (mid - 9, 0, 4, size)
        rail2 = (0, mid + 5, size, 4) if horizontal else (mid + 5, 0, 4, size)
        for r in (rail, rail2):
            pygame.draw.rect(tile, dark, pygame.Rect(r).inflate(2, 2))
            pygame.draw.rect(tile, metal, r)
        for k in range(3, size, 8):  # barreaux, perpendiculaires aux rails
            a, b = ((k, mid - 8), (k, mid + 8)) if horizontal else ((mid - 8, k), (mid + 8, k))
            pygame.draw.line(tile, dark, a, b, 5)
            pygame.draw.line(tile, _shade(metal, 1.15), a, b, 3)
        _cache[key] = tile
    return tile
