import pygame
import pytest

from game.ai.perception import can_see
from game.core.game import Game
from game.core.input import InputState
from game.difficulty import all_difficulties
from game.scenes import play_scene
from game.settings import (
    GUARD_FOV,
    GUARD_VISION_RANGE,
    HACK_TIME,
    PLAYER_SPEED,
)
from game.world.level_check import check_level, explore, route_distances
from game.world.lights import place_ceiling_lamps
from game.world.tilemap import Tilemap
from tests.paths import CAMPAIGN, CRUISER
from tests.runner import Runner


@pytest.fixture(scope="module")
def cruiser():
    return Tilemap.from_file(CRUISER)


def open_all_fields(tilemap):
    """Suppose tous les boutons déjà actionnés : aucun champ commutable ne barre plus le passage."""
    for f in tilemap.fields.values():
        f.target = f.active = False
    tilemap.invalidate_regions()


# --- Toutes les cartes livrées ------------------------------------------------
@pytest.mark.parametrize("mission", CAMPAIGN.missions, ids=lambda m: m.id)
def test_every_shipped_level_is_playable(mission):
    assert mission.map_path.exists()
    assert check_level(Tilemap.from_file(mission.map_path)) == []


@pytest.mark.parametrize("mission", CAMPAIGN.missions, ids=lambda m: m.id)
def test_every_level_has_closed_borders(mission):
    tm = Tilemap.from_file(mission.map_path)
    for x in range(tm.width):
        assert tm.is_solid(x, 0) and tm.is_solid(x, tm.height - 1)
    for y in range(tm.height):
        assert tm.is_solid(0, y) and tm.is_solid(tm.width - 1, y)


# --- check_level détecte les vrais problèmes -----------------------------------
def test_check_level_flags_missing_points():
    assert any("terminal" in p for p in check_level(Tilemap.from_text("####\n#P.#\n####")))


def test_check_level_flags_an_unreachable_terminal():
    problems = check_level(Tilemap.from_text("########\n#P.#TE.#\n########"))
    assert any("terminal inaccessible" in p for p in problems)
    assert any("exit inaccessible" in p for p in problems)


def test_check_level_flags_a_door_that_can_never_open():
    # Le seul badge est de niveau 1, mais la porte en demande 2.
    problems = check_level(Tilemap.from_text("###########\n#PK.D.T.E.#\n###########\n@door 4,1 -> 2\n"))
    assert any("niveau 2" in p for p in problems)


def test_check_level_accepts_a_solvable_chain():
    text = "############\n#PKD.K.D.TE#\n############\n@door 3,1 -> 1\n@door 7,1 -> 2\n@keycard 5,1 -> 2\n"
    assert check_level(Tilemap.from_text(text)) == []


def test_check_level_flags_unreachable_patrols():
    text = "########\n#PGD.TE#\n########\n@patrol 2,1 -> 4,1\n"
    assert any("garde" in p for p in check_level(Tilemap.from_text(text)))


def test_check_level_does_not_modify_the_map(cruiser):
    before = [row[:] for row in cruiser.tiles]
    route_distances(cruiser)
    assert cruiser.tiles == before and cruiser.door_groups()


def test_progress_collects_badges_in_order(cruiser):
    exploration = explore(cruiser)
    assert exploration.level == 3 and exploration.can_finish
    terminal, exit_ = cruiser.spawns_of("terminal")[0], cruiser.spawns_of("exit")[0]
    assert (terminal.tx, terminal.ty) in exploration.tiles and (exit_.tx, exit_.ty) in exploration.tiles


# --- Le croiseur --------------------------------------------------------------
def test_cruiser_dimensions_and_contents(cruiser):
    assert (cruiser.width, cruiser.height) == (72, 48)
    kinds = [s.kind for s in cruiser.spawns]
    assert kinds.count("player") == 1 and kinds.count("terminal") == 2 and kinds.count("exit") == 1  # plans + terminal de la caserne
    assert [t.can("data") for t in cruiser.terminal_specs.values()] == [True, False]
    assert 10 <= kinds.count("guard") <= 16
    assert kinds.count("decoy") >= 4
    assert kinds.count("reinforcement") >= 2


