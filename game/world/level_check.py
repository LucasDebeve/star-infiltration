"""Vérifications d'un niveau : faisabilité (badges, portes, point d'objectif, sortie) et distances à parcourir.

Logique pure, utilisée par les tests pour que toute carte (livrée ou future) reste jouable.
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass

from game.ai.pathfinding import find_path
from game.objectives import STEAL_PLANS, STEAL_SHIP, infer_objective, objective_spawns
from game.world.tilemap import DOOR, FLOOR, GATE, OPEN_DOOR

_NEIGHBORS = ((1, 0), (-1, 0), (0, 1), (0, -1))
MAX_STATES = 20000  # garde-fou : un niveau avec trop de boutons n'est pas analysé jusqu'au bout

Tile = tuple[int, int]
MAX_BOARDING_DISTANCE = 4.5  # tuiles : la zone d'extraction d'un vol de vaisseau est contre le vaisseau (passerelle)


@dataclass
class Exploration:
    """Ce qu'un joueur parfait peut atteindre (badges, portes, boutons, champs de force)."""

    tiles: set[Tile]  # tuiles atteignables, dans au moins un état des boutons
    level: int  # meilleur badge obtenu
    can_finish: bool  # le point d'objectif (terminal, console...) puis la sortie sont atteignables, dans cet ordre
    states: int  # nombre d'états explorés


def _passable(tilemap, tile: Tile, level: int, gates_active: dict[str, bool], uniform: bool = False) -> bool:
    kind = tilemap.tile_at(*tile)
    if kind in (FLOOR, OPEN_DOOR):
        return True
    if kind == DOOR:  # on peut l'ouvrir avec le badge du bon niveau
        if tile in tilemap.uniform_doors:  # porte du personnel : seul l'uniforme (porté) l'ouvre
            return uniform
        need = tilemap.door_level(*tile)
        if tile in tilemap.cell_doors:  # verrou électronique (niveau 0) : un terminal « cellules » ; sinon un badge de son niveau
            return tilemap.cells_openable or (need > 0 and level >= need)
        return level >= need
    if kind == GATE:
        return not gates_active[tilemap.field_at(*tile).id]
    return False  # mur, caisse, vaisseau, champ de baie, vide


def _flood(tilemap, start: Tile, level: int, gates_active: dict[str, bool], uniform: bool = False) -> set[Tile]:
    seen, todo = {start}, [start]
    while todo:
        x, y = todo.pop()
        for dx, dy in _NEIGHBORS:
            nxt = (x + dx, y + dy)
            if nxt not in seen and _passable(tilemap, nxt, level, gates_active, uniform):
                seen.add(nxt)
                todo.append(nxt)
    return seen


