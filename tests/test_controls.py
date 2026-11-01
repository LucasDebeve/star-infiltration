"""Remappage des touches, manette, écran Commandes."""

import json
import os
from pathlib import Path

import pygame
import pytest

from game.core import bindings, gamepad
from game.core.bindings import ACTIONS, DEFAULTS, RESERVED, KeyBindings, key_label
from game.core.gamepad import GAME, MENU, START, A, B, Gamepad, X, Y, apply_deadzone
from game.core.input import read_input
from game.core.preferences import Preferences
from game.scenes import play_scene
from game.scenes.controls_scene import ControlsScene
from game.scenes.main_menu import MainMenuScene
from game.scenes.settings_scene import SettingsScene
from game.settings import GAMEPAD_AIM_RADIUS, GAMEPAD_DEADZONE, RESTART_KEY
from game.ui.backdrop import Starfield
from game.ui.menu import KeyBind
from tests.paths import SANDBOX

V = pygame.Vector2
KEY = lambda k: pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode="", scancode=0)  # noqa: E731


class FakePad:
    def __init__(self, instance_id=1):
        self.instance_id, self.name = instance_id, "Manette de test"
        self.axes, self.buttons = {}, set()

    def get_axis(self, axis):
        return self.axes.get(axis, 0.0)

    def get_button(self, button):
        return button in self.buttons


def pad_event(kind, button, instance_id=1):
    return pygame.event.Event(kind, instance_id=instance_id, button=button)


def axis_event(axis, value):
    return pygame.event.Event(pygame.CONTROLLERAXISMOTION, instance_id=1, axis=axis, value=int(value * 32767))


def keys_of(events):
    return [(e.type, e.key) for e in events]


@pytest.fixture(autouse=True)
def _video():
    """`read_input` interroge la souris : il lui faut un système vidéo (factice)."""
    pygame.init()
    pygame.display.set_mode((1280, 720))
    yield
    pygame.quit()


@pytest.fixture
def pad():
    p = FakePad()
    gamepad.current = Gamepad()
    gamepad.current.add(p)
    return p


# --- Libellés ----------------------------------------------------------------------------------------
def test_key_labels_are_readable_french():
    assert key_label(pygame.K_z) == "Z" and key_label(pygame.K_LSHIFT) == "Maj gauche" and key_label(pygame.K_SPACE) == "Espace"
    assert key_label(pygame.K_UP) == "Haut" and key_label(pygame.K_RETURN) == "Entrée" and key_label(pygame.K_F5) == "F5"


def test_labels_name_the_key_or_the_pad_button_depending_on_the_device():
    assert bindings.label("interact") == "E" and bindings.label("move") == "Z Q S D" and bindings.label("pause") == "Échap"
    bindings.device = bindings.PAD
    assert bindings.label("interact") == "A" and bindings.label("throw") == "X" and bindings.label("pause") == "Start"
    assert bindings.label("restart") == "Y" and "joystick" in bindings.label("move")
    assert bindings.label("interact", bindings.KEYBOARD) == "E"


def test_labels_follow_the_remapped_keys():
    bindings.current.rebind("interact", 0, pygame.K_x)
    assert bindings.label("interact") == "X"
    bindings.current.rebind("up", 0, pygame.K_w)
    assert bindings.label("move").startswith("W")


# --- Remappage ---------------------------------------------------------------------------------------------
def test_defaults_match_the_game_defaults():
    k = KeyBindings()
    assert k.keys("up") == (pygame.K_z, pygame.K_UP) and k.keys("interact") == (pygame.K_e,) and k.keys("throw") == (pygame.K_f,)
    assert k.is_default() and set(ACTIONS) == set(DEFAULTS)


def test_binding_a_free_key_replaces_only_that_slot():
    k = KeyBindings()
    assert k.rebind("up", 0, pygame.K_w).ok
    assert k.keys("up") == (pygame.K_w, pygame.K_UP) and not k.is_default()
    assert k.rebind("interact", 1, pygame.K_g).ok and k.keys("interact") == (pygame.K_e, pygame.K_g)


