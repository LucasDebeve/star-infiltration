"""Champs de force commutables et boutons : modèle, lecture de la section de configuration, couleurs de liaison.

Dans la carte, une lettre minuscule `a`–`z` est une tuile de champ (toutes les tuiles de même lettre forment
un seul champ) et un chiffre `1`–`9` un bouton. Après une ligne `---`, une instruction par ligne :

    field a closed          # `closed` : actif (bloquant) au départ ; `open` : inactif (traversable)
    field b open
    button 1 toggles a b    # chaque pression inverse l'état de tous les champs liés

Un champ qui doit s'activer alors qu'une entité occupe sa zone reste « en attente » (il clignote) et ne
devient solide que lorsque la zone est libre : personne ne se retrouve coincé dans un champ.
Logique pure : le rendu est dans `prop_art.py`, l'interaction dans `entities/field_button.py`.
"""

from __future__ import annotations

import string
from dataclasses import dataclass, field
from typing import Iterable

from game.settings import LINK_COLOR_COUNT

FIELD_LETTERS = string.ascii_lowercase
BUTTON_DIGITS = "123456789"
STATES = {"closed": True, "open": False}  # état de départ : vrai = actif (bloquant)

Tile = tuple[int, int]
Run = tuple[int, int, int, int]  # x, y, largeur, hauteur (en tuiles) d'une ligne droite de champ
Cell = tuple[int, int, int]  # x, y, numéro de ligne du fichier


@dataclass
class Field:
    id: str
    tiles: list[Tile]
    runs: list[Run]
    start_active: bool
    active: bool  # effectivement solide
    target: bool  # état demandé : il diffère de `active` quand le champ attend que sa zone soit libre
    color: int = 0  # indice de teinte `link_N`
    buttons: list[str] = field(default_factory=list)

    @property
    def pending(self) -> bool:
        """Doit s'activer mais en est empêché par quelqu'un dans sa zone."""
        return self.target and not self.active


@dataclass(frozen=True)
class ButtonSpec:
    id: str
    tile: Tile
    fields: tuple[str, ...]
    color: int = 0


@dataclass
class SwitchConfig:
    fields: dict[str, tuple[bool, int]] = field(default_factory=dict)  # lettre -> (actif au départ, ligne)
    buttons: dict[str, tuple[tuple[str, ...], int]] = field(default_factory=dict)  # chiffre -> (champs, ligne)


def _error(line: int, message: str) -> ValueError:
    return ValueError(f"Ligne {line} : {message}")


# --- Lecture de la configuration ---------------------------------------------
def parse_config(lines: Iterable[tuple[int, str]]) -> SwitchConfig:
    """Lit les instructions `field` et `button` (lignes numérotées du fichier ; vides et commentaires `;` ignorés)."""
    config = SwitchConfig()
    for number, raw in lines:
        text = raw.split(";", 1)[0].strip()
        if not text:
            continue
        words = text.split()
        if words[0] == "field":
            _parse_field(config, number, words)
        elif words[0] == "button":
            _parse_button(config, number, words)
        else:
            raise _error(number, f"instruction inconnue {words[0]!r} (attendu 'field' ou 'button')")
    return config


def _parse_field(config: SwitchConfig, number: int, words: list[str]) -> None:
    if len(words) != 3:
        raise _error(number, "syntaxe attendue : 'field <lettre> closed|open'")
    letter, state = words[1], words[2]
    if len(letter) != 1 or letter not in FIELD_LETTERS:
        raise _error(number, f"{letter!r} n'est pas un nom de champ valide (une lettre minuscule de a à z)")
    if state not in STATES:
        raise _error(number, f"état inconnu {state!r} pour le champ '{letter}' (attendu 'closed' ou 'open')")
    if letter in config.fields:
        raise _error(number, f"le champ '{letter}' est déjà déclaré (ligne {config.fields[letter][1]})")
    config.fields[letter] = (STATES[state], number)


def _parse_button(config: SwitchConfig, number: int, words: list[str]) -> None:
    if len(words) < 4 or words[2] != "toggles":
        raise _error(number, "syntaxe attendue : 'button <chiffre> toggles <lettre> [<lettre> ...]'")
    digit, targets = words[1], tuple(words[3:])
    if len(digit) != 1 or digit not in BUTTON_DIGITS:
        raise _error(number, f"{digit!r} n'est pas un nom de bouton valide (un chiffre de 1 à 9)")
    if digit in config.buttons:
        raise _error(number, f"le bouton '{digit}' est déjà déclaré (ligne {config.buttons[digit][1]})")
    for letter in targets:
        if len(letter) != 1 or letter not in FIELD_LETTERS:
            raise _error(number, f"{letter!r} n'est pas un nom de champ valide (une lettre minuscule de a à z)")
    if len(set(targets)) != len(targets):
        raise _error(number, f"le bouton '{digit}' liste plusieurs fois le même champ")
    config.buttons[digit] = (targets, number)


