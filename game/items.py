"""Objets du joueur : types d'objets et inventaire. Logique pure, sans fenêtre."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ItemKind(Enum):
    KEYCARD = "keycard"  # badge : ouvre les portes de niveau inférieur ou égal au sien
    DATA = "data"  # données volées sur un terminal : objectif de la mission
    DECOY = "decoy"  # leurre sonore, consommable
    UNIFORM = "uniform"  # uniforme impérial dérobé : se porte (touche dédiée) pour passer pour un membre du personnel


@dataclass(frozen=True)
class Item:
    kind: ItemKind
    level: int = 0  # niveau d'un badge (sans objet pour les autres objets)

    @property
    def short_label(self) -> str:
        """Libellé court pour les petits emplacements de l'inventaire."""
        return _short(self)

    @property
    def label(self) -> str:
        if self.kind is ItemKind.KEYCARD:
            return f"Badge niv. {self.level}"
        return {ItemKind.DATA: "Données", ItemKind.DECOY: "Leurre", ItemKind.UNIFORM: "Uniforme impérial"}[self.kind]


_SHORT_LABELS = {ItemKind.DATA: "Données", ItemKind.DECOY: "Leurre", ItemKind.UNIFORM: "Uniforme"}


def _short(item: Item) -> str:
    return f"Badge {item.level}" if item.kind is ItemKind.KEYCARD else _SHORT_LABELS[item.kind]


_ORDER = {kind: i for i, kind in enumerate(ItemKind)}


class Inventory:
    def __init__(self) -> None:
        self._stacks: dict[Item, int] = {}
        self.uniform_worn = False  # l'uniforme est enfilé (et pas seulement dans le sac) : c'est lui que les portes du personnel contrôlent

    @property
    def has_uniform(self) -> bool:
        return self.count_kind(ItemKind.UNIFORM) > 0

    def toggle_uniform(self) -> bool:
        """Enfile ou retire l'uniforme. Sans uniforme, ne fait rien. Renvoie vrai s'il est porté ensuite."""
        self.uniform_worn = self.has_uniform and not self.uniform_worn
        return self.uniform_worn

    def add(self, item: Item, count: int = 1) -> None:
        if count < 1:
            raise ValueError("count doit être positif")
        self._stacks[item] = self._stacks.get(item, 0) + count

    def remove(self, item: Item, count: int = 1) -> bool:
        """Retire `count` exemplaires ; renvoie faux (sans rien changer) s'il n'y en a pas assez."""
        if self.count(item) < count:
            return False
        remaining = self._stacks[item] - count
        if remaining:
            self._stacks[item] = remaining
        else:
            del self._stacks[item]
        return True

    def count(self, item: Item) -> int:
        return self._stacks.get(item, 0)

    def count_kind(self, kind: ItemKind) -> int:
        return sum(n for item, n in self._stacks.items() if item.kind is kind)

    def has_keycard(self, level: int) -> bool:
        """Vrai si un badge de niveau au moins `level` est possédé (le niveau 0 n'en demande aucun)."""
        return level <= 0 or any(i.kind is ItemKind.KEYCARD and i.level >= level for i in self._stacks)

    def stacks(self) -> list[tuple[Item, int]]:
        """Piles triées (type, puis niveau) : ordre stable pour l'affichage."""
        return sorted(self._stacks.items(), key=lambda entry: (_ORDER[entry[0].kind], entry[0].level))