def test_the_cruiser_mixes_several_kinds_of_obstacles(cruiser):
    from game.world.props import BOX_KIND, FIELD_KIND, SHIP_KIND

    count = lambda kind: sum(p.kind == kind for p in cruiser.props)  # noqa: E731
    assert count(BOX_KIND) >= 15 and count(SHIP_KIND) == 4 and count(FIELD_KIND) == 2
    assert any(p.kind == BOX_KIND and p.w * p.h > 1 for p in cruiser.props)  # des conteneurs, pas seulement des caisses
    assert {p.w * p.h for p in cruiser.props if p.kind == SHIP_KIND} == {9, 20}  # des chasseurs et des navettes


def test_each_bay_has_ships_then_a_force_field_then_open_space(cruiser):
    """Du pont vers l'extérieur : vaisseaux, champ de force, vide."""
    from game.world.props import FIELD_KIND, SHIP_KIND
    from game.world.tilemap import VOID

    for field in (p for p in cruiser.props if p.kind == FIELD_KIND):
        assert field.h == 1 and field.w >= 10  # une baie large, dans le sens horizontal
        for tx in range(field.x, field.x + field.w):
            assert not cruiser.is_solid(tx, field.y - 1) or cruiser.tile_at(tx, field.y - 1) != VOID  # le pont est devant
            assert all(cruiser.tile_at(tx, field.y + dy) == VOID for dy in (1, 2, 3))  # l'espace est derrière
        ships = [p for p in cruiser.props if p.kind == SHIP_KIND and field.x <= p.x <= field.x + field.w and field.y - 8 < p.y < field.y]
        assert len(ships) == 2
        assert all(p.facing == "S" for p in ships)  # le nez pointe vers le champ de force


def test_the_exit_is_right_beside_the_extraction_shuttle(cruiser):
    from game.world.props import SHIP_KIND

    exit_ = cruiser.spawns_of("exit")[0]
    shuttle = next(p for p in cruiser.props if p.kind == SHIP_KIND and p.w * p.h == 20 and p.x > 40)
    assert exit_.tx == shuttle.x - 1 and shuttle.y <= exit_.ty < shuttle.y + shuttle.h


def test_the_player_cannot_leave_through_a_force_field(cruiser):
    from game.world.collision import move_and_collide

    field = next(p for p in cruiser.props if p.kind == "field")
    x, y = (field.x + 3) * 32 + 5, (field.y - 1) * 32 + 5  # juste devant le champ
    result = move_and_collide(cruiser, x, y, 22, 22, 0, 200)
    assert result.hit_y and result.y + 22 <= field.y * 32 + 1e-6


def test_no_guard_route_crosses_a_force_field_or_an_obstacle(cruiser):
    for spawn in cruiser.spawns_of("guard"):
        assert all(not cruiser.is_solid(*tile) for tile in cruiser.route_for(spawn))


def test_cruiser_has_one_badge_per_level_and_matching_doors(cruiser):
    assert sorted(s.level for s in cruiser.spawns_of("keycard")) == [1, 2, 3]
    assert {level for _, level in cruiser.door_groups()} == {0, 1, 2, 3}


def test_each_badge_is_found_before_the_door_that_needs_it(cruiser):
    """Le badge de niveau n se trouve dans une zone accessible avec les badges de niveau < n."""
    start = cruiser.spawns_of("player")[0]
    level = 0
    for wanted in (1, 2, 3):
        # Zones atteignables avec un badge de niveau `level` : on simule en n'autorisant que les portes <= level.
        reach = {cruiser.region_of(start.tx, start.ty)}
        changed = True
        while changed:
            changed = False
            for tiles, need in cruiser.door_groups():
                if need > level:
                    continue
                around = {cruiser.region_of(x + dx, y + dy) for x, y in tiles for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))} - {0}
                if around & reach and not around <= reach:
                    reach |= around
                    changed = True
        card = next(s for s in cruiser.spawns_of("keycard") if s.level == wanted)
        assert cruiser.region_of(card.tx, card.ty) in reach, f"le badge {wanted} est introuvable avec le badge {level}"
        level = wanted


def test_the_terminal_sits_behind_the_highest_door():
    cruiser = Tilemap.from_file(CRUISER)
    open_all_fields(cruiser)  # le terminal est dans une alcôve fermée par un champ : voir test_the_terminal_alcove...
    terminal = cruiser.spawns_of("terminal")[0]
    hub = cruiser.region_of(30, 22)
    assert cruiser.region_of(terminal.tx, terminal.ty) != hub
    top_door = next(tiles for tiles, level in cruiser.door_groups() if level == 3)
    around = {cruiser.region_of(x + dx, y + dy) for x, y in top_door for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))}
    assert cruiser.region_of(terminal.tx, terminal.ty) in around