# --- Construction et vérification --------------------------------------------
def build_switches(config: SwitchConfig, field_cells: dict[str, list[Cell]], button_cells: dict[str, list[Cell]]) -> tuple[dict[str, Field], dict[str, ButtonSpec], list[str]]:
    """Croise la carte et la configuration. Erreurs (ValueError, en français, avec la ligne) ; renvoie aussi les avertissements."""
    for letter, cells in field_cells.items():
        if letter not in config.fields:
            raise _error(cells[0][2], f"le champ '{letter}' est utilisé dans la carte mais n'est pas déclaré (ajouter 'field {letter} closed' ou 'field {letter} open' après '---')")
    for digit, cells in button_cells.items():
        if digit not in config.buttons:
            raise _error(cells[0][2], f"le bouton '{digit}' est utilisé dans la carte mais n'est pas déclaré (ajouter 'button {digit} toggles <champ>' après '---')")
        if len(cells) > 1:
            raise _error(cells[1][2], f"le bouton '{digit}' est placé deux fois (déjà ligne {cells[0][2]})")
    for letter, (_, line) in config.fields.items():
        if letter not in field_cells:
            raise _error(line, f"le champ '{letter}' est déclaré mais n'apparaît pas dans la carte")
    for digit, (targets, line) in config.buttons.items():
        if digit not in button_cells:
            raise _error(line, f"le bouton '{digit}' est déclaré mais n'apparaît pas dans la carte")
        for letter in targets:
            if letter not in config.fields:
                raise _error(line, f"le bouton '{digit}' référence le champ '{letter}', qui n'existe pas (déclarez 'field {letter} closed|open')")

    fields: dict[str, Field] = {}
    for letter, cells in sorted(field_cells.items()):
        tiles = [(x, y) for x, y, _ in cells]
        runs = straight_runs(tiles)
        if runs is None:
            raise _error(cells[0][2], f"le champ '{letter}' doit être formé de lignes droites d'une tuile d'épaisseur")
        active = config.fields[letter][0]
        fields[letter] = Field(letter, sorted(tiles), runs, active, active, active)

    colors_by_button, colors_by_field = link_colors({d: t for d, (t, _) in config.buttons.items()})
    buttons: dict[str, ButtonSpec] = {}
    for digit, cells in sorted(button_cells.items()):
        targets = config.buttons[digit][0]
        buttons[digit] = ButtonSpec(digit, (cells[0][0], cells[0][1]), targets, colors_by_button[digit])
        for letter in targets:
            fields[letter].buttons.append(digit)
    for letter, f in fields.items():
        f.color = colors_by_field.get(letter, 0)

    warnings = [f"Ligne {config.fields[letter][1]} : le champ '{letter}' n'est lié à aucun bouton, il gardera son état de départ" for letter, f in fields.items() if not f.buttons]
    return fields, buttons, warnings


def straight_runs(tiles: Iterable[Tile]) -> list[Run] | None:
    """Regroupe des tuiles contiguës en lignes droites ; `None` si un groupe n'est pas une ligne d'une tuile d'épaisseur."""
    remaining, runs = set(tiles), []
    while remaining:
        start = min(remaining)
        group, todo = set(), [start]
        while todo:
            x, y = todo.pop()
            if (x, y) in group:
                continue
            group.add((x, y))
            todo += [t for t in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)) if t in remaining and t not in group]
        remaining -= group
        xs, ys = [t[0] for t in group], [t[1] for t in group]
        w, h = max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
        if len(group) != w * h or min(w, h) != 1:
            return None
        runs.append((min(xs), min(ys), w, h))
    return runs


def link_colors(links: dict[str, tuple[str, ...]]) -> tuple[dict[str, int], dict[str, int]]:
    """Une teinte par ensemble de boutons et de champs reliés entre eux (directement ou par un champ commun).

    Ainsi chaque bouton partage sa couleur avec tous ses champs, même quand un champ répond à plusieurs boutons.
    Renvoie (teinte de chaque bouton, teinte de chaque champ lié). Les groupes sont numérotés dans l'ordre des boutons.
    """
    parent: dict[str, str] = {}

    def find(node: str) -> str:
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for digit, targets in links.items():
        for letter in targets:
            parent[find("b" + digit)] = find("f" + letter)
    index: dict[str, int] = {}
    for digit in sorted(links):
        root = find("b" + digit)
        index.setdefault(root, len(index) % LINK_COLOR_COUNT)
    buttons = {digit: index[find("b" + digit)] for digit in links}
    fields = {letter: index[find("f" + letter)] for targets in links.values() for letter in targets}
    return buttons, fields


def box_overlaps_tiles(box: tuple[float, float, float, float], tiles: Iterable[Tile], tile_size: int, eps: float = 1e-6) -> bool:
    """Vrai si la boîte (x, y, largeur, hauteur), en pixels, empiète sur l'une des tuiles (simple contact : non)."""
    x, y, w, h = box
    for tx, ty in tiles:
        if x < (tx + 1) * tile_size - eps and x + w > tx * tile_size + eps and y < (ty + 1) * tile_size - eps and y + h > ty * tile_size + eps:
            return True
    return False
