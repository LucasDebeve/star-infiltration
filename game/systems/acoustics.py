"""Acoustique d'une carte : combien de murs étouffent un son, et combien la salle résonne.

Pur (aucune sortie sonore). Un mur ou une porte fermée entre la source et le joueur rend le son sourd (filtre passe-bas, volume
réduit) ; la surface de la zone connexe où retentit un son décide de son écho : un hangar résonne, un bureau non.
"""
from __future__ import annotations

import pygame

from game.settings import MUFFLE_CUTOFFS, REVERB_AREAS
from game.world.raycast import count_solid_tiles


def muffle_level(walls: int) -> int:
    """Niveau de filtrage (0 = net) pour `walls` murs ou portes fermées entre la source et l'auditeur."""
    return max(0, min(walls, len(MUFFLE_CUTOFFS) - 1))


def reverb_level(area: int) -> int:
    """Niveau d'écho (0 aucun, 1 salle, 2 grande salle) d'une zone de `area` tuiles."""
    return sum(1 for threshold in REVERB_AREAS if area >= threshold)


class Acoustics:
    def __init__(self, tilemap) -> None:
        self.tilemap = tilemap

    def walls(self, source, listener) -> int:
        return count_solid_tiles(self.tilemap, source, listener)

    def reverb_at(self, pos) -> int:
        tx, ty = self.tilemap.world_to_tile(*pygame.Vector2(pos))
        return reverb_level(self.tilemap.region_size(tx, ty))

    def effects(self, source, listener) -> dict:
        """Réglages d'un son venu de `source` entendu depuis `listener` : seulement ce qui n'est pas neutre (`walls`, `reverb`)."""
        result = {}
        walls = self.walls(source, listener)
        if walls:
            result["walls"] = walls
        reverb = self.reverb_at(source)
        if reverb:
            result["reverb"] = reverb
        return result

    def own(self, listener) -> dict:
        """Réglages d'un son que fait le joueur lui-même : il résonne dans sa salle, sans mur entre eux."""
        reverb = self.reverb_at(listener)
        return {"reverb": reverb} if reverb else {}
