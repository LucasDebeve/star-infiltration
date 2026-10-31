"""Décor vivant de la carte : où poser les lanternes sur les murs, et les bouches de vapeur au sol.

Placement pur et déterministe (hachage des positions) : la même carte donne toujours le même décor, sans qu'il faille
rien écrire dans le fichier de carte. Ce décor est purement visuel : il ne bloque ni le passage ni la vue.
"""
from __future__ import annotations

from dataclasses import dataclass

from game.settings import DECOR_ONE_IN, DECOR_SPACING, VENT_ONE_IN, VENT_PERIOD, VENT_SPACING, VENT_START_CLEARANCE

NEIGHBORS4 = ((1, 0), (-1, 0), (0, 1), (0, -1))
NEIGHBORS8 = tuple((dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if (dx, dy) != (0, 0))


def _hash(tx: int, ty: int, salt: int) -> int:
    return ((tx * 73856093) ^ (ty * 19349663) ^ (salt * 83492791)) & 0x7FFFFFFF


@dataclass(frozen=True)
class WallDecor:
    kind: str  # "lantern" (les genres possibles sont ceux que déclarent les thèmes)
    tile: tuple[int, int]  # tuile de mur qui le porte
    face: tuple[int, int]  # direction (dx, dy) vers le passage qu'il regarde
    phase: float  # 0..1 : décale son animation de celles de ses voisins
    color_index: int  # choix dans les couleurs du thème

    def center(self, tile_size: int) -> tuple[float, float]:
        return (self.tile[0] + 0.5) * tile_size, (self.tile[1] + 0.5) * tile_size


@dataclass(frozen=True)
class Vent:
    tile: tuple[int, int]  # tuile de sol qui porte la grille
    direction: tuple[int, int]  # sens du jet : à l'opposé du mur voisin
    phase: float  # 0..1
    period: float  # secondes entre deux jets

    def center(self, tile_size: int) -> tuple[float, float]:
        return (self.tile[0] + 0.5) * tile_size, (self.tile[1] + 0.5) * tile_size


def _busy(tilemap, tx: int, ty: int) -> bool:
    """Une porte, un champ de force, un bouton ou un point de la carte à proximité : on n'y met pas de décor."""
    from game.world.tilemap import DOOR, GATE, OPEN_DOOR

    if any(tilemap.tile_at(tx + dx, ty + dy) in (DOOR, OPEN_DOOR, GATE) for dx, dy in NEIGHBORS8):
        return True
    near = {(tx + dx, ty + dy) for dx in range(-1, 2) for dy in range(-1, 2)}
    return any((s.tx, s.ty) in near for s in tilemap.spawns) or any(b.tile in near for b in tilemap.buttons.values())


def place_wall_decor(tilemap) -> list[WallDecor]:
    """Éléments de décor (lanternes) sur les murs qui bordent un passage, espacés ; les genres viennent du thème."""
    kinds = tilemap.theme.decor
    if not kinds:
        return []
    from game.world.tilemap import WALL

    placed: list[WallDecor] = []
    taken: set[tuple[int, int]] = set()
    for ty in range(tilemap.height):
        for tx in range(tilemap.width):
            if tilemap.tile_at(tx, ty) != WALL or _hash(tx, ty, 1) % DECOR_ONE_IN != 0:
                continue
            open_sides = [d for d in NEIGHBORS4 if tilemap.in_bounds(tx + d[0], ty + d[1]) and not tilemap.is_solid(tx + d[0], ty + d[1])]
            if len(open_sides) != 1 or _busy(tilemap, tx, ty):  # un seul côté ouvert : un mur plat, pas un angle ni un pilier
                continue
            if any((tx + dx, ty + dy) in taken for dx in range(-DECOR_SPACING, DECOR_SPACING + 1) for dy in range(-DECOR_SPACING, DECOR_SPACING + 1)):
                continue
            h = _hash(tx, ty, 2)
            taken.add((tx, ty))
            placed.append(WallDecor(kinds[h % len(kinds)], (tx, ty), open_sides[0], (h >> 8) % 100 / 100, h >> 16))
    return placed


def place_vents(tilemap) -> list[Vent]:
    """Bouches de vapeur au pied des murs (seulement si le thème en a), loin du départ et des passages."""
    if tilemap.theme.vent_color is None:
        return []
    from game.world.tilemap import FLOOR

    start = tilemap.spawns_of("player")
    vents: list[Vent] = []
    for ty in range(tilemap.height):
        for tx in range(tilemap.width):
            if tilemap.tile_at(tx, ty) != FLOOR or _hash(tx, ty, 3) % VENT_ONE_IN != 0:
                continue
            walls = [d for d in NEIGHBORS4 if tilemap.is_solid(tx + d[0], ty + d[1])]
            if len(walls) != 1 or _busy(tilemap, tx, ty):
                continue
            if start and max(abs(start[0].tx - tx), abs(start[0].ty - ty)) < VENT_START_CLEARANCE:
                continue
            if any(max(abs(v.tile[0] - tx), abs(v.tile[1] - ty)) < VENT_SPACING for v in vents):
                continue
            h = _hash(tx, ty, 4)
            lo, hi = VENT_PERIOD
            vents.append(Vent((tx, ty), (-walls[0][0], -walls[0][1]), (h >> 4) % 100 / 100, lo + (h >> 12) % 100 / 100 * (hi - lo)))
    return vents
