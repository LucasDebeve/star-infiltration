"""Carte en tuiles : chargement depuis un fichier texte, requêtes de collision, rendu.

Format du fichier (voir assets/maps/cruiser.txt) :
    #  mur          .  sol          D  porte (fermée = solide)
    (espace) vide   P  départ du joueur     G  garde     K  badge
    T  terminal     E  sortie               L  leurre sonore
    R  arrivée des renforts (alerte globale)
    B  caisse / conteneur   S  vaisseau (rectangle plein)   F  champ de force (ligne droite)
    a-z  champ de force commutable (toutes les tuiles de même lettre = un champ)   1-9  bouton (sol dessous)
    Solides : mur, porte fermée, caisse, vaisseau, champ de force, vide. Opaques (ils arrêtent la vue, la lumière
    et le bruit) : tous sauf le champ de force, que l'on traverse du regard mais pas du corps.
Les lignes commençant par ';' sont des commentaires. Toutes les lignes de la grille ont la même longueur.

Itinéraire d'un garde (après la grille) : `@patrol x,y -> x1,y1 x2,y2 ...`
    (x, y) est la tuile du garde (un 'G') ; il rejoint ensuite chaque point en boucle.
    Un garde sans itinéraire reste en poste.

Niveau d'une porte : `@door x,y -> n` (n de 0 à 3, une tuile quelconque de la porte).
    0 = s'ouvre sans badge (défaut). n >= 1 demande un badge de niveau n ou plus.
Niveau d'un badge : `@keycard x,y -> n` (défaut 1).
Orientation d'un vaisseau : `@ship x,y -> N|E|S|O` (une tuile quelconque de la coque ; nez vers le nord par défaut).

Champs commutables et boutons : après une ligne `---`, une instruction par ligne (voir `switch_fields.py`) :
    field a closed          `closed` = actif (bloquant) au départ, `open` = inactif (traversable)
    button 1 toggles a b    chaque pression du bouton 1 inverse l'état des champs a et b
Les erreurs de carte (en français) donnent le numéro de ligne du fichier.

Plus tard, un chargeur Tiled (.tmx) pourra produire la même classe `Tilemap`.
"""

from __future__ import annotations

import logging
import math
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import pygame

from game import terminals, tips
from game.objectives import OBJECTIVES
from game.settings import COLORS, DEFAULT_KEYCARD_LEVEL, MAX_BADGE_LEVEL, TILE_SIZE
from game.world import decor_art, prop_art, tile_art
from game.world.decor import Vent, WallDecor, place_vents, place_wall_decor
from game.world.map_settings import NAMES as SETTING_NAMES
from game.world.map_settings import MapSettings, apply_setting
from game.world.props import BOX_KIND, FACINGS, FIELD_KIND, SHIP_KIND, Prop, find_props
from game.world.surveillance import DIRECTIONS, CameraSpec, parse_camera
from game.world.switch_fields import (
    BUTTON_DIGITS,
    FIELD_LETTERS,
    ButtonSpec,
    Field,
    box_overlaps_tiles,
    build_switches,
    parse_config,
)
from game.world.themes import DEFAULT_THEME, THEMES, Theme, get_theme

VOID, FLOOR, WALL, DOOR, OPEN_DOOR, BOX, SHIP, FIELD, GATE, BARS = range(10)
SOLID_TILES = frozenset({VOID, WALL, DOOR, BOX, SHIP, FIELD, BARS})  # une porte ouverte ne l'est plus
OPAQUE_TILES = SOLID_TILES - {FIELD, BARS}  # le champ de force et les barreaux arrêtent le corps, pas le regard ni la lumière
# GATE (champ commutable) n'est dans aucun des deux ensembles : sa solidité dépend de son état (voir `is_solid`).

LEGEND = {" ": VOID, "#": WALL, ".": FLOOR, "D": DOOR, "B": BOX, "S": SHIP, "F": FIELD, "H": BARS}
CELL_DOOR_CHAR = "J"  # porte de cellule : une porte `D` à barreaux, qu'on voit à travers
log = logging.getLogger(__name__)
PROP_TILES = {BOX: BOX_KIND, SHIP: SHIP_KIND, FIELD: FIELD_KIND}
SPAWN_KINDS = {"P": "player", "G": "guard", "K": "keycard", "T": "terminal", "E": "exit", "L": "decoy", "R": "reinforcement", "C": "console", "Q": "prisoner", "U": "uniform"}
COMMENT_PREFIX = ";"
DIRECTIVE_PREFIX = "@"
CONFIG_SEPARATOR = "---"