def test_a_key_already_used_elsewhere_is_swapped():
    k = KeyBindings()
    result = k.rebind("interact", 0, pygame.K_f)  # F servait à lancer un leurre
    assert result.ok and result.swapped_with == "throw" and "Lancer un leurre" in result.message
    assert k.keys("interact") == (pygame.K_f,) and k.keys("throw") == (pygame.K_e,)  # chacune a la touche de l'autre
    assert k.owner_of(pygame.K_f) == ("interact", 0)


def test_a_swap_that_would_leave_an_action_without_keys_is_refused():
    k = KeyBindings()
    result = k.rebind("interact", 1, pygame.K_f)  # l'emplacement 2 est vide, et F est l'unique touche du leurre
    assert not result.ok and "aucune touche" in result.message
    assert k.keys("throw") == (pygame.K_f,) and k.keys("interact") == (pygame.K_e,)


def test_swapping_two_slots_of_the_same_action():
    k = KeyBindings()
    assert k.rebind("up", 0, pygame.K_UP).ok
    assert k.keys("up") == (pygame.K_UP, pygame.K_z)


@pytest.mark.parametrize("key", sorted(RESERVED))
def test_reserved_keys_cannot_be_bound(key):
    k = KeyBindings()
    result = k.rebind("up", 0, key)
    assert not result.ok and "réservée" in result.message and k.is_default()


def test_rebinding_the_same_key_changes_nothing():
    k = KeyBindings()
    assert k.rebind("up", 0, pygame.K_z).ok and k.is_default()


def test_a_slot_can_be_cleared_but_not_the_last_key():
    k = KeyBindings()
    assert k.clear("up", 1).ok and k.keys("up") == (pygame.K_z,)
    result = k.clear("up", 0)
    assert not result.ok and "garder une touche" in result.message and k.keys("up") == (pygame.K_z,)
    assert k.clear("interact", 1).ok  # un emplacement déjà vide


def test_reset_restores_the_defaults():
    k = KeyBindings()
    k.rebind("up", 0, pygame.K_w)
    k.reset()
    assert k.is_default()


# --- Enregistrement ----------------------------------------------------------------------------------------------
def test_only_changed_actions_are_saved_by_name():
    k = KeyBindings()
    assert k.to_prefs() == {}
    k.rebind("up", 0, pygame.K_w)
    k.clear("run", 1)
    assert k.to_prefs() == {"up": ["w", "up"], "run": ["left shift", None]}


def test_bindings_survive_a_save_and_reload():
    k = KeyBindings()
    k.rebind("up", 0, pygame.K_w)
    k.rebind("crouch", 1, pygame.K_x)
    k.clear("run", 1)
    assert KeyBindings.from_prefs(json.loads(json.dumps(k.to_prefs()))).slots == k.slots


@pytest.mark.parametrize(
    "data",
    [None, [], "x", {"up": "w"}, {"up": ["w"]}, {"up": [1, 2]}, {"up": ["touche inventée", "w"]}, {"inconnue": ["a", "b"]}, {"up": [None, None]}],
)
def test_garbage_in_the_file_falls_back_to_the_defaults(data):
    assert KeyBindings.from_prefs(data).is_default()


def test_reserved_and_duplicate_keys_in_the_file_are_ignored():
    assert KeyBindings.from_prefs({"up": ["escape", "w"]}).keys("up") == DEFAULTS["up"]
    assert KeyBindings.from_prefs({"up": ["w", "w"]}).keys("up") == DEFAULTS["up"]


def test_a_key_given_to_two_actions_in_the_file_keeps_only_the_first():
    k = KeyBindings.from_prefs({"up": ["w", "up"], "down": ["w", "down"]})
    assert k.keys("up") == (pygame.K_w, pygame.K_UP) and k.keys("down") == DEFAULTS["down"]


def test_preferences_hold_keys_and_the_gamepad_flag(tmp_path):
    path = tmp_path / "p.json"
    prefs = Preferences.load(path)
    assert prefs.keys == {} and prefs.gamepad is True
    prefs.keys, prefs.gamepad = {"up": ["w", "up"]}, False
    prefs.save()
    again = Preferences.load(path)
    assert again.keys == {"up": ["w", "up"]} and again.gamepad is False


def test_preferences_ignore_a_corrupt_keys_entry(tmp_path):
    path = tmp_path / "p.json"
    path.write_text('{"keys": "n\'importe quoi", "gamepad": "oui"}')
    prefs = Preferences.load(path)
    assert prefs.keys == {} and prefs.gamepad is True


