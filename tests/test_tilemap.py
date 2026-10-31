import pytest

from game.world.tilemap import DOOR, FLOOR, GATE, OPEN_DOOR, WALL, Tilemap
from tests.paths import SANDBOX

SMALL = """\
; commentaire ignoré
#####
#P.D#
#G.K#
#####
"""


def test_parse_tiles_and_spawns():
    tm = Tilemap.from_text(SMALL)
    assert (tm.width, tm.height) == (5, 4)
    assert tm.tile_at(0, 0) == WALL
    assert tm.tile_at(1, 1) == FLOOR  # 'P' est du sol
    assert tm.tile_at(3, 1) == DOOR
    assert {s.kind for s in tm.spawns} == {"player", "guard", "keycard"}
    assert tm.spawns_of("player")[0].tx == 1


def test_solidity_and_bounds():
    tm = Tilemap.from_text(SMALL)
    assert tm.is_solid(0, 0)
    assert tm.is_solid(3, 1)  # porte fermée
    assert not tm.is_solid(2, 1)
    assert tm.is_solid(-1, 0) and tm.is_solid(0, 99)  # hors carte


def test_world_to_tile_handles_negatives():
    tm = Tilemap.from_text(SMALL)
    assert tm.world_to_tile(40, 70) == (1, 2)
    assert tm.world_to_tile(-1, -1) == (-1, -1)


def test_spawn_center():
    tm = Tilemap.from_text(SMALL)
    center = tm.spawns_of("player")[0].center(tm.tile_size)
    assert (center.x, center.y) == (48, 48)


def test_ragged_map_rejected():
    with pytest.raises(ValueError, match="Ligne 2"):
        Tilemap.from_text("###\n##\n###")


def test_unknown_char_rejected():
    with pytest.raises(ValueError, match="inconnu"):
        Tilemap.from_text("#?#")


def test_empty_map_rejected():
    with pytest.raises(ValueError):
        Tilemap.from_text("; rien\n")


def test_sandbox_is_valid_and_connected():
    tm = Tilemap.from_file(SANDBOX)
    assert len(tm.spawns_of("player")) == 1
    assert tm.spawns_of("guard") and tm.spawns_of("exit")

    # Bords de la carte entièrement fermés.
    for x in range(tm.width):
        assert tm.tile_at(x, 0) == WALL and tm.tile_at(x, tm.height - 1) == WALL
    for y in range(tm.height):
        assert tm.tile_at(0, y) == WALL and tm.tile_at(tm.width - 1, y) == WALL

    # Toutes les tuiles libres sont atteignables depuis le départ (portes et champs commutables compris : on suppose
    # que les boutons sont actionnés ; la faisabilité réelle est vérifiée par `check_level`).
    start = tm.spawns_of("player")[0]
    seen, todo = set(), [(start.tx, start.ty)]
    while todo:
        tx, ty = todo.pop()
        if (tx, ty) in seen or tm.tile_at(tx, ty) not in (FLOOR, DOOR, GATE):
            continue
        seen.add((tx, ty))
        todo += [(tx + 1, ty), (tx - 1, ty), (tx, ty + 1), (tx, ty - 1)]
    walkable = {
        (x, y)
        for y in range(tm.height)
        for x in range(tm.width)
        if tm.tile_at(x, y) in (FLOOR, DOOR, GATE)
    }
    assert seen == walkable
    for spawn in tm.spawns:
        assert (spawn.tx, spawn.ty) in seen


PATROL_MAP = """\
#######
#G...K#
#.###.#
#.....#
#######
@patrol 1,1 -> 5,1 1,3
"""


def test_patrol_directive_builds_route():
    tm = Tilemap.from_text(PATROL_MAP)
    guard = tm.spawns_of("guard")[0]
    assert tm.height == 5  # la directive ne fait pas partie de la grille
    assert tm.route_for(guard) == [(1, 1), (5, 1), (1, 3)]


def test_guard_without_patrol_is_a_sentry():
    tm = Tilemap.from_text("#####\n#G..#\n#####")
    assert tm.route_for(tm.spawns_of("guard")[0]) == [(1, 1)]


@pytest.mark.parametrize(
    "directive, message",
    [
        ("@patrol 2,1 -> 5,1", "aucun garde"),  # (2, 1) n'est pas un 'G'
        ("@patrol 1,1 -> 2,2", "pas libre"),  # mur
        ("@patrol 1,1 -> 99,99", "pas libre"),  # hors carte
        ("@patrol 1,1 5,1", "illisible"),  # flèche manquante
        ("@patrol 1,x -> 5,1", "illisible"),
        ("@patrol 1,1 -> 5,1\n@patrol 1,1 -> 1,3", "Deux itinéraires"),
    ],
)
def test_bad_patrol_rejected(directive, message):
    grid = PATROL_MAP.split("@patrol")[0]
    with pytest.raises(ValueError, match=message):
        Tilemap.from_text(grid + directive)


def test_sandbox_patrols_are_reachable():
    """Chaque étape de chaque itinéraire de la carte de test doit être praticable par A*."""
    from game.ai.pathfinding import find_path

    tm = Tilemap.from_file(SANDBOX)
    guards = tm.spawns_of("guard")
    assert guards
    for spawn in guards:
        route = tm.route_for(spawn)
        for a, b in zip(route, route[1:] + route[:1]):
            assert find_path(tm, a, b), f"garde {route[0]} : pas de chemin {a} -> {b}"