@dataclass(frozen=True)
class Spawn:
    kind: str
    tx: int
    ty: int
    level: int = 0  # niveau d'un badge

    def center(self, tile_size: int = TILE_SIZE) -> pygame.Vector2:
        return pygame.Vector2((self.tx + 0.5) * tile_size, (self.ty + 0.5) * tile_size)


def _parse_tile(text: str) -> tuple[int, int]:
    x, y = text.strip().split(",")
    return int(x), int(y)


def _parse_tile_and_level(args: str) -> tuple[tuple[int, int], int]:
    """Lit `x,y -> n`."""
    tile_text, level_text = args.split("->")
    return _parse_tile(tile_text), int(level_text)


class Tilemap:
    def __init__(
        self,
        tiles: list[list[int]],
        spawns: list[Spawn],
        tile_size: int = TILE_SIZE,
        patrols: dict[tuple[int, int], list[tuple[int, int]]] | None = None,
    ) -> None:
        self.tiles = tiles
        self.spawns = spawns
        self.tile_size = tile_size
        self.patrols = patrols or {}  # tuile du garde -> points à rejoindre après son poste
        self.door_levels: dict[tuple[int, int], int] = {}  # tuile de porte -> niveau de badge requis
        self.fields: dict[str, Field] = {}  # champs de force commutables, par lettre
        self.buttons: dict[str, ButtonSpec] = {}  # boutons, par chiffre
        self.warnings: list[str] = []  # problèmes non bloquants relevés au chargement
        self._gate_field: dict[tuple[int, int], Field] = {}  # tuile de champ -> son champ
        self.ship_facings: dict[tuple[int, int], str] = {}  # tuile de coque -> orientation (`@ship`)
        self.props: list[Prop] = []  # caisses, vaisseaux, champs de force (voir `rebuild_props`)
        self.terminal_specs: dict[tuple[int, int], terminals.TerminalSpec] = {}  # pouvoirs déclarés (`@terminal`)
        self.cameras: list[CameraSpec] = []  # caméras de surveillance (`@camera`)
        self.uniform_doors: set[tuple[int, int]] = set()  # portes du personnel (`@door x,y -> uniform`) : on ne les ouvre qu'en uniforme
        self.cell_doors: set[tuple[int, int]] = set()  # tuiles de porte qui sont des portes de cellule (`J`) : on voit à travers
        self.ship_hold: float | None = None  # vol de vaisseau : 0 = rayons tracteurs et attaches actifs, 1 = libérés ; None : sans objet
        self.declared_objective: str | None = None  # `@objective` : indispensable quand le point (`C`) sert à plusieurs objectifs
        self.settings = MapSettings()  # réglages propres à la carte (`@lockdown`, `@waves`...)
        self.tip_zones: list[tips.TipZone] = []  # astuces contextuelles (directive `@tip`)
        self.theme: Theme = get_theme(DEFAULT_THEME)  # aspect de la carte (directive `@theme`)
        self.decor: list[WallDecor] = []  # écrans, voyants, lanternes (voir `rebuild_decor`)
        self.vents: list[Vent] = []  # bouches de vapeur
        self.revision = 0  # change à chaque modification des tuiles : invalide les caches (zones, ombres)
        self._regions: list[list[int]] | None = None  # étiquettes de zones connexes, calculées à la demande
        self._region_sizes: dict[int, int] | None = None  # surface de chaque zone (tuiles), calculée avec elles
        self.height = len(tiles)
        self.width = len(tiles[0]) if tiles else 0
        self.has_void = any(VOID in row for row in tiles)  # y a-t-il de l'espace à afficher derrière les murs ?
        self.rebuild_props()

    # --- Chargement ----------------------------------------------------------
    @classmethod
    def from_text(cls, text: str, tile_size: int = TILE_SIZE) -> Tilemap:
        numbered = [(n, line.rstrip("\r")) for n, line in enumerate(text.split("\n"), start=1)]
        separator = next((i for i, (_, line) in enumerate(numbered) if line.strip() == CONFIG_SEPARATOR), None)
        body, config = (numbered, []) if separator is None else (numbered[:separator], numbered[separator + 1 :])
        directives = [(n, line) for n, line in numbered if line.startswith(DIRECTIVE_PREFIX)]
        config = [(n, line) for n, line in config if not line.startswith(DIRECTIVE_PREFIX)]
        rows = [(n, line) for n, line in body if not line.startswith((COMMENT_PREFIX, DIRECTIVE_PREFIX))]
        while rows and rows[-1][1] == "":
            rows.pop()
        if not rows:
            raise ValueError("Carte vide")

        width = len(rows[0][1])
        tiles: list[list[int]] = []
        spawns: list[Spawn] = []
        cell_cells: list[tuple[int, int]] = []
        field_cells: dict[str, list[tuple[int, int, int]]] = {}
        button_cells: dict[str, list[tuple[int, int, int]]] = {}
        for y, (number, line) in enumerate(rows):
            if len(line) != width:
                raise ValueError(f"Ligne {number} de la carte : {len(line)} caractères, {width} attendus")
            row: list[int] = []
            for x, ch in enumerate(line):
                if ch in SPAWN_KINDS:
                    kind = SPAWN_KINDS[ch]
                    spawns.append(Spawn(kind, x, y, DEFAULT_KEYCARD_LEVEL if kind == "keycard" else 0))
                    row.append(FLOOR)
                elif ch in LEGEND:
                    row.append(LEGEND[ch])
                elif ch == CELL_DOOR_CHAR:
                    cell_cells.append((x, y))
                    row.append(DOOR)
                elif ch in FIELD_LETTERS:
                    field_cells.setdefault(ch, []).append((x, y, number))
                    row.append(GATE)
                elif ch in BUTTON_DIGITS:
                    button_cells.setdefault(ch, []).append((x, y, number))
                    row.append(FLOOR)
                else:
                    raise ValueError(f"Ligne {number} : caractère inconnu {ch!r} (colonne {x + 1})")
            tiles.append(row)
        tilemap = cls(tiles, spawns, tile_size)
        tilemap.cell_doors = set(cell_cells)
        tilemap._install_switches(parse_config(config), field_cells, button_cells)
        for number, directive in directives:
            try:
                tilemap._apply_directive(directive)
            except ValueError as error:
                raise ValueError(f"Ligne {number} : {error}") from None
        tilemap.rebuild_props()  # les orientations de `@ship` sont connues : on regroupe les tuiles
        tilemap.rebuild_decor()  # le thème est connu : on pose le décor qui lui va
        return tilemap

    def _install_switches(self, config, field_cells, button_cells) -> None:
        self.fields, self.buttons, self.warnings = build_switches(config, field_cells, button_cells)
        self._gate_field = {tile: f for f in self.fields.values() for tile in f.tiles}
        for warning in self.warnings:
            log.warning(warning)

    def _apply_directive(self, directive: str) -> None:
        name, _, args = directive.partition(" ")
        handlers = {
            "@patrol": self._add_patrol,
            "@door": self._set_door_level,
            "@keycard": self._set_keycard_level,
            "@ship": self._set_ship_facing,
            "@theme": self._set_theme,
            "@tip": self._add_tip,
            "@terminal": self._set_terminal,
            "@objective": self._set_objective,
            "@camera": self._add_camera,
        }
        handlers.update({f"@{n}": self._set_setting for n in SETTING_NAMES})
        if name not in handlers:
            raise ValueError(f"Directive inconnue : {directive!r}")
        handlers[name](directive, args)

    @staticmethod
    def _check_level(directive: str, level: int) -> None:
        if not 0 <= level <= MAX_BADGE_LEVEL:
            raise ValueError(f"{directive!r} : niveau {level} hors de 0..{MAX_BADGE_LEVEL}")

    def terminal_spec(self, tile: tuple[int, int]) -> terminals.TerminalSpec:
        """Les pouvoirs du terminal en `tile` : ceux de la carte, sinon seulement le téléchargement de données."""
        return self.terminal_specs.get(tile) or terminals.TerminalSpec(tile)

    def _set_terminal(self, directive: str, args: str) -> None:
        """`@terminal x,y -> data lights cameras[:groupes]` : ce que sait faire ce terminal."""
        try:
            tile_text, rest = args.split("->")
            tile = _parse_tile(tile_text)
        except ValueError:
            raise ValueError(f"Terminal illisible : {directive!r} (attendu '@terminal x,y -> data lights cameras')") from None
        if not any(s.kind == "terminal" and (s.tx, s.ty) == tile for s in self.spawns):
            raise ValueError(f"{directive!r} : pas de terminal 'T' en {tile}")
        if tile in self.terminal_specs:
            raise ValueError(f"{directive!r} : ce terminal est déjà configuré")
        try:
            capabilities, groups = terminals.parse_capabilities(rest)
        except ValueError as error:
            raise ValueError(f"{directive!r} : {error}") from None
        self.terminal_specs[tile] = terminals.TerminalSpec(tile, capabilities, groups)

    def _add_camera(self, directive: str, args: str) -> None:
        """`@camera x,y -> N|E|S|O [groupe] [amplitude]` : une caméra fixée au mur `x,y`, qui regarde dans cette direction."""
        try:
            tile_text, rest = args.split("->")
            tile = _parse_tile(tile_text)
        except ValueError:
            raise ValueError(f"Caméra illisible : {directive!r} (attendu '@camera x,y -> N|E|S|O [groupe] [amplitude]')") from None
        try:
            spec = parse_camera(tile, rest)
        except ValueError as error:
            raise ValueError(f"{directive!r} : {error}") from None
        if self.tile_at(*tile) != WALL:
            raise ValueError(f"{directive!r} : une caméra se fixe sur un mur '#'")
        dx, dy = DIRECTIONS[spec.facing]
        if self.is_solid(tile[0] + dx, tile[1] + dy):
            raise ValueError(f"{directive!r} : la caméra regarderait contre un mur ou un obstacle")
        if any(c.tile == tile for c in self.cameras):
            raise ValueError(f"{directive!r} : il y a déjà une caméra ici")
        self.cameras.append(spec)

    def target_ship(self) -> Prop | None:
        """Le vaisseau à voler : celui qui est le plus près de la zone d'extraction (la passerelle d'embarquement)."""
        exits = self.spawns_of("exit")
        ships = [p for p in self.props if p.kind == SHIP_KIND]
        if not exits or not ships:
            return None
        ex, ey = exits[0].tx + 0.5, exits[0].ty + 0.5
        return min(ships, key=lambda p: (p.x + p.w / 2 - ex) ** 2 + (p.y + p.h / 2 - ey) ** 2)

    @property
    def cells_openable(self) -> bool:
        """Un terminal de la carte sait-il ouvrir les cellules ?"""
        return any(spec.can(terminals.CELLS) for spec in self.terminal_specs.values())

    def _set_objective(self, directive: str, args: str) -> None:
        name = args.strip()
        if name not in OBJECTIVES:
            raise ValueError(f"Objectif inconnu : {directive!r} (attendu : {', '.join(OBJECTIVES)})")
        if self.declared_objective is not None:
            raise ValueError(f"{directive!r} : l'objectif est déjà indiqué")
        self.declared_objective = name

    def _set_setting(self, directive: str, args: str) -> None:
        name = directive.split()[0][1:]
        try:
            self.settings = apply_setting(self.settings, name, args)
        except ValueError as error:
            raise ValueError(f"{directive!r} : {error}") from None

    @property
    def ambient(self) -> tuple[int, int, int]:
        """Lumière ambiante de la carte : la sienne (`@ambient`), sinon celle de son thème."""
        return self.settings.ambient or self.theme.ambient

    def _add_tip(self, directive: str, args: str) -> None:
        """`@tip x,y -> nom [rayon]` : une astuce affichée quand le joueur s'approche de la tuile (rayon en tuiles)."""
        try:
            tile_text, rest = args.split("->")
            tile = _parse_tile(tile_text)
            parts = rest.split()
            name = parts[0]
            radius = float(parts[1]) if len(parts) > 1 else tips.DEFAULT_RADIUS
        except (ValueError, IndexError):
            raise ValueError(f"Astuce illisible : {directive!r} (attendu '@tip x,y -> nom [rayon]')") from None
        if name not in tips.TIPS:
            raise ValueError(f"Astuce inconnue : {directive!r} (attendu : {', '.join(tips.TIPS)})")
        if not self.in_bounds(*tile) or radius <= 0:
            raise ValueError(f"{directive!r} : tuile hors de la carte ou rayon nul")
        self.tip_zones.append(tips.TipZone(name, tile, radius))

    def _set_theme(self, directive: str, args: str) -> None:
        name = args.strip()
        if name not in THEMES:
            raise ValueError(f"Thème inconnu : {directive!r} (attendu : {', '.join(THEMES)})")
        self.theme = THEMES[name]

    def _set_door_level(self, directive: str, args: str) -> None:
        if args.split("->")[-1].strip() == "uniform":
            self._set_uniform_door(directive, args)
            return
        try:
            tile, level = _parse_tile_and_level(args)
        except ValueError:
            raise ValueError(f"Porte illisible : {directive!r} (attendu '@door x,y -> n')") from None
        self._check_level(directive, level)
        if self.tile_at(*tile) != DOOR:
            raise ValueError(f"{directive!r} : pas de porte 'D' en {tile}")
        for door_tile in self._connected_doors(tile):
            self.door_levels[door_tile] = level

    def _set_uniform_door(self, directive: str, args: str) -> None:
        """`@door x,y -> uniform` : une porte réservée au personnel, qui ne s'ouvre qu'avec l'uniforme impérial **enfilé**."""
        try:
            tile = _parse_tile(args.split("->")[0])
        except ValueError:
            raise ValueError(f"Porte illisible : {directive!r} (attendu '@door x,y -> n' ou '@door x,y -> uniform')") from None
        if self.tile_at(*tile) != DOOR or tile in self.cell_doors:
            raise ValueError(f"{directive!r} : pas de porte 'D' en {tile}")
        self.uniform_doors.update(self._connected_doors(tile))

    def _set_ship_facing(self, directive: str, args: str) -> None:
        try:
            tile_text, facing = args.split("->")
            tile, facing = _parse_tile(tile_text), facing.strip()
        except ValueError:
            raise ValueError(f"Vaisseau illisible : {directive!r} (attendu '@ship x,y -> N|E|S|O')") from None
        if facing not in FACINGS:
            raise ValueError(f"{directive!r} : orientation {facing!r} inconnue (attendu {'/'.join(FACINGS)})")
        if self.tile_at(*tile) != SHIP:
            raise ValueError(f"{directive!r} : pas de vaisseau 'S' en {tile}")
        self.ship_facings[tile] = facing

    def rebuild_decor(self) -> None:
        self.decor = place_wall_decor(self)
        self.vents = place_vents(self)

    def rebuild_props(self) -> None:
        """Regroupe les tuiles `B`, `S`, `F` en caisses, vaisseaux et champs de force."""
        by_kind: dict[str, set[tuple[int, int]]] = {kind: set() for kind in PROP_TILES.values()}
        for y, row in enumerate(self.tiles):
            for x, tile in enumerate(row):
                if tile in PROP_TILES:
                    by_kind[PROP_TILES[tile]].add((x, y))
        self.props = find_props(by_kind, self.ship_facings)

    def _set_keycard_level(self, directive: str, args: str) -> None:
        try:
            tile, level = _parse_tile_and_level(args)
        except ValueError:
            raise ValueError(f"Badge illisible : {directive!r} (attendu '@keycard x,y -> n')") from None
        self._check_level(directive, level)
        for i, spawn in enumerate(self.spawns):
            if spawn.kind == "keycard" and (spawn.tx, spawn.ty) == tile:
                self.spawns[i] = Spawn("keycard", spawn.tx, spawn.ty, level)
                return
        raise ValueError(f"{directive!r} : pas de badge 'K' en {tile}")

    def _add_patrol(self, directive: str, args: str) -> None:
        """Lit une ligne `@patrol x,y -> x1,y1 ...` et vérifie qu'elle a un sens."""
        try:
            owner_text, route_text = args.split("->")
            owner = _parse_tile(owner_text)
            route = [_parse_tile(word) for word in route_text.split()]
        except ValueError:
            raise ValueError(f"Itinéraire illisible : {directive!r} (attendu '@patrol x,y -> x1,y1 ...')") from None
        if not any(s.kind == "guard" and (s.tx, s.ty) == owner for s in self.spawns):
            raise ValueError(f"Itinéraire {directive!r} : aucun garde 'G' en {owner}")
        if owner in self.patrols:
            raise ValueError(f"Deux itinéraires pour le garde en {owner}")
        for tile in route:
            if self.is_solid(*tile):
                raise ValueError(f"Itinéraire {directive!r} : la tuile {tile} n'est pas libre")
        self.patrols[owner] = route

    @classmethod
    def from_file(cls, path: str | Path, tile_size: int = TILE_SIZE) -> Tilemap:
        return cls.from_text(Path(path).read_text(encoding="utf-8"), tile_size)

    # --- Requêtes ------------------------------------------------------------
    @property
    def pixel_width(self) -> int:
        return self.width * self.tile_size

    @property
    def pixel_height(self) -> int:
        return self.height * self.tile_size

    def in_bounds(self, tx: int, ty: int) -> bool:
        return 0 <= tx < self.width and 0 <= ty < self.height

    def tile_at(self, tx: int, ty: int) -> int:
        return self.tiles[ty][tx] if self.in_bounds(tx, ty) else VOID

    def is_opaque(self, tx: int, ty: int) -> bool:
        """Vrai si la tuile arrête la vue, la lumière et le bruit (le champ de force, les barreaux et les portes de cellule
        sont solides mais pas opaques : on voit à travers)."""
        tile = self.tile_at(tx, ty)
        return tile in OPAQUE_TILES and not (tile == DOOR and (tx, ty) in self.cell_doors)

    def blocks_light(self, tx: int, ty: int) -> bool:
        """Vrai si la tuile projette une ombre : tout ce qui est opaque, sauf les vaisseaux (la lumière les survole,
        leur ombre est dessinée avec le sprite, de la forme de la coque et non d'un rectangle)."""
        return self.is_opaque(tx, ty) and self.tile_at(tx, ty) != SHIP

    def is_solid(self, tx: int, ty: int) -> bool:
        """Hors de la carte = solide : impossible de sortir du monde. Un champ commutable ne l'est que s'il est actif."""
        tile = self.tile_at(tx, ty)
        if tile in SOLID_TILES:
            return True
        return tile == GATE and self._gate_field[(tx, ty)].active

    def world_to_tile(self, x: float, y: float) -> tuple[int, int]:
        return math.floor(x / self.tile_size), math.floor(y / self.tile_size)

    # --- Champs de force commutables -----------------------------------------
    def field_at(self, tx: int, ty: int) -> Field | None:
        return self._gate_field.get((tx, ty))

    def toggle_field(self, field_id: str, occupants=None) -> Field:
        """Inverse l'état voulu d'un champ. Éteindre est immédiat ; allumer attend que sa zone soit libre.

        Un champ qui doit s'activer reste « en attente » (`pending`) tant que `update_fields` ne l'a pas terminé :
        c'est lui qui connaît les entités à ne pas écraser. Si l'on fournit déjà leurs boîtes (x, y, largeur,
        hauteur) en `occupants`, l'activation est tentée tout de suite.
        """
        f = self.fields[field_id]
        f.target = not f.target
        if not f.target:
            f.active = False
            self.invalidate_regions()
        elif occupants is not None:
            self.update_fields(occupants)
        return f

    def update_fields(self, occupants=()) -> list[Field]:
        """Active les champs en attente dont la zone est libre. Renvoie ceux qui viennent de le devenir."""
        boxes = list(occupants)
        settled = [f for f in self.fields.values() if f.pending and not any(box_overlaps_tiles(box, f.tiles, self.tile_size) for box in boxes)]
        for f in settled:
            f.active = True
        if settled:
            self.invalidate_regions()  # les chemins et zones connexes changent
        return settled

    # --- Portes --------------------------------------------------------------
    def door_level(self, tx: int, ty: int) -> int:
        return self.door_levels.get((tx, ty), 0)

    def _connected_doors(self, tile: tuple[int, int]) -> list[tuple[int, int]]:
        """Tuiles de porte contiguës à `tile` (une porte double compte pour une seule porte)."""
        found, todo = [], [tile]
        seen = {tile}
        while todo:
            x, y = todo.pop()
            found.append((x, y))
            for neighbor in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if neighbor not in seen and self.tile_at(*neighbor) == DOOR:
                    seen.add(neighbor)
                    todo.append(neighbor)
        return found

    def door_groups(self) -> list[tuple[list[tuple[int, int]], int]]:
        """Portes encore fermées, sous la forme (tuiles, niveau requis)."""
        groups, seen = [], set()
        for y in range(self.height):
            for x in range(self.width):
                if self.tiles[y][x] != DOOR or (x, y) in seen:
                    continue
                tiles = [t for t in self._connected_doors((x, y)) if self.door_level(*t) == self.door_level(x, y) and (t in self.uniform_doors) == ((x, y) in self.uniform_doors)]
                seen.update(tiles)
                groups.append((sorted(tiles), self.door_level(x, y)))
        return groups

    def open_door(self, tiles: list[tuple[int, int]]) -> None:
        """Ouvre les tuiles d'une porte : elles deviennent praticables (l'IA le saura, zones recalculées)."""
        for tx, ty in tiles:
            if self.tile_at(tx, ty) != DOOR:
                raise ValueError(f"La tuile ({tx}, {ty}) n'est pas une porte fermée")
            self.tiles[ty][tx] = OPEN_DOOR
        self.revision += 1
        self.invalidate_regions()

    # --- Zones connexes ------------------------------------------------------
    def region_of(self, tx: int, ty: int) -> int:
        """Numéro de la zone connexe de la tuile (0 pour une tuile solide ou hors carte).

        Deux tuiles de zones différentes sont inatteignables l'une depuis l'autre : l'IA s'en sert
        pour renoncer tout de suite à un chemin impossible. Si une tuile change (porte ouverte),
        appeler `invalidate_regions()`.
        """
        if self.is_solid(tx, ty):
            return 0
        if self._regions is None:
            self._regions = self._label_regions()
        return self._regions[ty][tx]

    def region_size(self, tx: int, ty: int) -> int:
        """Nombre de tuiles praticables de la zone connexe de (tx, ty) : 0 pour une tuile solide ou hors carte. Sert à la réverbération."""
        region = self.region_of(tx, ty)
        if region == 0:
            return 0
        if self._region_sizes is None:
            counts: dict[int, int] = {}
            for row in self._regions:
                for label in row:
                    if label:
                        counts[label] = counts.get(label, 0) + 1
            self._region_sizes = counts
        return self._region_sizes[region]

    def same_region(self, a: tuple[int, int], b: tuple[int, int]) -> bool:
        region = self.region_of(*a)
        return region != 0 and region == self.region_of(*b)

    def invalidate_regions(self) -> None:
        self._regions = None
        self._region_sizes = None

    def _label_regions(self) -> list[list[int]]:
        labels = [[0] * self.width for _ in range(self.height)]
        count = 0
        for y in range(self.height):
            for x in range(self.width):
                if labels[y][x] or self.is_solid(x, y):
                    continue
                count += 1
                labels[y][x] = count
                todo = deque([(x, y)])
                while todo:
                    cx, cy = todo.popleft()
                    for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                        if self.is_solid(nx, ny) or labels[ny][nx]:
                            continue
                        labels[ny][nx] = count
                        todo.append((nx, ny))
        return labels

    def spawns_of(self, kind: str) -> list[Spawn]:
        return [s for s in self.spawns if s.kind == kind]

    def route_for(self, spawn: Spawn) -> list[tuple[int, int]]:
        """Tuiles que parcourt un garde en boucle : son poste, puis son itinéraire (vide = sentinelle)."""
        return [(spawn.tx, spawn.ty), *self.patrols.get((spawn.tx, spawn.ty), [])]

    # --- Rendu ---------------------------------------------------------------
    def draw(self, surface: pygame.Surface, camera, time: float = 0.0) -> None:
        """Dessine uniquement ce qui est visible à l'écran : tuiles, puis caisses, vaisseaux et champs de force.

        `time` (secondes) anime le champ de force. Les portes fermées sont dessinées par leur entité `Door`
        (qui les anime) : ici, seul le sol dessous. Le vide n'est pas dessiné : l'espace est derrière.
        """
        ts = self.tile_size
        view = camera.visible_rect
        ox, oy = camera.offset
        tx0, tx1 = max(0, view.left // ts), min(self.width, view.right // ts + 1)
        ty0, ty1 = max(0, view.top // ts), min(self.height, view.bottom // ts + 1)

        for ty in range(ty0, ty1):
            for tx in range(tx0, tx1):
                tile = self.tiles[ty][tx]
                if tile == VOID:
                    continue
                rect = pygame.Rect(tx * ts - ox, ty * ts - oy, ts, ts)
                if tile == WALL:
                    surface.blit(tile_art.wall_tile(self.theme, ts, tx, ty), rect)
                elif tile == BARS:
                    surface.blit(tile_art.floor_tile(self.theme, ts, tx, ty), rect)
                    surface.blit(tile_art.bars_tile(ts, self._bars_run_is_horizontal(tx, ty)), rect)
                else:
                    surface.blit(tile_art.floor_tile(self.theme, ts, tx, ty), rect)
                    if tile == OPEN_DOOR:
                        self._draw_open_door(surface, rect, self._wall_sides(tx, ty))

        for prop in self.props:
            screen = pygame.Rect(prop.x * ts - ox, prop.y * ts - oy, prop.w * ts, prop.h * ts)
            if screen.colliderect(surface.get_rect()):
                if self.ship_hold is None:
                    prop_art.draw_prop(surface, prop, screen, ts, time)
                else:
                    prop_art.draw_prop(surface, prop, screen, ts, time, hold=self.ship_hold, target=prop is self.target_ship())
        for f in self.fields.values():
            state = "pending" if f.pending else "active" if f.active else "inactive"
            for x, y, w, h in f.runs:
                screen = pygame.Rect(x * ts - ox, y * ts - oy, w * ts, h * ts)
                if screen.colliderect(surface.get_rect()):
                    prop_art.draw_gate(surface, screen, self._run_is_vertical(x, y, w, h), COLORS[f"link_{f.color}"], state, time)

    def draw_decor(self, surface: pygame.Surface, camera, time: float = 0.0) -> None:
        """Lanternes sur les murs et grilles de vapeur au sol : animées, visibles seulement."""
        ts = self.tile_size
        view = camera.visible_rect.inflate(ts, ts)
        ox, oy = camera.offset
        colors = self.theme.decor_colors or ((200, 200, 200),)
        for d in self.decor:
            cx, cy = d.center(ts)
            if view.collidepoint(cx, cy):
                rect = pygame.Rect(d.tile[0] * ts - ox, d.tile[1] * ts - oy, ts, ts)
                decor_art.draw_decor(surface, d, rect, colors[d.color_index % len(colors)], time)
        for vent in self.vents:
            cx, cy = vent.center(ts)
            if view.collidepoint(cx, cy):
                rect = pygame.Rect(vent.tile[0] * ts - ox, vent.tile[1] * ts - oy, ts, ts)
                decor_art.draw_vent(surface, rect, vent.direction)

    def decor_lights(self, camera, time: float = 0.0, around=None):
        """(position, rayon, couleur, intensité) des lanternes qui éclairent leurs abords : celles de la zone visible
        (`camera`) ou, sans caméra, celles qui sont à portée de `around` (pour calculer l'éclairement en un point)."""
        from game.settings import SPOT_LIGHTS

        ts = self.tile_size
        view = camera.visible_rect.inflate(2 * ts, 2 * ts) if camera is not None else None
        colors = self.theme.decor_colors or ((200, 200, 200),)
        radius, base = SPOT_LIGHTS["lantern"]
        origin = pygame.Vector2(around) if around is not None else None
        lights = []
        for d in self.decor:
            cx, cy = d.center(ts)
            if view is not None and not view.collidepoint(cx, cy):
                continue
            pos = (cx + d.face[0] * ts * 0.6, cy + d.face[1] * ts * 0.6)  # vers le passage, pas dans le mur
            if origin is not None and origin.distance_to(pos) >= radius:
                continue
            lights.append((pos, radius, colors[d.color_index % len(colors)], base * decor_art.lantern_flicker(d.phase, time)))
        return lights

    def _bars_run_is_horizontal(self, tx: int, ty: int) -> bool:
        """Les barreaux d'une cellule forment une ligne : horizontale si un voisin de gauche ou de droite en fait partie."""
        solid_side = lambda x, y: self.tile_at(x, y) in (BARS, WALL, DOOR, OPEN_DOOR)  # noqa: E731
        return solid_side(tx - 1, ty) or solid_side(tx + 1, ty)

    def _run_is_vertical(self, x: int, y: int, w: int, h: int) -> bool:
        """Sens d'une ligne de champ. Une tuile seule se barre entre les deux murs qui l'encadrent."""
        if w != h:
            return h > w
        sideways = self.tile_at(x - 1, y) == WALL and self.tile_at(x + 1, y) == WALL
        return not sideways and self.tile_at(x, y - 1) == WALL and self.tile_at(x, y + 1) == WALL

    def _wall_sides(self, tx: int, ty: int) -> tuple[bool, bool, bool, bool]:
        """(gauche, droite, haut, bas) : vrai si un mur touche la tuile de ce côté."""
        return tuple(self.tile_at(tx + dx, ty + dy) == WALL for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)))

    @staticmethod
    def _draw_open_door(surface: pygame.Surface, rect: pygame.Rect, walls: tuple[bool, bool, bool, bool]) -> None:
        """Porte ouverte : sol, avec les vantaux rentrés dans les murs qui bordent le passage."""
        slot, thick = COLORS["door_open"], 4
        left, right, top, bottom = walls
        if left:
            pygame.draw.rect(surface, slot, (rect.x, rect.y, thick, rect.h))
        if right:
            pygame.draw.rect(surface, slot, (rect.right - thick, rect.y, thick, rect.h))
        if top:
            pygame.draw.rect(surface, slot, (rect.x, rect.y, rect.w, thick))
        if bottom:
            pygame.draw.rect(surface, slot, (rect.x, rect.bottom - thick, rect.w, thick))