def test_the_game_loads_the_saved_keys_at_startup():
    from game.core.game import Game

    prefs = Preferences()
    prefs.keys = {"interact": ["g", None]}
    Game(prefs=prefs)
    pygame.event.clear()
    assert bindings.current.keys("interact") == (pygame.K_g,)
    pygame.quit()


# --- Lecture des touches ----------------------------------------------------------------------------------------------
class Pressed:
    def __init__(self, *down):
        self.down = set(down)

    def __getitem__(self, key):
        return key in self.down


def press(monkeypatch, *keys):
    monkeypatch.setattr(pygame.key, "get_pressed", lambda: Pressed(*keys))


def test_the_default_keys_move_the_player(monkeypatch):
    press(monkeypatch, pygame.K_z, pygame.K_d)
    state = read_input()
    assert state.move.x > 0 and state.move.y < 0 and state.move.length() == pytest.approx(1)


def test_remapped_keys_are_the_ones_read(monkeypatch):
    bindings.current.rebind("up", 0, pygame.K_w)
    bindings.current.rebind("up", 1, pygame.K_i)
    press(monkeypatch, pygame.K_w)
    assert read_input().move == V(0, -1)
    press(monkeypatch, pygame.K_z)  # l'ancienne touche ne fait plus rien
    assert read_input().move == V(0, 0)
    bindings.current.rebind("run", 0, pygame.K_x)
    bindings.current.rebind("interact", 0, pygame.K_g)
    press(monkeypatch, pygame.K_x, pygame.K_g)
    state = read_input()
    assert state.run and state.interact


# --- Joysticks ------------------------------------------------------------------------------------------------------------
def test_the_deadzone_ignores_drift_and_restarts_from_zero():
    assert apply_deadzone(0.1, 0.1) == V(0, 0) and apply_deadzone(0, 0.2) == V(0, 0)
    just_out = apply_deadzone(GAMEPAD_DEADZONE + 0.01, 0)
    assert 0 < just_out.x < 0.05  # pas de saut brutal à la sortie de la zone morte
    assert apply_deadzone(1, 0).x == pytest.approx(1) and apply_deadzone(1, 1).length() == pytest.approx(1)
    assert apply_deadzone(0, -0.6).y < 0


def test_the_left_stick_moves_the_player_progressively(pad, monkeypatch):
    press(monkeypatch)
    pad.axes[gamepad.AXIS_LX] = 1.0
    full = read_input().move
    pad.axes[gamepad.AXIS_LX] = 0.6
    half = read_input().move
    assert full == V(1, 0) and 0.2 < half.x < 0.7  # pousser doucement avance doucement
    pad.axes[gamepad.AXIS_LX] = 0.1
    assert read_input().move == V(0, 0)


def test_the_dpad_gives_full_speed_and_beats_the_stick(pad, monkeypatch):
    press(monkeypatch)
    pad.buttons.add(pygame.CONTROLLER_BUTTON_DPAD_LEFT)
    pad.axes[gamepad.AXIS_LX] = 0.5
    assert read_input().move == V(-1, 0)
    pad.buttons.add(pygame.CONTROLLER_BUTTON_DPAD_UP)
    assert read_input().move.length() == pytest.approx(1) and read_input().move.x < 0 > read_input().move.y


def test_the_keyboard_wins_while_it_moves(pad, monkeypatch):
    pad.axes[gamepad.AXIS_LX] = 1.0
    press(monkeypatch, pygame.K_q)
    assert read_input().move == V(-1, 0)


def test_pad_buttons_run_crouch_and_interact(pad, monkeypatch):
    press(monkeypatch)
    state = read_input()
    assert not (state.run or state.crouch or state.interact)
    pad.axes[gamepad.AXIS_RT] = 0.9
    pad.buttons.update({B, A})
    state = read_input()
    assert state.run and state.crouch and state.interact
    pad.axes[gamepad.AXIS_RT] = 0.2
    pad.buttons = {pygame.CONTROLLER_BUTTON_RIGHTSHOULDER}
    assert read_input().run and not read_input().crouch


def test_a_disabled_pad_does_nothing(pad, monkeypatch):
    press(monkeypatch)
    gamepad.current.enabled = False
    pad.axes[gamepad.AXIS_LX] = 1.0
    pad.buttons.add(A)
    state = read_input()
    assert state.move == V(0, 0) and not state.interact


