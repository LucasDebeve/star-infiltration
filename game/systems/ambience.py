"""Ambiances sonores des salles : chaque source (moteur, lampe, champ de force, terminal...) bourdonne là où elle est.

Un genre de source = une boucle (voir `settings.AMBIENT_SOURCES`). Les sources du même genre se mélangent en une seule
voix : son volume est la somme de leurs volumes, atténués par la distance et étouffés par les murs et portes fermées qui
les séparent du joueur ; sa balance penche du côté des plus proches. On entend donc le moteur du hangar en y entrant,
le bourdonnement des lampes salle après salle, et plus rien d'une pièce dont la porte est fermée.

`audio` est tout objet qui offre `set_ambient(nom, volume, balance)` et `stop_ambient()` : les tests injectent un faux.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import pygame

from game.core.audio import attenuation, stereo_pan
from game.settings import AMBIENT_FADE_RATE, AMBIENT_REFRESH, AMBIENT_SOURCES, AMBIENT_WALL_DAMPING
from game.world.raycast import count_solid_tiles


@dataclass
class AmbientSource:
    kind: str  # clé de `AMBIENT_SOURCES`
    pos: pygame.Vector2
    active: Callable[[], bool] = field(default=lambda: True)  # faux : la source se tait (terminal piraté, courant coupé...)


def mix(sources, listener, tilemap=None) -> dict[str, tuple[float, float]]:
    """Pour chaque genre : (volume cible 0..1, balance -1..1) entendus depuis `listener`. Pur : aucune sortie sonore."""
    listener = pygame.Vector2(listener)
    levels: dict[str, float] = {}
    pans: dict[str, float] = {}
    for source in sources:
        _, reach, volume = AMBIENT_SOURCES[source.kind]
        distance = source.pos.distance_to(listener)
        if distance >= reach or not source.active():
            continue
        loudness = volume * attenuation(distance, reach)
        if tilemap is not None and loudness > 0:
            loudness *= AMBIENT_WALL_DAMPING ** count_solid_tiles(tilemap, source.pos, listener)
        if loudness <= 0:
            continue
        levels[source.kind] = levels.get(source.kind, 0.0) + loudness
        pans[source.kind] = pans.get(source.kind, 0.0) + loudness * stereo_pan(source.pos.x - listener.x, reach)
    return {kind: (min(1.0, level), pans[kind] / level) for kind, level in levels.items()}


class Ambience:
    def __init__(self, audio, tilemap, sources: list[AmbientSource]) -> None:
        self.audio, self.tilemap, self.sources = audio, tilemap, sources
        self.levels = {kind: 0.0 for kind in AMBIENT_SOURCES}  # volume actuel (lissé) de chaque genre
        self.pans = {kind: 0.0 for kind in AMBIENT_SOURCES}
        self._targets: dict[str, tuple[float, float]] = {}
        self._clock = AMBIENT_REFRESH  # recalcul dès la première image

    def update(self, dt: float, listener) -> None:
        self._clock += dt
        if self._clock >= AMBIENT_REFRESH:
            self._clock = 0.0
            self._targets = mix(self.sources, listener, self.tilemap)
        step = AMBIENT_FADE_RATE * dt
        for kind, (sound, _, _) in AMBIENT_SOURCES.items():
            target, pan = self._targets.get(kind, (0.0, self.pans[kind]))
            current = self.levels[kind]
            self.levels[kind] = min(target, current + step) if target > current else max(target, current - step)
            self.pans[kind] = pan
            self.audio.set_ambient(sound, self.levels[kind], self.pans[kind])

    def stop(self) -> None:
        self.audio.stop_ambient()
        self.levels = {kind: 0.0 for kind in AMBIENT_SOURCES}