def test_the_south_rooms_connect_without_using_the_main_corridor():
    """Les tunnels de service offrent une route qui évite la coursive centrale (et ses trois gardes)."""
    from game.ai.pathfinding import find_path
    from game.world.tilemap import WALL

    tm = Tilemap.from_file(CRUISER)
    open_all_fields(tm)  # les tunnels sont barrés par des champs : on suppose les boutons actionnés
    for tiles, level in tm.door_groups():
        if level == 0:
            tm.open_door(tiles)
    for x in range(tm.width):  # on bouche la coursive
        for y in (22, 23):
            tm.tiles[y][x] = WALL
    tm.invalidate_regions()
    start = tm.spawns_of("player")[0]
    first_badge = next(s for s in tm.spawns_of("keycard") if s.level == 1)
    exit_ = tm.spawns_of("exit")[0]
    assert find_path(tm, (start.tx, start.ty), (first_badge.tx, first_badge.ty))
    assert find_path(tm, (first_badge.tx, first_badge.ty), (exit_.tx, exit_.ty))


def test_no_two_things_share_a_tile(cruiser):
    tiles = [(s.tx, s.ty) for s in cruiser.spawns]
    assert len(tiles) == len(set(tiles))


# --- Équilibrage mesuré --------------------------------------------------------
def test_the_route_is_short_enough_to_beat_the_lockdown_even_on_hard(cruiser):
    d = route_distances(cruiser)
    run_time = (d["to_goal"] + d["escape"]) / PLAYER_SPEED["run"] + HACK_TIME
    for difficulty in all_difficulties():
        # Alerte dès la première seconde : à pleine course, sans embûche, il reste de la marge pour les gardes.
        assert run_time <= difficulty.lockdown_time * 0.5, difficulty.key


def test_a_calm_walk_through_the_level_takes_a_reasonable_time(cruiser):
    d = route_distances(cruiser)
    walk = d["to_goal"] / PLAYER_SPEED["walk"] + HACK_TIME
    assert 30 <= walk <= 90  # ni un couloir de 10 secondes, ni une corvée de plusieurs minutes


def test_the_escape_leg_is_short_but_not_trivial(cruiser):
    escape_run = route_distances(cruiser)["escape"] / PLAYER_SPEED["run"]
    assert 4 <= escape_run <= 15


def test_the_escape_is_survivable_when_alerted_at_the_terminal(cruiser):
    """Alerte donnée en piratant : en marchant, on rejoint la sortie en moins de 15 % du temps de verrouillage."""
    walk = route_distances(cruiser)["escape"] / PLAYER_SPEED["walk"]
    for difficulty in all_difficulties():
        assert walk <= difficulty.lockdown_time * 0.15, difficulty.key


# --- Démarrage sûr -------------------------------------------------------------
def test_no_guard_sees_the_player_at_the_start(cruiser):
    start = cruiser.spawns_of("player")[0].center(cruiser.tile_size)
    from game.ai.guard import Guard

    for spawn in cruiser.spawns_of("guard"):
        guard = Guard.from_spawn(cruiser, spawn)
        assert not can_see(cruiser, guard.pos, guard.angle, GUARD_FOV, GUARD_VISION_RANGE, start), spawn


def test_guards_start_well_away_from_the_player(cruiser):
    start = cruiser.spawns_of("player")[0].center(cruiser.tile_size)
    nearest = min(s.center(cruiser.tile_size).distance_to(start) for s in cruiser.spawns_of("guard"))
    assert nearest >= 10 * cruiser.tile_size


def test_every_guard_stays_in_its_own_zone_while_doors_are_closed(cruiser):
    for spawn in cruiser.spawns_of("guard"):
        zone = cruiser.region_of(spawn.tx, spawn.ty)
        assert all(cruiser.region_of(*tile) == zone for tile in cruiser.route_for(spawn))


def test_the_hub_has_cover_against_long_sightlines(cruiser):
    """Des piliers coupent la coursive : aucune ligne de vue ne la traverse de bout en bout."""
    from game.world.raycast import line_of_sight

    assert not line_of_sight(cruiser, pygame.Vector2(2.5 * 32, 22.5 * 32), pygame.Vector2(69.5 * 32, 22.5 * 32))
    assert not line_of_sight(cruiser, pygame.Vector2(2.5 * 32, 23.5 * 32), pygame.Vector2(69.5 * 32, 23.5 * 32))


