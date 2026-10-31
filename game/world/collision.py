"""Collisions AABB contre la grille de tuiles.

Principe : on déplace la boîte sur l'axe X puis on corrige, puis sur l'axe Y puis on corrige.
Séparer les axes permet de glisser le long d'un mur au lieu de s'y coller.
Fonctions pures (aucune dépendance à pygame) : faciles à tester.
"""
from __future__ import annotations

import math
from typing import NamedTuple

EPS = 1e-6  # tolérance : une boîte "collée" à un mur ne doit pas être vue comme chevauchante


class MoveResult(NamedTuple):
    x: float  # coin haut-gauche après déplacement
    y: float
    hit_x: bool  # collision rencontrée sur l'axe X
    hit_y: bool


def _span(start: float, size: float, tile_size: int) -> tuple[int, int]:
    """Indices (min, max) des tuiles recouvertes par le segment [start, start + size]."""
    first = math.floor(start / tile_size + EPS)
    last = math.ceil((start + size) / tile_size - EPS) - 1
    return first, max(first, last)


def _resolve_x(tilemap, x: float, y: float, w: float, h: float, sx: float) -> tuple[float, bool]:
    ts = tilemap.tile_size
    tx0, tx1 = _span(x, w, ts)
    ty0, ty1 = _span(y, h, ts)
    hit = False
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            if tilemap.is_solid(tx, ty):
                x = min(x, tx * ts - w) if sx > 0 else max(x, (tx + 1) * ts)
                hit = True
    return x, hit


def _resolve_y(tilemap, x: float, y: float, w: float, h: float, sy: float) -> tuple[float, bool]:
    ts = tilemap.tile_size
    tx0, tx1 = _span(x, w, ts)
    ty0, ty1 = _span(y, h, ts)
    hit = False
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            if tilemap.is_solid(tx, ty):
                y = min(y, ty * ts - h) if sy > 0 else max(y, (ty + 1) * ts)
                hit = True
    return y, hit


def move_and_collide(tilemap, x: float, y: float, w: float, h: float, dx: float, dy: float) -> MoveResult:
    """Déplace la boîte (x, y, w, h) de (dx, dy) en respectant les tuiles solides.

    Le déplacement est découpé en pas d'au plus une demi-tuile : même un très gros `dx`
    ne permet pas de traverser un mur fin (effet « tunnel »).
    """
    steps = max(1, math.ceil(max(abs(dx), abs(dy)) / (tilemap.tile_size / 2)))
    sx, sy = dx / steps, dy / steps
    hit_x = hit_y = False
    for _ in range(steps):
        if sx:
            x, hit = _resolve_x(tilemap, x + sx, y, w, h, sx)
            hit_x |= hit
        if sy:
            y, hit = _resolve_y(tilemap, x, y + sy, w, h, sy)
            hit_y |= hit
    return MoveResult(x, y, hit_x, hit_y)
