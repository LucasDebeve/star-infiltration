import json

import pygame
import pytest

from game.core.game import Game
from game.core.input import InputState
from game.core.preferences import default_path
from game.core.scene import Scene, SceneManager
from game.scenes import play_scene
from game.scenes.main_menu import MainMenuScene
from game.scenes.pause_scene import PauseScene
from game.scenes.settings_scene import SettingsScene
from game.settings import DUCK_VOLUME
from tests.paths import SANDBOX

KEY = lambda key: pygame.event.Event(pygame.KEYDOWN, key=key)  # noqa: E731


@pytest.fixture
def game():
    g = Game()
    pygame.event.clear()  # le pilote vidéo factice envoie des « perte de focus » au démarrage
    yield g
    pygame.quit()


@pytest.fixture
def menu(game):
    scene = MainMenuScene(game)
    game.scenes.push(scene)
    return scene


def labels(scene):
    return [item.label for item in scene.menu.items]


def saved():
    return json.loads(default_path().read_text())


# --- Gestionnaire de scènes ---------------------------------------------------
class Probe(Scene):
    def __init__(self, game, log, name):
        super().__init__(game)
        self.log, self.name = log, name

    def on_enter(self):
        self.log.append(f"enter {self.name}")

    def on_exit(self):
        self.log.append(f"exit {self.name}")

    def on_resume(self):
        self.log.append(f"resume {self.name}")


def test_pop_wakes_the_scene_below():
    log, manager = [], SceneManager()
    manager.push(Probe(None, log, "jeu"))
    manager.push(Probe(None, log, "pause"))
    manager.pop()
    assert log == ["enter jeu", "enter pause", "exit pause", "resume jeu"]


def test_replace_does_not_resume_the_scene_below():
    log, manager = [], SceneManager()
    manager.push(Probe(None, log, "a"))
    manager.push(Probe(None, log, "b"))
    manager.replace(Probe(None, log, "c"))
    assert log == ["enter a", "enter b", "exit b", "enter c"]
    assert manager.current.name == "c"


def test_clear_exits_every_scene_from_the_top():
    log, manager = [], SceneManager()
    for name in "abc":
        manager.push(Probe(None, log, name))
    log.clear()
    manager.clear()
    assert log == ["exit c", "exit b", "exit a"] and manager.current is None
    manager.clear()  # sans danger sur une pile vide


# --- Menu principal -----------------------------------------------------------
def test_main_menu_lists_campaign_settings_and_quit(menu):
    assert labels(menu) == ["Campagne", "Réglages", "Quitter"]


def test_main_menu_starts_music_without_tension(menu, game):
    menu.on_enter()
    assert game.audio._music_channels and game.audio.tension_target == 0.0


def test_enter_opens_the_campaign_map(menu, game):
    from game.scenes.campaign_scene import CampaignScene

    menu.handle_event(KEY(pygame.K_RETURN))
    assert isinstance(game.scenes.current, CampaignScene)
    game.scenes.current.handle_event(KEY(pygame.K_ESCAPE))
    assert game.scenes.current is menu  # Échap ramène au menu principal


def test_zqsd_navigates_like_the_arrows(menu):
    menu.handle_event(KEY(pygame.K_s))
    assert menu.menu.index == 1
    menu.handle_event(KEY(pygame.K_z))
    assert menu.menu.index == 0


def test_quit_entry_stops_the_game(menu, game):
    game.running = True
    menu.menu.select(len(menu.menu.items) - 1)
    menu.handle_event(KEY(pygame.K_RETURN))
    assert game.running is False


def test_escape_does_nothing_in_the_main_menu(menu, game):
    menu.handle_event(KEY(pygame.K_ESCAPE))
    assert game.scenes.current is menu


def test_mouse_hover_selects_and_click_activates(menu, game):
    from game.ui.menu import row_rects

    rects = row_rects(game.screen.get_size(), len(menu.menu.items), menu.top)
    menu.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=rects[1].center, rel=(0, 0), buttons=(0, 0, 0)))
    assert menu.menu.index == 1
    menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=rects[0].center, button=1))
    assert type(game.scenes.current).__name__ == "CampaignScene"


