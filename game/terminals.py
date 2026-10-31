"""Terminaux : ce que chacun sait faire, déclaré dans la carte (directive `@terminal`). Données pures.

Un terminal n'a pas tous les pouvoirs par défaut : sans directive, il ne sert qu'à télécharger des données.
    @terminal x,y -> data lights cameras cells  (dans n'importe quel ordre)
    @terminal x,y -> cameras:ab                 (seulement les caméras des groupes a et b ; `cameras` seul = toutes)
"""
from __future__ import annotations

from dataclasses import dataclass

DATA, LIGHTS, CAMERAS, CELLS = "data", "lights", "cameras", "cells"
CAPABILITIES = (DATA, CAMERAS, CELLS, LIGHTS)  # l'ordre du menu
DEFAULT_CAPABILITIES = (DATA,)
LABELS = {
    DATA: "Télécharger les données",
    CAMERAS: "Désactiver les caméras",
    LIGHTS: "Couper la lumière de la salle",
    CELLS: "Ouvrir les cellules",
}


@dataclass(frozen=True)
class TerminalSpec:
    tile: tuple[int, int]
    capabilities: tuple[str, ...] = DEFAULT_CAPABILITIES
    camera_groups: str | None = None  # None : toutes les caméras de la carte ; sinon les lettres de leurs groupes

    def can(self, capability: str) -> bool:
        return capability in self.capabilities

    def controls(self, group: str) -> bool:
        """Ce terminal commande-t-il les caméras du groupe `group` ?"""
        return self.can(CAMERAS) and (self.camera_groups is None or group in self.camera_groups)


def parse_capabilities(text: str) -> tuple[tuple[str, ...], str | None]:
    """Lit `data lights cameras:ab` -> (capacités, groupes de caméras). ValueError (en français) si quelque chose cloche."""
    wanted: list[str] = []
    groups: str | None = None
    for token in text.split():
        name, _, argument = token.partition(":")
        if name not in CAPABILITIES:
            raise ValueError(f"pouvoir inconnu {name!r} (attendu : {', '.join(CAPABILITIES)})")
        if name in wanted:
            raise ValueError(f"pouvoir {name!r} indiqué deux fois")
        if argument:
            if name != CAMERAS:
                raise ValueError(f"seul 'cameras' accepte des groupes (reçu {token!r})")
            if not argument.isalpha() or not argument.islower():
                raise ValueError(f"groupes de caméras illisibles {argument!r} (attendu : des lettres a-z collées, comme 'ab')")
            groups = "".join(dict.fromkeys(argument))
        wanted.append(name)
    if not wanted:
        raise ValueError("aucun pouvoir indiqué")
    return tuple(c for c in CAPABILITIES if c in wanted), groups