def explore(tilemap, allow_uniform: bool = True) -> Exploration:
    """Explore tous les états : badges obtenus, portes ouvertes, boutons actionnés (une pression inverse ses champs).

    Un état = (parité de pressions de chaque bouton, meilleur badge, données récupérées, uniforme dérobé, zone où se trouve le joueur).
    `allow_uniform=False` interdit de dérober l'uniforme : sert à prouver qu'une carte l'exige.
    """
    start = tilemap.spawns_of("player")[0]
    keycards = [(s.level, (s.tx, s.ty)) for s in tilemap.spawns_of("keycard")]
    goal = objective_spawns(tilemap, infer_objective(tilemap))
    exit_tile = tilemap.spawns_of("exit")
    terminal_tile = (goal[0].tx, goal[0].ty) if goal else None
    exit_tile = (exit_tile[0].tx, exit_tile[0].ty) if exit_tile else None
    uniforms = [(s.tx, s.ty) for s in tilemap.spawns_of("uniform")] if allow_uniform else []
    buttons = [tilemap.buttons[b] for b in sorted(tilemap.buttons)]

    def gates_for(parity: tuple[bool, ...]) -> dict[str, bool]:
        active = {fid: f.start_active for fid, f in tilemap.fields.items()}
        for pressed, button in zip(parity, buttons):
            if pressed:
                for fid in button.fields:
                    active[fid] = not active[fid]
        return active

    def settle(parity, level, has_data, has_uniform, position):
        """Fixe l'état : le joueur ramasse tout badge et le terminal de sa zone (ce qui peut ouvrir d'autres portes)."""
        gates = gates_for(parity)
        while True:
            reach = _flood(tilemap, position, level, gates, has_uniform)
            best = max([level] + [lv for lv, tile in keycards if tile in reach])
            took = has_uniform or any(tile in reach for tile in uniforms)  # le casier se fouille, puis l'uniforme s'enfile
            if best == level and took == has_uniform:
                break
            level, has_uniform = best, took
        has_data = has_data or (terminal_tile in reach)
        return (parity, level, has_data, has_uniform, min(reach)), reach

    first, reach0 = settle((False,) * len(buttons), 0, False, False, (start.tx, start.ty))
    seen, queue = {first}, [first]
    all_tiles, best_level, can_finish = set(reach0), first[1], False
    while queue and len(seen) <= MAX_STATES:
        state = queue.pop()
        parity, level, has_data, has_uniform, anchor = state
        reach = _flood(tilemap, anchor, level, gates_for(parity), has_uniform)
        all_tiles |= reach
        best_level = max(best_level, level)
        can_finish = can_finish or (has_data and exit_tile in reach)
        for i, button in enumerate(buttons):
            beside = [t for t in [button.tile] + [(button.tile[0] + dx, button.tile[1] + dy) for dx, dy in _NEIGHBORS] if t in reach]
            if not beside:
                continue
            flipped = parity[:i] + (not parity[i],) + parity[i + 1 :]
            nxt, _ = settle(flipped, level, has_data, has_uniform, beside[0])
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)

    return Exploration(all_tiles, best_level, can_finish, len(seen))


def check_level(tilemap) -> list[str]:
    """Liste des problèmes qui rendraient le niveau injouable (vide si tout va bien)."""
    problems = []
    objective = infer_objective(tilemap)
    for kind in ("player", "exit"):
        if not tilemap.spawns_of(kind):
            problems.append(f"pas de point '{kind}'")
    if not objective_spawns(tilemap, objective):
        problems.append(f"pas de point '{objective.tile}'" + (" qui télécharge des données" if objective.tile == "terminal" else ""))
    if objective_spawns(tilemap, STEAL_PLANS) and tilemap.spawns_of("console"):
        problems.append("la carte a un terminal de données et une console : un seul objectif par carte")
    if len(objective_spawns(tilemap, STEAL_PLANS)) > 1:
        problems.append("plusieurs terminaux de données : un seul est géré")
    if len(tilemap.spawns_of("console")) > 1:
        problems.append("plusieurs points 'console' : un seul est géré")
    if problems:
        return problems

    exploration = explore(tilemap)
    for kind, spawn in (("objectif", objective_spawns(tilemap, objective)[0]), ("exit", tilemap.spawns_of("exit")[0])):
        if (spawn.tx, spawn.ty) not in exploration.tiles:
            problems.append(f"{objective.tile if kind == 'objectif' else kind} inaccessible avec les badges de la carte")
    highest = max((need for _, need in tilemap.door_groups()), default=0)
    if exploration.level < highest:
        problems.append(f"aucun badge de niveau {highest} accessible : des portes restent verrouillées pour toujours")
    if tilemap.uniform_doors and not tilemap.spawns_of("uniform"):
        problems.append("des portes du personnel exigent un uniforme, mais la carte n'a aucun casier 'U'")
    for spawn in tilemap.spawns_of("keycard") + tilemap.spawns_of("decoy") + tilemap.spawns_of("terminal") + tilemap.spawns_of("uniform"):
        if (spawn.tx, spawn.ty) not in exploration.tiles:
            problems.append(f"objet '{spawn.kind}' inaccessible en ({spawn.tx}, {spawn.ty})")
    if objective is STEAL_SHIP:
        ships = [p for p in tilemap.props if p.kind == "ship"]
        exit_ = tilemap.spawns_of("exit")[0]
        if not ships:
            problems.append("voler un vaisseau : la carte n'a aucun vaisseau 'S'")
        elif min(math.hypot(p.x + p.w / 2 - exit_.tx - 0.5, p.y + p.h / 2 - exit_.ty - 0.5) for p in ships) > MAX_BOARDING_DISTANCE:
            problems.append("la zone d'extraction doit se trouver contre le vaisseau à voler (passerelle d'embarquement)")
    for spec in tilemap.terminal_specs.values():
        if spec.can("cells") and not tilemap.cell_doors:
            problems.append(f"terminal {spec.tile} : aucune porte de cellule 'J' à ouvrir")
        if spec.can("cameras") and not any(spec.controls(camera.group) for camera in tilemap.cameras):
            problems.append(f"terminal {spec.tile} : aucune caméra à commander")
    for spawn in tilemap.spawns_of("guard"):
        route = tilemap.route_for(spawn)
        for a, b in zip(route, route[1:] + route[:1]):
            if not find_path(tilemap, a, b):
                problems.append(f"garde {route[0]} : pas de chemin {a} -> {b}")
    return problems


