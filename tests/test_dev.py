"""Mode développeur : activé seulement par `--dev`/variable d'environnement, jamais en version livrée ; jouer n'importe quel niveau."""

import pygame
import pytest

import main
from game import dev
from game.core.input import InputState
from game.dev import DEV_KEYS, DevTools, dev_requested
from game.scenes import play_scene
from game.scenes.dev_scene import DevScene
from game.scenes.main_menu import MainMenuScene
from game.settings import SCREEN_SIZE
from game.ui.backdrop import Starfield
from tests.paths import CAMPAIGN

V = pygame.Vector2


# --- Activation -----------------------------------------------------------------------------------------------------------------------
def test_dev_mode_is_off_by_default():
    assert not dev_requested(False, {})
    assert main.parse_args([]).dev is False


def test_the_flag_or_the_environment_turns_it_on():
    assert dev_requested(True, {})
    assert dev_requested(False, {dev.DEV_ENV: "1"})
    assert not dev_requested(False, {dev.DEV_ENV: "0"})
    assert main.parse_args(["--dev"]).dev is True


def test_a_packaged_build_never_has_dev_mode(monkeypatch):
    monkeypatch.setattr("sys.frozen", True, raising=False)
    assert not dev.dev_allowed() and not dev_requested(True, {dev.DEV_ENV: "1"})


def test_the_browser_build_never_has_dev_mode(monkeypatch):
    monkeypatch.setattr("sys.platform", "emscripten")
    assert not dev_requested(True, {})


def test_the_packaging_spec_does_not_ship_dev_flags():
    # Le mode développeur reste un simple booléen de l'appelant : rien n'est lu dans un exécutable.
    assert dev.DevTools().active() == []


# --- Menu ---------------------------------------------------------------------------------------------------------------------------------
def labels(scene):
    return [item.label for item in scene.menu.items]


def test_the_main_menu_has_no_dev_entry_normally(game):
    assert "Mode développeur" not in labels(MainMenuScene(game))


def test_the_main_menu_offers_dev_mode_when_enabled(game):
    game.dev = DevTools()
    scene = MainMenuScene(game)
    assert labels(scene)[-2:] == ["Mode développeur", "Quitter"]
    scene.menu.items[labels(scene).index("Mode développeur")].activate()
    assert isinstance(game.scenes.current, DevScene)


def test_the_dev_menu_lists_every_mission_even_locked_ones(game):
    game.dev = DevTools()
    scene = DevScene(game, Starfield(SCREEN_SIZE))
    names = labels(scene)
    for mission in CAMPAIGN.missions:
        assert any(mission.title in name for name in names)
    assert not game.progress.is_completed(CAMPAIGN.missions[-1].id)
    assert names[-1] == "Retour"


def test_a_level_is_launched_straight_from_the_dev_menu_without_touching_progress(game, monkeypatch):
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState())
    game.dev = DevTools()
    scene = DevScene(game, Starfield(SCREEN_SIZE))
    game.scenes.push(scene)
    last = CAMPAIGN.missions[-1]
    next(i for i in scene.menu.items if last.title in i.label).activate()
    play = game.scenes.current
    assert isinstance(play, play_scene.PlayScene) and play.mission is None
    play.won = True
    play.update(1 / 60)
    assert not game.progress.is_completed(last.id) and game.scenes.current is play  # pas d'écran de résultats ni d'enregistrement


def test_every_mission_keeps_its_objective_when_played_without_mission(game, monkeypatch):
    """Lancé du menu développeur, le niveau déduit son objectif de la carte : il doit être celui de la campagne."""
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState())
    for mission in CAMPAIGN.missions:
        scene = play_scene.PlayScene(game, mission.map_path)
        assert scene.goal.id == mission.objective, mission.id


def test_the_toggles_change_the_dev_tools(game):
    game.dev = DevTools()
    scene = DevScene(game, Starfield(SCREEN_SIZE))
    scene.menu.items[0].activate()
    scene.menu.items[1].activate()
    assert game.dev.invincible and game.dev.ghost


def test_the_dev_menu_draws(game):
    game.dev = DevTools()
    scene = DevScene(game, Starfield(SCREEN_SIZE))
    scene.draw(pygame.Surface(SCREEN_SIZE))


# --- Outils en jeu ----------------------------------------------------------------------------------------------------------------------
def key(name):
    return pygame.event.Event(pygame.KEYDOWN, key=DEV_KEYS[name])


@pytest.fixture
def scene(game, monkeypatch):
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState())
    game.dev = DevTools()
    mission = CAMPAIGN.get("hq")
    s = play_scene.PlayScene(game, mission.map_path)
    game.scenes.push(s)
    return s


def test_dev_keys_do_nothing_without_dev_mode(game, monkeypatch):
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState())
    s = play_scene.PlayScene(game, CAMPAIGN.get("outpost").map_path)
    game.scenes.push(s)
    for name in DEV_KEYS:
        s.handle_event(key(name))
    assert not s.inventory.has_keycard(3)
    assert not s.objective_done and game.dev is None


def test_invincible_stops_the_capture(scene):
    guard = scene.guards[0]
    guard.pos = V(scene.player.pos)
    guard._start_chase(scene.player)
    scene.update(1 / 60)
    assert scene.caught
    scene.restart()
    scene.handle_event(key("invincible"))
    guard = scene.guards[0]
    guard.pos = V(scene.player.pos)
    guard._start_chase(scene.player)
    for _ in range(30):
        scene.update(1 / 60)
    assert scene.game.dev.invincible and not scene.caught


def test_ghost_makes_the_player_invisible_and_silent(scene):
    scene.handle_event(key("ghost"))
    scene.update(1 / 60)
    assert scene.player.ghost and scene.player.detectability == 0 and scene.player.detectability_at(10) == 0 and scene.player.heard_radius == 0
    scene.handle_event(key("ghost"))
    scene.update(1 / 60)
    assert not scene.player.ghost and scene.player.detectability > 0


def test_the_loadout_gives_every_badge_and_decoys(scene):
    scene.handle_event(key("loadout"))
    assert scene.inventory.has_keycard(3)


def test_the_objective_key_completes_every_kind_of_objective(game, monkeypatch):
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState())
    game.dev = DevTools()
    for mission in CAMPAIGN.missions:
        s = play_scene.PlayScene(game, mission.map_path)
        game.scenes.push(s)
        assert not s.objective_done, mission.id
        s.handle_event(key("objective"))
        assert s.objective_done, mission.id
        game.scenes.pop()


def test_the_teleport_keys_move_the_player(scene):
    scene.handle_event(key("goto_exit"))
    exit_ = scene.tilemap.spawns_of("exit")[0]
    assert scene.player.pos == exit_.center(32)
    scene.handle_event(key("goto_goal"))
    goal = scene.goal_spawn()
    assert scene.player.pos == goal.center(32)


def test_the_hud_shows_the_dev_banner(scene):
    scene.game.dev.invincible = True
    surface = pygame.Surface(SCREEN_SIZE)
    scene.draw(surface)
    plain = pygame.image.tostring(surface, "RGB")
    scene.game.dev.invincible = False
    scene.draw(surface)
    assert pygame.image.tostring(surface, "RGB") != plain