@pytest.mark.parametrize("scene_name", ["main", "settings", "pause"])
def test_moving_the_mouse_over_empty_space_never_crashes(game, scene_name, monkeypatch):
    """Régression : un survol hors des lignes du menu faisait planter le jeu dès les premiers mouvements de souris."""
    if scene_name == "main":
        scene = MainMenuScene(game)
    elif scene_name == "settings":
        scene = SettingsScene(game, MainMenuScene(game).backdrop)
    else:
        play = play_scene.PlayScene(game, SANDBOX)
        game.scenes.push(play)
        scene = PauseScene(game, play)
    game.scenes.push(scene)
    before = scene.menu.index
    for pos in ((0, 0), (5, 700), (1279, 719), (640, 10), (100, 360)):  # coins, bords, hors de la colonne
        scene.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=pos, rel=(0, 0), buttons=(0, 0, 0)))
        scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1))
    assert scene.menu.index == before  # la sélection n'a pas bougé et rien n'a été activé


def test_clicking_outside_or_with_another_button_does_nothing(menu, game):
    menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(5, 5), button=1))
    menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(640, 300 + 20), button=3))
    assert game.scenes.current is menu


def test_main_menu_draws_and_animates(menu, game):
    for _ in range(30):
        game.step(1 / 60)


# --- Réglages -----------------------------------------------------------------
@pytest.fixture
def settings(game):
    game.scenes.push(MainMenuScene(game))
    scene = SettingsScene(game, game.scenes.current.backdrop)
    game.scenes.push(scene)
    return scene


def test_volume_slider_changes_prefs_and_saves_immediately(settings, game):
    settings.handle_event(KEY(pygame.K_LEFT))
    assert game.prefs.master == pytest.approx(0.7)
    assert saved()["master"] == pytest.approx(0.7)


def test_volume_changes_are_audible_immediately(settings, game):
    game.audio.start_music()
    before = game.audio.layer_volumes()[0]
    settings.menu.select(1)  # musique
    for _ in range(3):
        settings.handle_event(KEY(pygame.K_LEFT))
    game.audio.update(0.01)
    assert game.audio.layer_volumes()[0] < before


def test_lighting_toggle(settings, game):
    settings.menu.select(3)
    settings.handle_event(KEY(pygame.K_RETURN))
    assert game.prefs.lighting is False and saved()["lighting"] is False
    settings.handle_event(KEY(pygame.K_RETURN))
    assert game.prefs.lighting is True


def test_screen_shake_toggle_saves_the_preference(settings, game):
    settings.menu.select(4)
    assert game.prefs.screen_shake is True
    settings.handle_event(KEY(pygame.K_RETURN))
    assert game.prefs.screen_shake is False and saved()["screen_shake"] is False


def test_fullscreen_pref_reflects_what_the_system_granted(settings, game):
    settings.menu.select(5)
    settings.handle_event(KEY(pygame.K_RETURN))
    assert game.prefs.fullscreen == game.fullscreen  # jamais en désaccord avec la réalité


def test_difficulty_choice_cycles_and_saves(settings, game):
    settings.menu.select(6)
    settings.handle_event(KEY(pygame.K_RIGHT))
    assert game.prefs.difficulty == "hard" and saved()["difficulty"] == "hard"
    settings.handle_event(KEY(pygame.K_RIGHT))
    assert game.prefs.difficulty == "easy"
    settings.handle_event(KEY(pygame.K_LEFT))
    assert game.prefs.difficulty == "hard"


def test_escape_and_back_button_return(settings, game):
    settings.handle_event(KEY(pygame.K_ESCAPE))
    assert isinstance(game.scenes.current, MainMenuScene)
    game.scenes.push(settings)
    settings.menu.select(len(settings.menu.items) - 1)
    settings.handle_event(KEY(pygame.K_RETURN))
    assert isinstance(game.scenes.current, MainMenuScene)


def test_clicking_a_slider_adjusts_by_side(settings, game):
    from game.ui.menu import row_rects

    rect = row_rects(game.screen.get_size(), len(settings.menu.items), settings.top)[0]
    settings.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(rect.right - 20, rect.centery), button=1))
    assert game.prefs.master == pytest.approx(0.9)
    settings.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(rect.x + 20, rect.centery), button=1))
    assert game.prefs.master == pytest.approx(0.8)