def _path_length(tilemap, a: tuple[int, int], b: tuple[int, int]) -> float:
    path = find_path(tilemap, a, b)
    if not path:
        raise ValueError(f"pas de chemin {a} -> {b}")
    return sum(math.dist(p, q) for p, q in zip(path, path[1:])) * tilemap.tile_size


def route_distances(tilemap) -> dict[str, float]:
    """Distances (px) de la route la plus directe : départ -> badges (par niveau) -> point d'objectif -> sortie.

    Toutes les portes sont comptées ouvertes (on les aura ouvertes dans l'ordre). Renvoie `to_goal`
    (aller) et `escape` (de l'objectif à la sortie). Les champs commutables sont comptés ouverts : on ignore
    le détour vers les boutons, donc ce sont des minimums.
    """
    tm = copy.deepcopy(tilemap)  # on ouvre les portes sur une copie : la carte reçue n'est pas modifiée
    for tiles, _ in tm.door_groups():
        tm.open_door(tiles)
    for f in tm.fields.values():  # en supposant les boutons déjà actionnés : c'est un minimum, sans les détours
        f.target = f.active = False
    tm.invalidate_regions()
    start = tm.spawns_of("player")[0]
    here = (start.tx, start.ty)
    forward = 0.0
    for level in sorted({s.level for s in tm.spawns_of("keycard")}):
        card = min((s for s in tm.spawns_of("keycard") if s.level == level), key=lambda s: _path_length(tm, here, (s.tx, s.ty)))
        forward += _path_length(tm, here, (card.tx, card.ty))
        here = (card.tx, card.ty)
    if tilemap.uniform_doors:  # l'uniforme se dérobe avant de franchir les portes du personnel
        locker = min(tm.spawns_of("uniform"), key=lambda s: _path_length(tm, here, (s.tx, s.ty)))
        forward += _path_length(tm, here, (locker.tx, locker.ty))
        here = (locker.tx, locker.ty)
    goal, exit_ = objective_spawns(tm, infer_objective(tm))[0], tm.spawns_of("exit")[0]
    forward += _path_length(tm, here, (goal.tx, goal.ty))
    escape = _path_length(tm, (goal.tx, goal.ty), (exit_.tx, exit_.ty))
    return {"to_goal": forward, "escape": escape}


def complexity(tilemap) -> float:
    """Indice de complexité d'un niveau (sans unité) : plus il est grand, plus la carte demande de patience et de maîtrise.

    Il pèse ce qui complique vraiment une infiltration : les gardes, les portes, les champs de force et leurs boutons, les caméras,
    les terminaux utilitaires, le plus haut niveau de badge, et un peu la taille. Sert à vérifier que la campagne monte en difficulté.
    """
    utility = sum(1 for s in tilemap.spawns_of("terminal") if not tilemap.terminal_spec((s.tx, s.ty)).can("data"))
    badge = max((need for _, need in tilemap.door_groups()), default=0)
    return (
        2 * len(tilemap.spawns_of("guard"))
        + 1.5 * len(tilemap.door_groups())
        + 2 * len(tilemap.fields)
        + len(tilemap.buttons)
        + 2 * len(tilemap.cameras)
        + 1.5 * utility
        + 2 * badge
        + tilemap.width * tilemap.height / 200
    )