def test_regions_separate_sealed_areas():
    tm = Tilemap.from_text("#######\n#..#..#\n#..#..#\n#######")
    assert tm.same_region((1, 1), (2, 2))
    assert not tm.same_region((1, 1), (4, 1))
    assert tm.region_of(0, 0) == 0 and tm.region_of(99, 99) == 0  # mur / hors carte
    assert not tm.same_region((0, 0), (0, 0))  # une tuile solide n'est dans aucune zone


def test_regions_follow_changes_after_invalidation():
    tm = Tilemap.from_text("#######\n#..D..#\n#######")
    assert not tm.same_region((1, 1), (5, 1))  # porte fermée = solide
    tm.tiles[1][3] = FLOOR  # la porte s'ouvre
    assert not tm.same_region((1, 1), (5, 1))  # le cache est encore périmé...
    tm.invalidate_regions()
    assert tm.same_region((1, 1), (5, 1))


DOORS = """\
#########
#.K.#...#
#...D.T.#
#.L.D...#
#########
@door 4,2 -> 2
@keycard 2,1 -> 3
"""


def test_door_directive_sets_the_level_of_the_whole_door():
    tm = Tilemap.from_text(DOORS)
    assert tm.door_level(4, 2) == tm.door_level(4, 3) == 2  # porte double : un seul niveau
    assert tm.door_groups() == [([(4, 2), (4, 3)], 2)]


def test_doors_are_free_by_default():
    tm = Tilemap.from_text("#####\n#.D.#\n#####")
    assert tm.door_level(2, 1) == 0


def test_keycard_directive_and_defaults():
    tm = Tilemap.from_text(DOORS)
    assert tm.spawns_of("keycard")[0].level == 3
    plain = Tilemap.from_text("####\n#K.#\n####")
    assert plain.spawns_of("keycard")[0].level == 1
    assert tm.spawns_of("decoy")[0].kind == "decoy"


@pytest.mark.parametrize(
    "directive, message",
    [
        ("@door 1,1 -> 1", "pas de porte"),  # c'est du sol
        ("@door 4,2 -> 9", "hors de"),
        ("@door 4,2 -> -1", "hors de"),
        ("@door 4,2", "illisible"),
        ("@keycard 1,1 -> 1", "pas de badge"),
        ("@keycard 2,1 -> x", "illisible"),
        ("@mystere 1,1", "inconnue"),
    ],
)
def test_bad_door_and_keycard_directives(directive, message):
    grid = DOORS.split("@door")[0]
    with pytest.raises(ValueError, match=message):
        Tilemap.from_text(grid + directive)


def test_opening_a_door_makes_it_walkable_and_updates_regions():
    tm = Tilemap.from_text(DOORS)
    assert not tm.same_region((1, 1), (6, 1))
    tm.open_door([(4, 2), (4, 3)])
    assert tm.tile_at(4, 2) == OPEN_DOOR and not tm.is_solid(4, 2)
    assert tm.same_region((1, 1), (6, 1))  # le cache de zones a été invalidé
    assert tm.door_groups() == []


def test_cannot_open_something_that_is_not_a_closed_door():
    tm = Tilemap.from_text(DOORS)
    with pytest.raises(ValueError):
        tm.open_door([(1, 1)])
    tm.open_door([(4, 2), (4, 3)])
    with pytest.raises(ValueError):  # déjà ouverte
        tm.open_door([(4, 2)])


def test_level_door_and_keycard_data_is_consistent():
    from game.settings import MAX_BADGE_LEVEL

    tm = Tilemap.from_file(SANDBOX)
    assert tm.door_groups()
    assert all(0 <= level <= MAX_BADGE_LEVEL for _, level in tm.door_groups())
    assert all(s.level >= 1 for s in tm.spawns_of("keycard"))


def test_sandbox_is_completable():
    """Le niveau se termine : à chaque étape on atteint un badge assez fort pour la porte suivante,
    puis le terminal, puis on revient à la sortie."""
    tm = Tilemap.from_file(SANDBOX)
    groups = tm.door_groups()
    start = tm.spawns_of("player")[0]
    level = 0
    while True:
        # Zones atteignables : on franchit les portes déjà ouvertes ou accessibles avec le niveau de badge actuel.
        reach = {tm.region_of(start.tx, start.ty)}
        changed = True
        while changed:
            changed = False
            for i, (tiles, need) in enumerate(groups):
                if need > level:
                    continue
                around = {tm.region_of(x + dx, y + dy) for x, y in tiles for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))} - {0}
                if around & reach and not around <= reach:
                    reach |= around
                    changed = True
        best = max([level] + [s.level for s in tm.spawns_of("keycard") if tm.region_of(s.tx, s.ty) in reach])
        if best == level:
            break
        level = best

    terminal, exit_ = tm.spawns_of("terminal")[0], tm.spawns_of("exit")[0]
    assert tm.region_of(terminal.tx, terminal.ty) in reach, "le terminal est inaccessible"
    assert tm.region_of(exit_.tx, exit_.ty) in reach, "la sortie est inaccessible"
    # Et chaque porte verrouillée est utile : le badge qui l'ouvre se trouve avant elle.
    assert level >= max(need for _, need in groups)


def test_reinforcement_spawns_in_the_sandbox():
    tm = Tilemap.from_file(SANDBOX)
    spawns = tm.spawns_of("reinforcement")
    assert len(spawns) >= 2
    hub = tm.region_of(30, 10)
    assert any(tm.region_of(s.tx, s.ty) == hub for s in spawns)  # au moins un point sur l'axe principal
    assert all(not tm.is_solid(s.tx, s.ty) for s in spawns)