def test_the_level_is_well_lit(cruiser):
    lamps = place_ceiling_lamps(cruiser)
    assert len(lamps) >= 30
    rooms = {cruiser.region_of(*lamp.tile) for lamp in lamps}
    assert len(rooms) >= 5  # des lampes dans plusieurs zones


# --- Parties simulées ----------------------------------------------------------
@pytest.fixture
def game():
    g = Game()
    pygame.event.clear()
    yield g
    pygame.quit()


def test_one_minute_of_idle_play_on_the_cruiser(game, monkeypatch):
    scene = play_scene.PlayScene(game, CRUISER)
    game.scenes.push(scene)
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState())
    for _ in range(60 * 60):
        scene.update(1 / 60)
    assert not scene.alert.active and not scene.over  # le joueur immobile dans le hangar est tranquille
    for guard in scene.guards:
        assert not scene.tilemap.is_solid(*scene.tilemap.world_to_tile(*guard.pos))


def test_a_full_frame_is_drawn_at_the_start_and_everywhere_on_the_cruiser(game, monkeypatch):
    scene = play_scene.PlayScene(game, CRUISER)
    game.scenes.push(scene)
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState())
    for tile in ((4, 37), (30, 23), (65, 6), (66, 36), (10, 8), (35, 36)):
        scene.player.pos.update((tile[0] + 0.5) * 32, (tile[1] + 0.5) * 32)
        scene.camera.snap_to(scene.player.pos)
        game.step(1 / 60)


def test_a_scripted_runner_completes_the_cruiser(game, monkeypatch):
    from game.items import ItemKind

    scene = play_scene.PlayScene(game, CRUISER)
    game.scenes.push(scene)
    scene.guards.clear()
    runner = Runner(game, scene, monkeypatch)
    tm = scene.tilemap

    for level in (1, 2, 3):  # les badges dans l'ordre
        card = next(s for s in tm.spawns_of("keycard") if s.level == level)
        runner.go((card.tx, card.ty))
        assert scene.inventory.has_keycard(level)

    exit_ = tm.spawns_of("exit")[0]
    assert tm.fields["c"].active  # l'alcôve du terminal est fermée au départ
    runner.press("3")  # le bouton du poste de commandement ouvre l'alcôve
    assert not tm.fields["c"].active
    runner.use_terminal()
    assert scene.inventory.count_kind(ItemKind.DATA) == 1

    runner.go((exit_.tx, exit_.ty))
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_e))
    runner.frames(2)
    assert scene.won and not scene.failed and not scene.caught


def test_the_south_route_works_through_the_tunnels_with_buttons_1_then_2(game, monkeypatch):
    """Exemple A-B-C : hangar -(a)- ingénierie -(b)- quai. Le bouton 1 ouvre a et ferme b, le bouton 2 rouvre b.
    La coursive est bouchée : seuls les tunnels et les boutons permettent d'avancer."""
    from game.world.tilemap import WALL

    scene = play_scene.PlayScene(game, CRUISER)
    game.scenes.push(scene)
    scene.guards.clear()
    tm = scene.tilemap
    for x in range(tm.width):
        for y in (22, 23):
            tm.tiles[y][x] = WALL
    tm.invalidate_regions()
    runner = Runner(game, scene, monkeypatch)
    a, b = tm.fields["a"], tm.fields["b"]
    assert (a.active, b.active) == (True, False)  # départ : AB fermé, BC ouvert

    with pytest.raises(AssertionError, match="aucun badge ne permet d'avancer|pas de chemin"):
        runner.go((43, 34))  # sans bouton, le champ a barre le tunnel

    runner.press("1")
    assert (a.active, b.active) == (False, True)  # AB s'ouvre, BC se ferme
    runner.go((43, 34))  # engineering (badge 1)
    assert scene.inventory.has_keycard(1)
    exit_ = tm.spawns_of("exit")[0]
    with pytest.raises(AssertionError):
        runner.go((exit_.tx, exit_.ty))  # le quai est maintenant fermé par b
    runner.press("2")
    assert not b.active
    runner.go((exit_.tx, exit_.ty))
    assert runner.tile == (exit_.tx, exit_.ty)