def test_the_right_stick_aims_and_leans_the_camera(game, pad, monkeypatch):
    press(monkeypatch)
    gamepad.current.last_device = bindings.PAD
    pad.axes[gamepad.AXIS_RX] = 1.0
    state = read_input()
    center = V(pygame.display.get_surface().get_size()) / 2
    assert V(state.aim_screen) == center + V(GAMEPAD_AIM_RADIUS, 0) and state.aim_active
    pad.axes[gamepad.AXIS_RX] = 0.0
    pad.axes[gamepad.AXIS_LY] = -1.0  # sans joystick droit : on vise dans le sens où l'on marche, sans pencher la caméra
    state = read_input()
    assert V(state.aim_screen).y < center.y and not state.aim_active
    pad.axes[gamepad.AXIS_LY] = 0.0
    assert V(read_input().aim_screen).y < center.y  # la dernière direction est retenue (pour lancer un leurre à l'arrêt)


def test_the_mouse_aims_when_the_keyboard_was_the_last_device(game, pad, monkeypatch):
    press(monkeypatch)
    gamepad.current.last_device = bindings.KEYBOARD
    pad.axes[gamepad.AXIS_RX] = 1.0
    assert read_input().aim_screen == pygame.mouse.get_pos()


# --- Traduction des appuis en touches ---------------------------------------------------------------------------------------
def test_events_that_are_not_from_a_pad_are_left_alone(pad):
    assert gamepad.current.process(KEY(pygame.K_a), GAME) is None
    assert gamepad.current.process(pygame.event.Event(pygame.MOUSEMOTION, pos=(1, 1), rel=(0, 0), buttons=(0, 0, 0)), MENU) is None


def test_in_the_game_buttons_become_the_bound_keys(pad):
    p = gamepad.current.process
    assert keys_of(p(pad_event(pygame.CONTROLLERBUTTONDOWN, A), GAME)) == [(pygame.KEYDOWN, pygame.K_e)]
    assert keys_of(p(pad_event(pygame.CONTROLLERBUTTONUP, A), GAME)) == [(pygame.KEYUP, pygame.K_e)]
    assert keys_of(p(pad_event(pygame.CONTROLLERBUTTONDOWN, X), GAME)) == [(pygame.KEYDOWN, pygame.K_f)]
    assert keys_of(p(pad_event(pygame.CONTROLLERBUTTONDOWN, Y), GAME)) == [(pygame.KEYDOWN, RESTART_KEY)]
    assert keys_of(p(pad_event(pygame.CONTROLLERBUTTONDOWN, START), GAME)) == [(pygame.KEYDOWN, pygame.K_ESCAPE)]
    assert p(pad_event(pygame.CONTROLLERBUTTONDOWN, B), GAME) == []  # B s'accroupit : lu en continu, pas un appui


def test_in_the_game_the_pad_uses_the_remapped_keys(pad):
    bindings.current.rebind("interact", 0, pygame.K_g)
    bindings.current.rebind("throw", 0, pygame.K_t)
    p = gamepad.current.process
    assert keys_of(p(pad_event(pygame.CONTROLLERBUTTONDOWN, A), GAME)) == [(pygame.KEYDOWN, pygame.K_g)]
    assert keys_of(p(pad_event(pygame.CONTROLLERBUTTONDOWN, X), GAME)) == [(pygame.KEYDOWN, pygame.K_t)]


def test_in_menus_the_pad_navigates_like_the_keyboard(pad):
    p = gamepad.current.process
    assert keys_of(p(pad_event(pygame.CONTROLLERBUTTONDOWN, pygame.CONTROLLER_BUTTON_DPAD_DOWN), MENU)) == [(pygame.KEYDOWN, pygame.K_DOWN)]
    assert keys_of(p(pad_event(pygame.CONTROLLERBUTTONDOWN, pygame.CONTROLLER_BUTTON_DPAD_LEFT), MENU)) == [(pygame.KEYDOWN, pygame.K_LEFT)]
    assert keys_of(p(pad_event(pygame.CONTROLLERBUTTONDOWN, A), MENU)) == [(pygame.KEYDOWN, pygame.K_RETURN)]
    assert keys_of(p(pad_event(pygame.CONTROLLERBUTTONUP, A), MENU)) == [(pygame.KEYUP, pygame.K_RETURN)]  # le maintien du générique marche
    assert keys_of(p(pad_event(pygame.CONTROLLERBUTTONDOWN, B), MENU)) == [(pygame.KEYDOWN, pygame.K_ESCAPE)]
    assert keys_of(p(pad_event(pygame.CONTROLLERBUTTONDOWN, START), MENU)) == [(pygame.KEYDOWN, pygame.K_RETURN)]
    assert p(pad_event(pygame.CONTROLLERBUTTONDOWN, X), MENU) == []


