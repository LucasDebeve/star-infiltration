"""Le niveau d'entraînement doit rester simple : une découverte par salle, de gauche à droite, un seul garde."""
import pygame
import pytest

from game.ai.guard import Guard
from game.ai.perception import can_see
from game.core.game import Game
from game.core.input import InputState
from game.items import ItemKind
from game.scenes import play_scene
from game.settings import GUARD_FOV, GUARD_VISION_RANGE, HACK_TIME, PLAYER_SPEED
from game.world.level_check import check_level, explore, route_distances
from game.world.props import BOX_KIND
from game.world.tilemap import Tilemap
from tests.paths import CAMPAIGN
from tests.runner import Runner

PATH = CAMPAIGN.get("training").map_path
ROOM_WIDTH, ROOM_STEP = 9, 10  # cinq salles de 9 tuiles, séparées par des murs d'une tuile


@pytest.fixture(scope="module")
def training():
    return Tilemap.from_file(PATH)


def room_of(spawn):
    return (spawn.tx - 1) // ROOM_STEP + 1


def rooms(training, kind):
    return sorted(room_of(s) for s in training.spawns_of(kind))


def test_the_menu_points_to_this_level():
    assert PATH.name == "training.txt" and PATH.exists()
    assert CAMPAIGN.get("training").title == "Entraînement"


def test_it_is_a_small_valid_map(training):
    assert (training.width, training.height) == (51, 12)
    assert check_level(training) == []
    assert training.warnings == []


def test_it_has_exactly_one_of_each_thing_to_discover(training):
    count = lambda kind: len(training.spawns_of(kind))  # noqa: E731
    assert count("player") == count("exit") == count("terminal") == count("keycard") == count("decoy") == 1
    assert count("guard") == 1  # un seul garde : pas de coursive à surveiller
    assert count("reinforcement") == 0  # pas de renforts pour apprendre
    assert len(training.buttons) == 1 and len(training.fields) == 1
    assert sorted(level for _, level in training.door_groups()) == [0, 1]  # une porte libre, une porte à badge


def test_each_room_teaches_one_thing_in_a_logical_order(training):
    assert rooms(training, "player") == [1] and rooms(training, "decoy") == [1]  # 1 : bouger, ramasser
    assert rooms(training, "keycard") == [2]  # 2 : un badge
    assert [room_of(type("S", (), {"tx": b.tile[0]})) for b in training.buttons.values()] == [3]  # 3 : un bouton
    assert rooms(training, "guard") == [4]  # 4 : un garde
    assert rooms(training, "terminal") == [5] and rooms(training, "exit") == [5]  # 5 : le terminal, la sortie


def test_nothing_is_needed_before_it_can_be_found(training):
    """La porte à badge (fin de la salle 2) suit le badge (salle 2) ; le champ (fin de la salle 3) suit le bouton (salle 3)."""
    locked = next(tiles for tiles, level in training.door_groups() if level == 1)
    assert min(x for x, _ in locked) > training.spawns_of("keycard")[0].tx
    gate = training.fields["a"]
    assert min(x for x, _ in gate.tiles) > training.buttons["1"].tile[0]
    assert gate.active  # fermé au départ : c'est ce que le bouton apprend à ouvrir
    free_door = next(tiles for tiles, level in training.door_groups() if level == 0)
    assert min(x for x, _ in free_door) < training.spawns_of("keycard")[0].tx  # la porte libre vient avant


def test_it_uses_no_advanced_decor(training):
    assert {p.kind for p in training.props} == {BOX_KIND}  # des caisses seulement : ni vaisseau, ni champ de baie
    assert not training.has_void


def test_the_guard_has_a_simple_vertical_patrol_in_its_own_room(training):
    guard = training.spawns_of("guard")[0]
    route = training.route_for(guard)
    assert len(route) == 2 and route[0][0] == route[1][0]  # un simple aller-retour vertical
    assert {room_of(type("S", (), {"tx": x})) for x, _ in route} == {4}


def test_the_guard_patrol_crosses_the_path_and_the_room_has_cover(training):
    """Sa ronde coupe le passage (il faut agir : se cacher ou le leurrer), et la salle a des caisses pour s'abriter."""
    guard = training.spawns_of("guard")[0]
    route_ys = [y for _, y in training.route_for(guard)]
    assert min(route_ys) <= 5 and max(route_ys) >= 6  # sa ronde traverse la ligne de passage (rangées 5 et 6)
    crates = [p for p in training.props if p.kind == BOX_KIND and 31 <= p.x <= 39]
    assert len(crates) >= 2


def test_the_start_is_calm(training):
    start = training.spawns_of("player")[0].center(training.tile_size)
    guard = Guard.from_spawn(training, training.spawns_of("guard")[0])
    assert not can_see(training, guard.pos, guard.angle, GUARD_FOV, GUARD_VISION_RANGE, start)
    assert guard.pos.distance_to(start) > 20 * training.tile_size


def test_it_is_short(training):
    d = route_distances(training)
    assert d["to_goal"] / PLAYER_SPEED["walk"] + HACK_TIME < 40  # moins d'une minute à pas tranquilles
    assert d["escape"] / PLAYER_SPEED["walk"] < 15


def test_the_button_is_required(training):
    """Sans le bouton, le terminal est inaccessible : la salle 3 enseigne vraiment quelque chose."""
    exploration = explore(training)
    assert exploration.can_finish and exploration.states >= 2
    blocked = Tilemap.from_file(PATH)
    blocked.fields["a"].target = blocked.fields["a"].active = True
    blocked.buttons.clear()  # pas de bouton : le champ ne s'ouvre jamais
    problems = check_level(blocked)
    assert any("terminal inaccessible" in p for p in problems)


@pytest.fixture
def game():
    g = Game()
    pygame.event.clear()
    yield g
    pygame.quit()


def test_a_player_can_do_the_whole_tutorial(game, monkeypatch):
    """Dans l'ordre : leurre, porte libre, badge, porte à badge, bouton, champ, terminal, sortie."""
    scene = play_scene.PlayScene(game, PATH)
    game.scenes.push(scene)
    scene.guards.clear()
    runner = Runner(game, scene, monkeypatch)
    tm = scene.tilemap

    decoy = tm.spawns_of("decoy")[0]
    runner.go((decoy.tx, decoy.ty))
    assert scene.inventory.count_kind(ItemKind.DECOY) == 1
    card = tm.spawns_of("keycard")[0]
    runner.go((card.tx, card.ty))  # ouvre la porte libre en chemin
    assert scene.inventory.has_keycard(1)
    assert tm.fields["a"].active
    runner.press("1")  # le bouton de la salle 3 (après la porte à badge)
    assert not tm.fields["a"].active
    exit_ = tm.spawns_of("exit")[0]
    runner.use_terminal()
    assert scene.inventory.count_kind(ItemKind.DATA) == 1
    runner.go((exit_.tx, exit_.ty))
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_e))
    runner.frames(2)
    assert scene.won


def test_a_full_frame_in_every_room(game, monkeypatch):
    scene = play_scene.PlayScene(game, PATH)
    game.scenes.push(scene)
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState())
    for room in range(5):
        scene.player.pos.update((1 + room * 10 + 4.5) * 32, 5.5 * 32)
        scene.camera.snap_to(scene.player.pos)
        for _ in range(3):
            game.step(1 / 60)