def test_settings_scene_draws_with_the_difficulty_summary(settings, game):
    game.step(1 / 60)


def test_preferences_survive_a_new_game(game):
    game.prefs.music, game.prefs.difficulty = 0.2, "easy"
    game.prefs.save()
    again = Game()
    assert again.prefs.music == 0.2 and again.prefs.difficulty == "easy"


# --- Pause --------------------------------------------------------------------
@pytest.fixture
def playing(game, monkeypatch):
    scene = play_scene.PlayScene(game, SANDBOX)
    game.scenes.push(scene)
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState(move=pygame.Vector2(1, 0), run=True))
    return scene


def pause(playing, game):
    playing.handle_event(KEY(pygame.K_ESCAPE))
    return game.scenes.current


def test_escape_pauses_and_escape_resumes(playing, game):
    paused = pause(playing, game)
    assert isinstance(paused, PauseScene)
    paused.handle_event(KEY(pygame.K_ESCAPE))
    assert game.scenes.current is playing


def test_the_game_is_frozen_while_paused(playing, game):
    playing.guards.clear()
    pause(playing, game)
    before = pygame.Vector2(playing.player.pos)
    for _ in range(60):
        game.step(1 / 60)  # seule la scène du dessus avance
    assert playing.player.pos == before
    game.scenes.pop()
    for _ in range(30):
        game.step(1 / 60)
    assert playing.player.pos.x > before.x  # la partie reprend


def test_music_is_ducked_during_the_pause_only(playing, game):
    game.audio.start_music()
    normal = game.audio.layer_volumes()[0]
    pause(playing, game)
    assert game.audio.layer_volumes()[0] == pytest.approx(normal * DUCK_VOLUME)
    game.scenes.pop()
    assert game.audio.layer_volumes()[0] == pytest.approx(normal)


def test_losing_window_focus_pauses_once(playing, game):
    playing.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST))
    assert isinstance(game.scenes.current, PauseScene)
    game.scenes.current.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST))  # déjà en pause
    assert isinstance(game.scenes.current, PauseScene) and len(game.scenes._stack) == 2


def test_resume_button(playing, game):
    paused = pause(playing, game)
    paused.handle_event(KEY(pygame.K_RETURN))  # « Reprendre » est en tête
    assert game.scenes.current is playing


def test_restart_from_the_pause_menu(playing, game):
    playing.caught = True
    playing.player.pos.update(300, 300)
    paused = pause(playing, game)
    paused.menu.select(1)
    paused.handle_event(KEY(pygame.K_RETURN))
    assert game.scenes.current is playing and not playing.caught
    start = playing.tilemap.spawns_of("player")[0].center(playing.tilemap.tile_size)
    assert playing.player.pos == start


def test_main_menu_button_unwinds_everything(playing, game):
    paused = pause(playing, game)
    paused.menu.select(3)
    paused.handle_event(KEY(pygame.K_RETURN))
    assert isinstance(game.scenes.current, MainMenuScene) and len(game.scenes._stack) == 1
    game.events.emit("noise", pos=pygame.Vector2(0, 0), radius=10)  # la partie s'est bien désabonnée
    assert game.audio.tension_target == 0.0


def test_quit_button(playing, game):
    game.running = True
    paused = pause(playing, game)
    paused.menu.select(4)
    paused.handle_event(KEY(pygame.K_RETURN))
    assert game.running is False


def test_settings_from_the_pause_menu_and_back(playing, game):
    paused = pause(playing, game)
    paused.menu.select(2)
    paused.handle_event(KEY(pygame.K_RETURN))
    assert isinstance(game.scenes.current, SettingsScene)
    game.scenes.current.handle_event(KEY(pygame.K_ESCAPE))
    assert game.scenes.current is paused  # retour à la pause, pas au jeu
    assert game.audio.ducked