def test_the_menu_stick_announces_a_direction_once_until_it_returns_to_the_middle(pad):
    p = gamepad.current.process
    down = p(axis_event(gamepad.AXIS_LY, 0.9), MENU)
    assert [e.key for e in down if e.type == pygame.KEYDOWN] == [pygame.K_DOWN]
    assert p(axis_event(gamepad.AXIS_LY, 1.0), MENU) == [] and p(axis_event(gamepad.AXIS_LY, 0.5), MENU) == []  # pas de répétition
    assert p(axis_event(gamepad.AXIS_LY, 0.1), MENU) == []  # relâché
    again = p(axis_event(gamepad.AXIS_LY, -0.9), MENU)
    assert [e.key for e in again if e.type == pygame.KEYDOWN] == [pygame.K_UP]
    assert [e.key for e in p(axis_event(gamepad.AXIS_LX, 0.0), MENU)] == []
    p(axis_event(gamepad.AXIS_LY, 0.0), MENU)
    assert [e.key for e in p(axis_event(gamepad.AXIS_LX, 0.9), MENU) if e.type == pygame.KEYDOWN] == [pygame.K_RIGHT]


def test_the_stick_does_not_navigate_during_the_game(pad):
    assert gamepad.current.process(axis_event(gamepad.AXIS_LY, 1.0), GAME) == []


def test_a_disabled_pad_swallows_its_events(pad):
    gamepad.current.enabled = False
    assert gamepad.current.process(pad_event(pygame.CONTROLLERBUTTONDOWN, A), MENU) == []


def test_the_last_device_follows_what_the_player_touches(pad):
    g = gamepad.current
    assert g.last_device == bindings.KEYBOARD
    g.process(pad_event(pygame.CONTROLLERBUTTONDOWN, A), MENU)
    assert g.last_device == bindings.PAD
    g.note_device(KEY(pygame.K_a))
    assert g.last_device == bindings.KEYBOARD
    g.process(axis_event(gamepad.AXIS_LX, 0.9), MENU)
    assert g.last_device == bindings.PAD
    g.note_device(pygame.event.Event(pygame.MOUSEMOTION, pos=(1, 1), rel=(0, 0), buttons=(0, 0, 0)))
    assert g.last_device == bindings.KEYBOARD
    g.process(axis_event(gamepad.AXIS_LX, 0.05), MENU)  # une dérive du joystick ne compte pas comme un usage
    assert g.last_device == bindings.KEYBOARD


def test_unplugging_the_last_pad_goes_back_to_the_keyboard(pad):
    g = gamepad.current
    g.last_device = bindings.PAD
    assert g.connected and g.name == "Manette de test"
    g.process(pygame.event.Event(pygame.CONTROLLERDEVICEREMOVED, instance_id=1), MENU)
    assert not g.connected and g.name == "" and g.last_device == bindings.KEYBOARD


# --- Dans le jeu --------------------------------------------------------------------------------------------------------------
def test_a_pad_button_reaches_the_game_scene_as_a_key(game, pad):
    gamepad.current = game.gamepad
    game.gamepad.add(pad)
    scene = play_scene.PlayScene(game, SANDBOX)
    game.scenes.push(scene)
    assert scene.pad_context == GAME
    pygame.event.post(pad_event(pygame.CONTROLLERBUTTONDOWN, A))
    game.step(1 / 60)
    pygame.event.post(pad_event(pygame.CONTROLLERBUTTONDOWN, START))
    game.step(1 / 60)
    assert type(game.scenes.current).__name__ == "PauseScene"  # Start met en pause


