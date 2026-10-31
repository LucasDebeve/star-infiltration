"""Éléments de décor de la carte : caisses, vaisseaux, champs de force. Données pures, sans dessin.

Les tuiles `B`, `S` et `F` de la carte sont regroupées en « props » (une caisse de 2 × 2 tuiles est un seul
conteneur, pas quatre caisses). Le dessin est dans `prop_art.py`.
"""
from __future__ import annotations

from dataclasses import dataclass

BOX_KIND, SHIP_KIND, FIELD_KIND = "box", "ship", "field"
FACINGS = ("N", "E", "S", "O")  # direction du nez d'un vaisseau (O = ouest)
DEFAULT_FACING = "N"


@dataclass(frozen=True)
class Prop:
    kind: str
    x: int  # tuile en haut à gauche
    y: int
    w: int  # taille en tuiles
    h: int
    facing: str = DEFAULT_FACING  # vaisseaux seulement

    @property
    def tiles(self) -> list[tuple[int, int]]:
        return [(self.x + dx, self.y + dy) for dy in range(self.h) for dx in range(self.w)]


def _components(tiles: set[tuple[int, int]]) -> list[set[tuple[int, int]]]:
    """Groupes de tuiles contiguës (4 voisins)."""
    remaining, groups = set(tiles), []
    while remaining:
        start = min(remaining)  # ordre stable : la carte donne toujours les mêmes props dans le même ordre
        group, todo = set(), [start]
        while todo:
            x, y = todo.pop()
            if (x, y) in group:
                continue
            group.add((x, y))
            todo += [t for t in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)) if t in remaining and t not in group]
        remaining -= group
        groups.append(group)
    return groups


def _bounds(group: set[tuple[int, int]]) -> tuple[int, int, int, int]:
    xs, ys = [t[0] for t in group], [t[1] for t in group]
    return min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1


def find_props(tiles_by_kind: dict[str, set[tuple[int, int]]], ship_facings: dict[tuple[int, int], str]) -> list[Prop]:
    """Regroupe les tuiles de chaque genre en props.

    - caisses : un rectangle plein devient un seul conteneur ; une forme irrégulière, autant de caisses que de tuiles ;
    - vaisseaux : la coque doit être un rectangle plein (sinon ValueError) ; son orientation vient de `@ship` ;
    - champs de force : une ligne droite d'une tuile d'épaisseur (sinon ValueError).
    """
    props: list[Prop] = []
    for group in _components(tiles_by_kind.get(BOX_KIND, set())):
        x, y, w, h = _bounds(group)
        if len(group) == w * h:
            props.append(Prop(BOX_KIND, x, y, w, h))
        else:
            props += [Prop(BOX_KIND, tx, ty, 1, 1) for tx, ty in sorted(group)]
    for group in _components(tiles_by_kind.get(SHIP_KIND, set())):
        x, y, w, h = _bounds(group)
        if len(group) != w * h:
            raise ValueError(f"Le vaisseau en ({x}, {y}) doit être un rectangle plein de tuiles 'S'")
        facing = next((ship_facings[t] for t in sorted(group) if t in ship_facings), DEFAULT_FACING)
        props.append(Prop(SHIP_KIND, x, y, w, h, facing))
    for group in _components(tiles_by_kind.get(FIELD_KIND, set())):
        x, y, w, h = _bounds(group)
        if len(group) != w * h or min(w, h) != 1:
            raise ValueError(f"Le champ de force en ({x}, {y}) doit être une ligne droite d'une tuile d'épaisseur")
        props.append(Prop(FIELD_KIND, x, y, w, h))
    return props