def test_the_alert_klaxon_goes_quiet_during_the_pause_and_comes_back(playing, game):
    game.audio.start_loop("alert", 0.5)
    channel = game.audio._loops["alert"][0]
    loud = channel.get_volume()
    assert loud > 0
    pause(playing, game)
    assert channel.get_volume() == 0.0
    game.scenes.pop()
    assert channel.get_volume() == pytest.approx(loud)


def test_leaving_to_the_main_menu_stops_the_klaxon(playing, game):
    game.audio.start_loop("alert", 0.5)
    playing.director.update(0.1, [], (0, 0), hacking=False, alert_active=True)
    paused = pause(playing, game)
    paused.menu.select(3)
    paused.handle_event(KEY(pygame.K_RETURN))
    assert not game.audio.is_looping("alert")


def test_lighting_changed_in_the_pause_applies_on_resume(playing, game):
    assert playing.lighting.enabled
    paused = pause(playing, game)
    paused.menu.select(2)
    paused.handle_event(KEY(pygame.K_RETURN))
    settings = game.scenes.current
    settings.menu.select(3)
    settings.handle_event(KEY(pygame.K_RETURN))  # éclairage coupé
    settings.handle_event(KEY(pygame.K_ESCAPE))
    paused.handle_event(KEY(pygame.K_ESCAPE))
    assert not playing.lighting.enabled


def test_pause_menu_draws_a_blurred_snapshot(playing, game):
    game.step(1 / 60)
    paused = pause(playing, game)
    for _ in range(3):
        game.step(1 / 60)
    assert paused.subtitle.startswith("Difficulté : ")


def test_pause_works_after_winning_or_losing_too(playing, game):
    playing.caught = True
    assert isinstance(pause(playing, game), PauseScene)


# --- Difficulté en jeu --------------------------------------------------------
@pytest.mark.parametrize("key", ["easy", "normal", "hard"])
def test_scene_applies_the_chosen_difficulty(game, key):
    from game.difficulty import get_difficulty

    game.prefs.difficulty = key
    scene = play_scene.PlayScene(game, SANDBOX)
    wanted = get_difficulty(key)
    assert scene.alert.difficulty == wanted
    assert all(g.sensitivity == wanted.detect for g in scene.guards)
    assert scene.alert.time_left == wanted.lockdown_time


def test_restart_rereads_the_difficulty(game):
    scene = play_scene.PlayScene(game, SANDBOX)
    assert scene.alert.difficulty.key == "normal"
    game.prefs.difficulty = "hard"
    scene.restart()
    assert scene.alert.difficulty.key == "hard"


def test_harder_guards_spot_the_player_faster(game):
    from game.ai.guard import Guard

    def awareness(key):
        game.prefs.difficulty = key
        scene = play_scene.PlayScene(game, SANDBOX)
        guard = Guard([pygame.Vector2(100, 100)], 0.0)
        guard.sensitivity = scene.difficulty.detect
        guard._update_awareness(0.1, type("T", (), {"pos": pygame.Vector2(180, 100), "detectability": 1.0})(), True)
        return guard.awareness

    assert awareness("easy") < awareness("normal") < awareness("hard")


def test_lockdown_time_depends_on_difficulty(game):
    from game.ai.guard import Guard, GuardState
    from game.difficulty import get_difficulty
    from game.entities.player import Player
    from game.systems.alert import AlertSystem
    from game.world.tilemap import Tilemap

    tm = Tilemap.from_text("#########\n#.......#\n#########")
    for key in ("easy", "hard"):
        system = AlertSystem(game.events, tm, [], None, get_difficulty(key))
        chaser = Guard([pygame.Vector2(48, 48)], 0.0)
        chaser.state = GuardState.CHASE
        system.update(0.1, [chaser], Player(100, 48))
        assert system.time_left == get_difficulty(key).lockdown_time
    assert get_difficulty("easy").lockdown_time > get_difficulty("hard").lockdown_time


# --- Point d'entrée -----------------------------------------------------------
def test_main_opens_the_main_menu(monkeypatch):
    import main

    started = []
    monkeypatch.setattr(Game, "run", lambda self: started.append(type(self.scenes.current).__name__))
    main.main()
    assert started == ["MainMenuScene"]
    pygame.quit()