def test_a_pad_navigates_a_menu_through_the_game_loop(game):
    game.scenes.push(MainMenuScene(game))
    menu = game.scenes.current
    before = menu.menu.index
    pygame.event.post(pad_event(pygame.CONTROLLERBUTTONDOWN, pygame.CONTROLLER_BUTTON_DPAD_DOWN))
    game.step(1 / 60)
    assert menu.menu.index == (before + 1) % len(menu.menu.items)
    assert bindings.device == bindings.PAD  # les invites parlent désormais de boutons


def test_using_the_keyboard_again_switches_the_prompts_back(game):
    game.scenes.push(MainMenuScene(game))
    pygame.event.post(pad_event(pygame.CONTROLLERBUTTONDOWN, pygame.CONTROLLER_BUTTON_DPAD_DOWN))
    game.step(1 / 60)
    pygame.event.post(KEY(pygame.K_DOWN))
    game.step(1 / 60)
    assert bindings.device == bindings.KEYBOARD


def test_the_game_has_a_gamepad_that_follows_the_preference(game):
    assert game.gamepad is gamepad.current and game.gamepad.enabled
    off = Preferences()
    off.gamepad = False
    from game.core.game import Game

    assert not Game(prefs=off).gamepad.enabled
    pygame.quit()


# --- L'écran Commandes ----------------------------------------------------------------------------------------------------------------
@pytest.fixture
def controls(game):
    game.scenes.push(MainMenuScene(game))
    scene = ControlsScene(game, Starfield(game.screen.get_size(), seed=1))
    game.scenes.push(scene)
    return scene


def saved_prefs():
    return json.loads((Path(os.environ["STAR_INFILTRATION_HOME"]) / "preferences.json").read_text())


def select_action(scene, action):
    scene.menu.select(ACTIONS.index(action))
    return scene.menu.selected


def test_the_controls_screen_lists_every_action_then_the_pad_and_back(controls):
    items = controls.menu.items
    assert [i.label for i in items[: len(ACTIONS)]] == [bindings.ACTION_LABELS[a] for a in ACTIONS]
    assert all(isinstance(i, KeyBind) for i in items[: len(ACTIONS)])
    assert [i.label for i in items[len(ACTIONS) :]] == ["Utiliser la manette", "Rétablir les touches par défaut", "Retour"]


def test_each_row_shows_its_two_keys_and_marks_the_slot_that_will_change(controls):
    item = select_action(controls, "up")
    assert item.value_text() == "[Z]   Haut"
    controls.handle_event(KEY(pygame.K_RIGHT))
    assert item.value_text() == "Z   [Haut]"
    assert select_action(controls, "interact").value_text() == "[E]   —"


def test_remapping_a_key_end_to_end(controls, game):
    select_action(controls, "interact")
    controls.handle_event(KEY(pygame.K_RETURN))
    assert controls.waiting == ("interact", 0)
    controls.handle_event(KEY(pygame.K_g))
    assert controls.waiting is None
    assert bindings.current.keys("interact") == (pygame.K_g,)
    assert game.prefs.keys == {"interact": ["g", None]} and saved_prefs()["keys"] == {"interact": ["g", None]}


def test_the_second_slot_can_be_remapped_too(controls):
    select_action(controls, "up")
    controls.handle_event(KEY(pygame.K_RIGHT))
    controls.handle_event(KEY(pygame.K_RETURN))
    controls.handle_event(KEY(pygame.K_i))
    assert bindings.current.keys("up") == (pygame.K_z, pygame.K_i)


def test_escape_cancels_the_capture(controls):
    select_action(controls, "up")
    controls.handle_event(KEY(pygame.K_RETURN))
    controls.handle_event(KEY(pygame.K_ESCAPE))
    assert controls.waiting is None and bindings.current.is_default() and "annulé" in controls.message
    assert game_scene_is(controls)


def game_scene_is(controls):
    return controls.game.scenes.current is controls  # Échap n'a pas quitté l'écran


def test_the_menu_keys_do_not_navigate_while_waiting_for_a_key(controls):
    select_action(controls, "up")
    controls.handle_event(KEY(pygame.K_RETURN))
    index = controls.menu.index
    controls.handle_event(KEY(pygame.K_DOWN))  # c'est la nouvelle touche, pas un déplacement dans le menu
    assert controls.menu.index == index and bindings.current.owner_of(pygame.K_DOWN) is not None


def test_a_reserved_key_is_explained_and_not_bound(controls):
    select_action(controls, "up")
    controls.handle_event(KEY(pygame.K_RETURN))
    controls.handle_event(KEY(pygame.K_r))
    assert "réservée" in controls.message and bindings.current.is_default() and controls.game.prefs.keys == {}


def test_a_taken_key_swaps_and_says_so(controls):
    select_action(controls, "interact")
    controls.handle_event(KEY(pygame.K_RETURN))
    controls.handle_event(KEY(pygame.K_f))
    assert "Lancer un leurre" in controls.message
    assert bindings.current.keys("interact") == (pygame.K_f,) and bindings.current.keys("throw") == (pygame.K_e,)


def test_delete_empties_the_selected_slot_but_keeps_one_key(controls):
    select_action(controls, "up")
    controls.handle_event(KEY(pygame.K_RIGHT))
    controls.handle_event(KEY(pygame.K_DELETE))
    assert bindings.current.keys("up") == (pygame.K_z,) and controls.game.prefs.keys["up"] == ["z", None]
    controls.handle_event(KEY(pygame.K_LEFT))
    controls.handle_event(KEY(pygame.K_BACKSPACE))
    assert bindings.current.keys("up") == (pygame.K_z,) and "garder une touche" in controls.message


def test_reset_restores_and_saves_the_default_keys(controls, game):
    select_action(controls, "up")
    controls.handle_event(KEY(pygame.K_RETURN))
    controls.handle_event(KEY(pygame.K_w))
    controls.menu.select(len(ACTIONS) + 1)
    controls.handle_event(KEY(pygame.K_RETURN))
    assert bindings.current.is_default() and game.prefs.keys == {} and saved_prefs()["keys"] == {}


def test_the_pad_toggle_is_applied_and_saved(controls, game):
    controls.menu.select(len(ACTIONS))
    controls.handle_event(KEY(pygame.K_RETURN))
    assert game.prefs.gamepad is False and game.gamepad.enabled is False and saved_prefs()["gamepad"] is False
    controls.handle_event(KEY(pygame.K_RETURN))
    assert game.gamepad.enabled is True


def test_back_returns_to_the_previous_screen(controls, game):
    controls.handle_event(KEY(pygame.K_ESCAPE))
    assert isinstance(game.scenes.current, MainMenuScene)


def test_a_click_cancels_a_pending_capture(controls):
    select_action(controls, "up")
    controls.handle_event(KEY(pygame.K_RETURN))
    controls.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(5, 5), button=1))
    assert controls.waiting is None


def test_the_controls_screen_draws_in_every_state(controls, game):
    surface = pygame.Surface(game.screen.get_size())
    controls.draw(surface)
    game.gamepad.add(FakePad())
    controls.message = "Un message"
    controls.draw(surface)
    select_action(controls, "up")
    controls.handle_event(KEY(pygame.K_RETURN))
    controls.draw(surface)


def test_the_settings_screen_opens_the_controls_screen(game):
    settings = SettingsScene(game, Starfield(game.screen.get_size(), seed=1))
    game.scenes.push(MainMenuScene(game))
    game.scenes.push(settings)
    entry = next(i for i, item in enumerate(settings.menu.items) if item.label.startswith("Commandes"))
    settings.menu.select(entry)
    settings.handle_event(KEY(pygame.K_RETURN))
    assert isinstance(game.scenes.current, ControlsScene)


def test_the_remapped_keys_drive_the_game_scene(game):
    bindings.current.rebind("interact", 0, pygame.K_g)
    bindings.current.rebind("throw", 0, pygame.K_t)
    scene = play_scene.PlayScene(game, SANDBOX)
    game.scenes.push(scene)
    scene.handle_event(KEY(pygame.K_e))
    assert not scene._interact_pressed  # l'ancienne touche ne fait plus rien
    scene.handle_event(KEY(pygame.K_g))
    assert scene._interact_pressed
    scene.handle_event(KEY(pygame.K_t))
    assert scene._throw_requested


def test_the_help_shown_on_pause_follows_the_remapped_keys():
    from game.ui.hud import help_lines

    bindings.current.rebind("interact", 0, pygame.K_g)
    assert "G : interagir" in help_lines()[1]
    bindings.device = bindings.PAD
    assert "A : interagir" in help_lines()[1] and "Start : pause" in help_lines()[1]
