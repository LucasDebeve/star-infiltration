"""Terminaux à menu, caméras de surveillance, lumière coupée depuis un terminal, et éclairage qui influence la détection."""
import math

import pygame
import pytest

from game.ai.guard import Guard, GuardState
from game.core.camera import Camera
from game.core.input import InputState
from game.entities.security_camera import SecurityCamera
from game.objectives import STEAL_PLANS, infer_objective, objective_spawns
from game.scenes import play_scene
from game.settings import (
    AMBIENT_BLACKOUT,
    CAMERA_ALARM_TIME,
    CAMERA_OFF_TIME,
    CAMERA_RANGE,
    CAMERA_RESPONDERS,
    CAMERA_SWEEP,
    CAMERA_SWEEP_PERIOD,
    LAMP_FADE_TIME,
    LAMP_RADIUS,
    LIGHTS_OUT_TIME,
    TERMINAL_JOB_TIME,
    TERMINAL_LINK_RANGE,
    VISIBILITY_FACTORS,
)
from game.terminals import CAMERAS, DATA, LIGHTS, TerminalSpec, parse_capabilities
from game.world.exposure import DIM, LIT, SHADOW, falloff, light_at, luminance, visibility_factor, visibility_zone
from game.world.level_check import check_level
from game.world.surveillance import CameraSpec, parse_camera
from game.world.tilemap import Tilemap
from tests.paths import BLACKOUT, CAMPAIGN, CRUISER, SANDBOX, TRAINING
from tests.runner import Runner

V = pygame.Vector2
KEY_E = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_e)
ROOM = "#" * 22 + "\n" + ("#" + "." * 20 + "#\n") * 7 + "#" * 22 + "\n"


def tile_center(x, y):
    return V((x + 0.5) * 32, (y + 0.5) * 32)


# --- Pouvoirs d'un terminal : déclarés dans la carte ---------------------------------------------------------
def test_a_terminal_only_downloads_data_by_default():
    tm = Tilemap.from_text("#####\n#PTE#\n#####\n")
    spec = tm.terminal_spec((2, 1))
    assert spec.capabilities == (DATA,) and spec.can(DATA) and not spec.can(LIGHTS) and not spec.can(CAMERAS)


def test_the_directive_gives_a_terminal_its_powers_in_menu_order():
    tm = Tilemap.from_text("#####\n#PTE#\n#####\n@terminal 2,1 -> lights cameras\n")
    assert tm.terminal_spec((2, 1)).capabilities == (CAMERAS, LIGHTS)  # l'ordre du menu, pas celui de la ligne


def test_camera_groups_restrict_what_a_terminal_commands():
    spec = parse_capabilities("cameras:ab")
    assert spec == ((CAMERAS,), "ab")
    terminal = TerminalSpec((1, 1), *spec)
    assert terminal.controls("a") and terminal.controls("b") and not terminal.controls("c")
    assert TerminalSpec((1, 1), (CAMERAS,)).controls("z")  # sans groupe : toutes
    assert not TerminalSpec((1, 1), (LIGHTS,)).controls("a")


@pytest.mark.parametrize(
    "text,message",
    [("piller", "pouvoir inconnu"), ("data data", "deux fois"), ("", "aucun pouvoir"), ("data:a", "seul 'cameras'"), ("cameras:A1", "groupes de caméras illisibles")],
)
def test_bad_capabilities_are_explained(text, message):
    with pytest.raises(ValueError, match=message):
        parse_capabilities(text)


@pytest.mark.parametrize(
    "line,message",
    [
        ("@terminal 1,1 -> data", "pas de terminal"),
        ("@terminal 2,1 -> piller", "pouvoir inconnu"),
        ("@terminal 2,1", "Terminal illisible"),
        ("@terminal 2,1 -> data\n@terminal 2,1 -> lights", "déjà configuré"),
    ],
)
def test_bad_terminal_directives_name_their_line(line, message):
    with pytest.raises(ValueError, match=rf"Ligne \d : .*{message}"):
        Tilemap.from_text("#####\n#PTE#\n#####\n" + line + "\n")


def test_only_terminals_that_download_data_carry_the_objective():
    tm = Tilemap.from_text("########\n#PTT.E.#\n########\n@terminal 2,1 -> lights\n")
    goal = objective_spawns(tm, STEAL_PLANS)
    assert [(s.tx, s.ty) for s in goal] == [(3, 1)] and infer_objective(tm) is STEAL_PLANS


def test_a_map_with_only_utility_terminals_has_no_objective_terminal():
    tm = Tilemap.from_text("#####\n#PTE#\n#####\n@terminal 2,1 -> lights\n")
    assert any("télécharge des données" in p for p in check_level(tm))


def test_two_data_terminals_are_refused_but_a_utility_one_is_fine():
    two = Tilemap.from_text("########\n#PTT.E.#\n########\n")
    assert any("plusieurs terminaux de données" in p for p in check_level(two))
    mixed = Tilemap.from_text("########\n#PTT.E.#\n########\n@terminal 2,1 -> lights\n")
    assert check_level(mixed) == []


def test_a_utility_terminal_must_be_reachable():
    tm = Tilemap.from_text("##########\n#PT.#T#E.#\n##########\n@terminal 5,1 -> lights\n")
    assert any("objet 'terminal' inaccessible" in p for p in check_level(tm))


def test_a_camera_terminal_needs_a_camera_to_command():
    tm = Tilemap.from_text("#####\n#PTE#\n#####\n@terminal 2,1 -> data cameras\n")
    assert any("aucune caméra à commander" in p for p in check_level(tm))
    ok = Tilemap.from_text("#####\n#PTE#\n#####\n@terminal 2,1 -> data cameras\n@camera 2,0 -> S\n")
    assert check_level(ok) == []
    wrong_group = Tilemap.from_text("#####\n#PTE#\n#####\n@terminal 2,1 -> data cameras:b\n@camera 2,0 -> S a\n")
    assert any("aucune caméra" in p for p in check_level(wrong_group))


# --- Directive @camera ------------------------------------------------------------------------------------------------------
def test_the_camera_directive_reads_direction_group_and_sweep():
    assert parse_camera((3, 0), "S") == CameraSpec((3, 0), "S", "a", math.degrees(CAMERA_SWEEP))
    assert parse_camera((3, 0), "O b 30") == CameraSpec((3, 0), "O", "b", 30.0)
    assert parse_camera((3, 0), "E 15 c").group == "c" and parse_camera((3, 0), "E 15 c").sweep == 15


@pytest.mark.parametrize("rest,message", [("", "direction attendue"), ("X", "direction attendue"), ("S 120", "hors de 0"), ("S bleu", "ni une lettre"), ("S -3", "hors de 0")])
def test_bad_camera_arguments_are_explained(rest, message):
    with pytest.raises(ValueError, match=message):
        parse_camera((3, 0), rest)


@pytest.mark.parametrize(
    "line,message",
    [
        ("@camera 2,1 -> S", "se fixe sur un mur"),
        ("@camera 2,0 -> N", "regarderait contre un mur"),
        ("@camera 2,0 -> S\n@camera 2,0 -> S", "déjà une caméra"),
        ("@camera 2,0", "Caméra illisible"),
        ("@camera 2,0 -> Z", "direction attendue"),
    ],
)
def test_bad_camera_directives_name_their_line(line, message):
    with pytest.raises(ValueError, match=rf"Ligne \d : .*{message}"):
        Tilemap.from_text("#####\n#PTE#\n#####\n" + line + "\n")


def test_cameras_are_listed_on_the_map():
    tm = Tilemap.from_text("#####\n#PTE#\n#####\n@camera 1,0 -> S a 20\n@camera 3,0 -> S b\n")
    assert [(c.tile, c.group) for c in tm.cameras] == [((1, 0), "a"), ((3, 0), "b")]


# --- La caméra ------------------------------------------------------------------------------------------------------------------------
class Target:
    def __init__(self, pos, detectability=1.0):
        self.pos, self.detectability = V(pos), detectability


def make_camera(facing="S", **kw):
    tm = Tilemap.from_text(ROOM)
    spec = CameraSpec((10, 0), facing, "a", kw.get("sweep", 0.0))
    return tm, SecurityCamera(spec, 32)


def test_the_camera_looks_from_just_in_front_of_its_wall():
    tm, camera = make_camera("S")
    assert camera.mount == tile_center(10, 0) and camera.pos.y > camera.mount.y and camera.pos.x == camera.mount.x
    assert not tm.is_solid(*tm.world_to_tile(*camera.pos))  # son œil n'est pas dans le mur : il voit


def test_the_camera_sweeps_around_its_axis_and_never_beyond():
    tm, camera = make_camera("S", sweep=42.0)
    angles = []
    for _ in range(int(CAMERA_SWEEP_PERIOD * 60 * 2)):
        camera.update(1 / 60, tm, None)
        angles.append(camera.angle)
    assert max(angles) - camera.base_angle == pytest.approx(CAMERA_SWEEP, abs=0.03)
    assert camera.base_angle - min(angles) == pytest.approx(CAMERA_SWEEP, abs=0.03)
    assert len({round(a, 2) for a in angles}) > 20  # elle balaie vraiment


def test_a_camera_with_no_sweep_stays_put():
    tm, camera = make_camera("S", sweep=0.0)
    for _ in range(120):
        camera.update(1 / 60, tm, None)
    assert camera.angle == camera.base_angle


def test_the_camera_sees_only_inside_its_cone_and_range():
    tm, camera = make_camera("S")
    camera.update(0.0, tm, None)
    front = camera.pos + V(0, 100)
    assert camera.update(0.1, tm, Target(front)) is False and camera.sees_target
    side = camera.pos + V(200, 20)  # hors du cône
    camera.update(0.1, tm, Target(side))
    assert not camera.sees_target
    far = camera.pos + V(0, CAMERA_RANGE + 60)
    camera.update(0.1, tm, Target(far))
    assert not camera.sees_target


def test_awareness_rises_while_seen_then_the_camera_spots_the_player():
    tm, camera = make_camera("S")
    target = Target(camera.pos + V(0, 120))
    spotted_at = None
    for i in range(300):
        if camera.update(1 / 60, tm, target):
            spotted_at = i / 60
            break
    assert spotted_at is not None and 0.2 < spotted_at < 1.5 and camera.awareness == 1.0 and camera.alarmed


def test_awareness_fades_when_the_player_leaves_the_cone():
    tm, camera = make_camera("S")
    camera.update(1 / 60, tm, Target(camera.pos + V(0, 120)))
    seen = camera.awareness
    for _ in range(30):
        camera.update(1 / 60, tm, Target(camera.pos + V(300, 20)))
    assert 0 <= camera.awareness < seen


def test_a_camera_does_not_look_through_walls():
    tm = Tilemap.from_text("#" * 22 + "\n#" + "." * 20 + "#\n#" + "." * 9 + "#" + "." * 10 + "#\n#" + "." * 20 + "#\n" + "#" * 22 + "\n")
    camera = SecurityCamera(CameraSpec((10, 0), "S", "a", 0.0), 32)
    camera.update(0.1, tm, Target(tile_center(10, 3)))  # le pilier (10, 2) cache le joueur
    assert not camera.sees_target


def test_a_camera_spots_again_while_the_player_stays_in_view():
    tm, camera = make_camera("S")
    target = Target(camera.pos + V(0, 100))
    events = sum(camera.update(1 / 60, tm, target) for _ in range(int((CAMERA_ALARM_TIME * 2 + 3) * 60)))
    assert events >= 2


def test_light_and_stance_change_how_fast_a_camera_notices():
    def time_to_spot(detectability):
        tm, camera = make_camera("S")
        target = Target(camera.pos + V(0, 120), detectability)
        for i in range(60 * 30):
            if camera.update(1 / 60, tm, target):
                return i / 60
        return math.inf

    assert time_to_spot(0.5) > 1.8 * time_to_spot(1.0) > 0 and time_to_spot(1.5) < time_to_spot(1.0)


def test_a_disabled_camera_sees_nothing_and_recovers():
    tm, camera = make_camera("S")
    target = Target(camera.pos + V(0, 100))
    camera.update(0.5, tm, target)
    assert camera.awareness > 0
    camera.disable(CAMERA_OFF_TIME)
    assert not camera.active and camera.awareness == 0 and not camera.alarmed
    assert camera.update(1.0, tm, target) is False and not camera.sees_target
    for _ in range(int(CAMERA_OFF_TIME)):
        camera.update(1.0, tm, target)
    assert camera.active


def test_disabling_never_shortens_a_longer_shutdown():
    _, camera = make_camera("S")
    camera.disable(50)
    camera.disable(10)
    assert camera.off_left == 50


def test_a_camera_is_drawn_active_alarmed_and_off():
    tm, camera = make_camera("S")
    surface = pygame.Surface((400, 300))
    view = Camera(400, 300, 800, 600)
    images = []
    for state in ("on", "alarm", "off"):
        if state == "alarm":
            camera.alarm_left = 3
        if state == "off":
            camera.alarm_left = 0
            camera.disable(10)
        surface.fill((20, 20, 20))
        camera.draw(surface, view, 0.0)
        images.append(pygame.image.tobytes(surface, "RGB"))
    assert len(set(images)) == 3


# --- Dans la scène -------------------------------------------------------------------------------------------------------------------------
@pytest.fixture
def cruiser(game, monkeypatch):
    holder = {"input": InputState()}
    monkeypatch.setattr(play_scene, "read_input", lambda: holder["input"])
    scene = play_scene.PlayScene(game, CRUISER)
    game.scenes.push(scene)
    scene.guards.clear()
    scene.holder = holder
    return scene


def utility_terminal(scene):
    return next(t for t in scene.terminals if not t.spec.can(DATA))


def data_terminal(scene):
    return next(t for t in scene.terminals if t.spec.can(DATA))


def stand_by(scene, terminal, dx=-24):
    scene.player.pos.update(terminal.pos.x + dx, terminal.pos.y)


def open_menu(scene):
    scene.handle_event(KEY_E)
    scene.update(1 / 60)
    scene.update(1 / 60)
    return scene.game.scenes.current


def test_the_cruiser_has_cameras_and_two_terminals(cruiser):
    assert len(cruiser.cameras) == 3 and len(cruiser.terminals) == 2
    assert [c.group for c in cruiser.cameras] == ["a", "a", "b"]


def test_using_a_terminal_pauses_the_game_and_opens_its_menu(cruiser, game):
    stand_by(cruiser, utility_terminal(cruiser))
    menu = open_menu(cruiser)
    assert type(menu).__name__ == "TerminalScene" and game.scenes.current is menu
    assert [a[0] for a in menu.actions] == [CAMERAS, LIGHTS]
    assert [item.label for item in menu.menu.items] == ["Désactiver les caméras", "Couper la lumière de la salle", "Fermer"]
    assert game.audio.ducked  # le jeu est en pause : la scène de jeu n'est plus mise à jour tant que le menu est ouvert


def test_the_menu_only_offers_what_the_map_allowed(cruiser):
    stand_by(cruiser, data_terminal(cruiser), -20)
    menu = open_menu(cruiser)
    assert [a[0] for a in menu.actions] == [DATA] and [i.label for i in menu.menu.items] == ["Télécharger les données", "Fermer"]


def test_closing_the_menu_does_nothing(cruiser, game):
    stand_by(cruiser, utility_terminal(cruiser))
    menu = open_menu(cruiser)
    menu.menu.select(len(menu.menu.items) - 1)
    menu.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    assert game.scenes.current is cruiser and utility_terminal(cruiser).job is None and not game.audio.ducked
    menu = open_menu(cruiser)
    menu.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    assert game.scenes.current is cruiser and not cruiser.lights_out and all(c.active for c in cruiser.cameras)


def test_choosing_an_action_starts_a_connection_not_an_instant_effect(cruiser, game):
    terminal = utility_terminal(cruiser)
    stand_by(cruiser, terminal)
    menu = open_menu(cruiser)
    assert menu.choose(CAMERAS) and game.scenes.current is cruiser
    assert terminal.job.action == CAMERAS and all(c.active for c in cruiser.cameras)  # pas encore : il faut attendre la connexion
    assert terminal.prompt(cruiser.inventory) is None  # et on ne peut pas rouvrir le menu pendant ce temps


def test_the_menu_refuses_actions_the_terminal_cannot_do(cruiser):
    stand_by(cruiser, data_terminal(cruiser), -20)
    menu = open_menu(cruiser)
    assert not menu.choose(LIGHTS) and not menu.choose(CAMERAS)


def update(scene, seconds):
    for _ in range(int(seconds * 60)):
        scene.update(1 / 60)


def test_the_cameras_go_down_after_the_connection(cruiser):
    terminal = utility_terminal(cruiser)
    stand_by(cruiser, terminal)
    open_menu(cruiser).choose(CAMERAS)
    update(cruiser, TERMINAL_JOB_TIME[CAMERAS] * 0.5)
    assert all(c.active for c in cruiser.cameras) and 0 < cruiser.hack_progress < 1
    update(cruiser, TERMINAL_JOB_TIME[CAMERAS] * 0.7)
    assert all(not c.active for c in cruiser.cameras) and terminal.job is None
    assert any("Caméras désactivées" in t[0] for t in cruiser.hud._toasts)


def test_only_the_cameras_of_the_commanded_groups_go_down(game, monkeypatch):
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState())
    text = "#########\n#P..T..E#\n#########\n@terminal 4,1 -> cameras:b\n@camera 2,0 -> S a\n@camera 6,0 -> S b\n"
    path = SANDBOX.parent / "_tmp_cameras.txt"
    path.write_text(text)
    try:
        scene = play_scene.PlayScene(game, path)
    finally:
        path.unlink()
    game.scenes.push(scene)
    scene.guards.clear()
    stand_by(scene, scene.terminals[0], -8)
    open_menu(scene).choose(CAMERAS)
    update(scene, 2.5)
    assert [c.active for c in scene.cameras] == [True, False]


def test_cameras_come_back_after_the_delay(cruiser):
    stand_by(cruiser, utility_terminal(cruiser))
    open_menu(cruiser).choose(CAMERAS)
    update(cruiser, 2.5)
    assert not cruiser.cameras[0].active
    for camera in cruiser.cameras:
        camera.off_left = 0.05
    update(cruiser, 0.2)
    assert all(c.active for c in cruiser.cameras)


def test_walking_away_cuts_the_connection(cruiser):
    terminal = utility_terminal(cruiser)
    stand_by(cruiser, terminal)
    open_menu(cruiser).choose(LIGHTS)
    update(cruiser, 0.4)
    cruiser.player.pos.update(terminal.pos.x - TERMINAL_LINK_RANGE - 40, terminal.pos.y)
    update(cruiser, 0.1)
    assert terminal.job is None and not cruiser.lights_out
    assert any("Connexion perdue" in t[0] for t in cruiser.hud._toasts)


def test_a_hack_for_data_works_through_the_menu(cruiser):
    terminal = data_terminal(cruiser)
    stand_by(cruiser, terminal, -20)
    open_menu(cruiser).choose(DATA)
    update(cruiser, TERMINAL_JOB_TIME[DATA] + 0.3)
    assert terminal.hacked and cruiser.objective_done


def test_the_menu_announces_what_is_already_done(cruiser):
    stand_by(cruiser, utility_terminal(cruiser))
    for camera in cruiser.cameras:
        camera.disable(30)
    menu = open_menu(cruiser)
    assert menu.actions[0][2] is False and "Déjà" in menu.actions[0][3]
    assert not menu.choose(CAMERAS)


# --- Lumière coupée --------------------------------------------------------------------------------------------------------------------------------
def test_cutting_the_lights_darkens_only_the_terminals_room(cruiser):
    terminal = utility_terminal(cruiser)
    room = cruiser._room_lamps(terminal)
    assert room and len(room) < len(cruiser.lighting.lamps) / 2  # une salle, pas tout le croiseur
    stand_by(cruiser, terminal)
    open_menu(cruiser).choose(LIGHTS)
    update(cruiser, TERMINAL_JOB_TIME[LIGHTS] + 0.2)
    assert set(cruiser.lights_out) == set(room) and all(0 < left <= LIGHTS_OUT_TIME for left in cruiser.lights_out.values())


def test_the_lamps_fade_out_then_come_back(cruiser):
    stand_by(cruiser, utility_terminal(cruiser))
    open_menu(cruiser).choose(LIGHTS)
    update(cruiser, TERMINAL_JOB_TIME[LIGHTS] + LAMP_FADE_TIME + 0.5)
    room = next(iter(cruiser.lights_out))
    assert cruiser.lighting.lamp_level(room) < 0.05  # éteinte
    other = next(i for i in range(len(cruiser.lighting.lamps)) if i not in cruiser.lights_out)
    assert cruiser.lighting._lamp_levels[other] == 1.0
    for i in cruiser.lights_out:
        cruiser.lights_out[i] = 0.05
    update(cruiser, 0.2 + LAMP_FADE_TIME + 0.1)
    assert not cruiser.lights_out and cruiser.lighting._lamp_levels[room] == 1.0


def test_the_lights_are_out_for_a_limited_time(cruiser):
    stand_by(cruiser, utility_terminal(cruiser))
    open_menu(cruiser).choose(LIGHTS)
    update(cruiser, TERMINAL_JOB_TIME[LIGHTS] + 0.2)
    update(cruiser, LIGHTS_OUT_TIME + 1)
    assert not cruiser.lights_out


def test_cutting_the_lights_makes_noise_and_the_menu_says_when_it_is_done(cruiser, game):
    heard = []
    game.events.subscribe("noise", lambda pos, radius: heard.append(radius))
    stand_by(cruiser, utility_terminal(cruiser))
    open_menu(cruiser).choose(LIGHTS)
    update(cruiser, TERMINAL_JOB_TIME[LIGHTS] + 0.2)
    assert heard and max(heard) >= 170
    menu = open_menu(cruiser)
    assert menu.actions[1][2] is False and "noir" in menu.actions[1][3]


def test_a_dark_room_has_no_lamp_hum_and_no_floating_dust(cruiser):
    terminal = utility_terminal(cruiser)
    lamp = next(s for s in cruiser.ambience.sources if s.kind == "lamp" and s.pos.distance_to(terminal.pos) < 260)
    assert lamp.active()
    stand_by(cruiser, terminal)
    open_menu(cruiser).choose(LIGHTS)
    update(cruiser, TERMINAL_JOB_TIME[LIGHTS] + 0.2)
    assert not lamp.active()


# --- L'éclairage influence la détection (B5) ----------------------------------------------------------------------------------------------------
def test_light_falls_off_with_distance_like_the_rendering():
    assert falloff(0, 100) == 1.0 and falloff(100, 100) == 0.0 and falloff(150, 100) == 0.0
    assert 0 < falloff(50, 100) < falloff(20, 100) < 1


def test_light_adds_up_over_the_ambient_and_is_blocked_by_walls():
    tm = Tilemap.from_text(ROOM)
    lamp = (tile_center(10, 3), LAMP_RADIUS, (255, 255, 255), 1.0)
    here = tile_center(10, 3)
    assert light_at(tm, here, 0.3, [lamp]) == 1.0  # sous la lampe : au maximum
    assert light_at(tm, here, 0.3, []) == 0.3
    near, far = light_at(tm, tile_center(12, 3), 0.3, [lamp]), light_at(tm, tile_center(15, 3), 0.3, [lamp])
    assert 0.3 < far < near <= 1.0
    walled = Tilemap.from_text("\n".join(["#" * 22] + ["#" + "." * 9 + "#" + "." * 10 + "#"] * 3 + ["#" * 22]))
    behind = light_at(walled, tile_center(12, 2), 0.3, [(tile_center(8, 2), LAMP_RADIUS, (255, 255, 255), 1.0)])
    assert behind == 0.3  # le mur arrête la lumière


def test_a_dim_lamp_lights_less_than_a_bright_one():
    tm = Tilemap.from_text(ROOM)
    pos = tile_center(10, 3)
    bright = light_at(tm, pos + V(30, 0), 0.2, [(pos, LAMP_RADIUS, (255, 255, 255), 1.0)])
    dim = light_at(tm, pos + V(30, 0), 0.2, [(pos, LAMP_RADIUS, (255, 255, 255), 0.3)])
    colored = light_at(tm, pos + V(30, 0), 0.2, [(pos, LAMP_RADIUS, (255, 40, 40), 1.0)])
    assert 0.2 < dim < colored < bright


def test_the_visibility_factor_runs_from_dark_to_bright():
    dark, bright = VISIBILITY_FACTORS
    assert visibility_factor(luminance(AMBIENT_BLACKOUT)) == pytest.approx(dark)
    assert visibility_factor(1.0) == pytest.approx(bright)
    values = [visibility_factor(x / 10) for x in range(11)]
    assert values == sorted(values) and values[0] <= dark + 0.01


def test_light_zones_are_named_for_the_hud():
    assert visibility_zone(0.5, 0.5) == SHADOW and visibility_zone(0.1, 0.5) == SHADOW  # rien n'éclaire : dans l'ombre
    assert visibility_zone(0.6, 0.5) == DIM and visibility_zone(0.9, 0.5) == LIT
    assert visibility_zone(0.6, 0.3) == LIT  # la même lumière compte plus dans une carte sombre


def test_the_player_is_less_detectable_in_the_dark():
    from game.entities.player import Player

    player = Player(0, 0)
    assert player.light_factor == 1.0
    base = player.detectability
    player.light_factor = visibility_factor(0.1)
    assert player.detectability < base < 1.5 * base
    player.light_factor = visibility_factor(1.0)
    assert player.detectability > base


def test_a_guard_notices_a_player_in_the_dark_more_slowly():
    from game.entities.player import Player

    tm = Tilemap.from_text(ROOM)

    def seconds_to_notice(light):
        guard = Guard.from_spawn(tm, type("S", (), {"kind": "guard", "tx": 10, "ty": 5, "level": 0})())
        player = Player(*(guard.pos + V(100, 0)))
        guard.angle = 0.0
        player.light_factor = visibility_factor(light)
        for i in range(60 * 20):
            guard.update(1 / 60, tm, player)
            if guard.state is GuardState.CHASE:
                return i / 60
        return math.inf

    assert seconds_to_notice(0.9) < seconds_to_notice(0.5) < seconds_to_notice(0.15)


def test_the_scene_measures_the_light_under_the_player(cruiser):
    update(cruiser, 0.2)
    assert 0 <= cruiser.player_light <= 1 and cruiser.player.light_factor == pytest.approx(visibility_factor(cruiser.player_light))
    assert cruiser.player_light >= cruiser.lighting.base_light()  # les lampes ne font qu'ajouter à l'ambiance


def test_standing_under_a_lamp_is_brighter_than_in_a_corner(cruiser):
    lamp = cruiser.lighting.lamps[len(cruiser.lighting.lamps) // 2]
    cruiser.player.pos.update(lamp.position(32))
    update(cruiser, 0.1)
    under = cruiser.player_light
    corner = next(
        tile_center(x, y)
        for y in range(3, 47)
        for x in range(3, 70)
        if not cruiser.tilemap.is_solid(x, y) and all(tile_center(x, y).distance_to(l.position(32)) > LAMP_RADIUS for l in cruiser.lighting.lamps)
    )
    cruiser.player.pos.update(corner)
    update(cruiser, 0.1)
    assert cruiser.player_light < under and cruiser.player.light_factor < visibility_factor(under)


def test_the_hud_says_shadow_in_a_room_whose_light_was_cut(cruiser):
    from game.world.exposure import SHADOW as shadow

    terminal = utility_terminal(cruiser)
    lamp = cruiser.lighting.lamps[cruiser._room_lamps(terminal)[0]]
    stand_by(cruiser, terminal)
    open_menu(cruiser).choose(LIGHTS)
    update(cruiser, TERMINAL_JOB_TIME[LIGHTS] + LAMP_FADE_TIME + 1)
    cruiser.player.pos.update(lamp.position(32))
    update(cruiser, 0.1)
    assert visibility_zone(cruiser.player_light, cruiser.lighting.base_light()) == shadow


def test_cutting_the_lights_makes_the_room_a_hiding_place(cruiser):
    terminal = utility_terminal(cruiser)
    lamp = cruiser.lighting.lamps[cruiser._room_lamps(terminal)[0]]
    cruiser.player.pos.update(lamp.position(32))
    update(cruiser, 0.1)
    before = cruiser.player.light_factor  # sous une lampe de la salle
    stand_by(cruiser, terminal)
    open_menu(cruiser).choose(LIGHTS)
    update(cruiser, TERMINAL_JOB_TIME[LIGHTS] + LAMP_FADE_TIME + 1)
    cruiser.player.pos.update(lamp.position(32))
    update(cruiser, 0.1)
    assert cruiser.player.light_factor < before - 0.15  # au même endroit, on se repère nettement moins bien


def test_a_power_cut_makes_the_whole_level_dark_for_detection(game, monkeypatch):
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState())
    scene = play_scene.PlayScene(game, BLACKOUT, CAMPAIGN.get("blackout"))
    game.scenes.push(scene)
    scene.guards.clear()
    update(scene, 0.2)
    lit = scene.player.light_factor
    scene.consoles[0].cut = True
    update(scene, 3.0)
    assert scene.player.light_factor <= lit and scene.player_light == pytest.approx(luminance(AMBIENT_BLACKOUT), abs=0.12)


def test_a_flickering_lamp_opens_a_window(cruiser):
    flicker = next(i for i, lamp in enumerate(cruiser.lighting.lamps) if lamp.flickers)
    levels = []
    for _ in range(60 * 40):
        cruiser.lighting.update(1 / 60, False)
        levels.append(cruiser.lighting.lamp_level(flicker))
    assert min(levels) < 0.4 < 0.9 < max(levels)  # par moments presque éteinte : une fenêtre pour passer


def test_the_hud_tells_the_player_how_visible_they_are(cruiser):
    from game.ui.hud import VISIBILITY_LABELS

    assert {"shadow", "dim", "lit"} == set(VISIBILITY_LABELS)
    surface = pygame.Surface((1280, 720))
    surface.fill((0, 0, 0))
    cruiser.draw(surface)
    top_left = surface.subsurface(pygame.Rect(0, 36, 260, 24))
    assert pygame.mask.from_threshold(top_left, (0, 0, 0), (1, 1, 1, 255)).count() < 260 * 24  # la ligne « Visibilité » est là


# --- Cameras dans la scène ------------------------------------------------------------------------------------------------------------------------
def watch(scene, camera, distance=100):
    """Place le joueur dans le champ d'une caméra, face à elle."""
    camera.base_angle = camera.angle
    scene.player.pos.update(camera.pos + V(math.cos(camera.angle), math.sin(camera.angle)) * distance)


def test_a_spotting_camera_warns_the_nearest_guards_and_the_player(cruiser, game):
    camera = cruiser.cameras[0]  # dans la coursive, où patrouille le garde de la rangée 22
    camera.sweep = 0.0
    neighbour = next(s for s in cruiser.tilemap.spawns_of("guard") if (s.tx, s.ty) == (4, 22))
    guard = Guard.from_spawn(cruiser.tilemap, neighbour)
    cruiser.guards.append(guard)
    watch(cruiser, camera, 40)  # la coursive ne fait que deux tuiles de large
    spotted = []
    game.events.subscribe("camera_spotted", lambda pos, camera: spotted.append(pos))
    update(cruiser, 2.5)
    assert spotted and any("caméra" in t[0] for t in cruiser.hud._toasts)
    assert guard.state in (GuardState.INVESTIGATE, GuardState.SEARCH)  # il vient voir sur place
    assert guard.destination is not None and guard.destination.distance_to(spotted[0]) < 64


def test_at_most_a_few_guards_answer_a_camera(cruiser):
    camera = cruiser.cameras[0]
    guards = [Guard.from_spawn(cruiser.tilemap, s) for s in cruiser.tilemap.spawns_of("guard") if s.ty in (22, 23)]
    cruiser.guards.extend(guards)
    assert len(guards) >= 3
    cruiser.game.events.emit("camera_spotted", pos=V(camera.pos + V(0, 90)), camera=camera)
    answering = [g for g in guards if g.state is GuardState.INVESTIGATE]
    assert 1 <= len(answering) <= CAMERA_RESPONDERS


def test_a_camera_that_starts_to_notice_makes_the_player_suspect(cruiser):
    camera = cruiser.cameras[0]
    camera.sweep = 0.0
    assert cruiser.threat is GuardState.PATROL
    camera.awareness = 0.5
    assert cruiser.threat is GuardState.INVESTIGATE  # pastille « SUSPECT » même sans garde en vue
    camera.awareness = 0.1
    assert cruiser.threat is GuardState.PATROL


def test_cameras_do_nothing_after_the_mission_ends(cruiser):
    camera = cruiser.cameras[0]
    camera.sweep = 0.0
    watch(cruiser, camera, 40)
    cruiser.caught = True
    update(cruiser, 2.0)
    assert camera.awareness == 0


def test_a_restart_brings_the_cameras_and_the_light_back(cruiser):
    cruiser.cameras[0].disable(30)
    cruiser.lights_out[3] = 10
    cruiser.restart()
    assert all(c.active for c in cruiser.cameras) and cruiser.lights_out == {} and all(t.job is None for t in cruiser.terminals)


def test_the_scene_draws_cameras_and_their_cones(cruiser, game):
    camera = cruiser.cameras[0]
    cruiser.player.pos.update(camera.pos + V(0, 90))
    cruiser.camera.snap_to(cruiser.player.pos)
    for _ in range(30):
        game.step(1 / 60)
    surface = pygame.Surface((1280, 720))
    cruiser.draw(surface)
    camera.disable(10)
    cruiser.draw(surface)


# --- Cartes livrées ------------------------------------------------------------------------------------------------------------------------------
def test_the_cruiser_terminal_of_the_barracks_serves_cameras_and_lights():
    tm = Tilemap.from_file(CRUISER)
    spec = tm.terminal_spec((43, 16))
    assert spec.capabilities == (CAMERAS, LIGHTS) and tm.terminal_spec((65, 4)).capabilities == (DATA,)
    assert check_level(tm) == []


def test_the_training_terminal_is_a_plain_data_terminal():
    tm = Tilemap.from_file(TRAINING)
    assert tm.terminal_specs == {} and tm.cameras == []
    assert tm.terminal_spec((45, 2)).capabilities == (DATA,)


def test_every_shipped_camera_watches_a_passage():
    for mission in CAMPAIGN.missions:
        tm = Tilemap.from_file(mission.map_path)
        for spec in tm.cameras:
            assert tm.tile_at(*spec.tile) == tm.tile_at(0, 0)  # un mur
            dx, dy = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "O": (-1, 0)}[spec.facing]
            assert not tm.is_solid(spec.tile[0] + dx, spec.tile[1] + dy)


def test_the_virtual_player_completes_the_cruiser_through_the_menu(game, monkeypatch):
    from game.items import ItemKind

    scene = play_scene.PlayScene(game, CRUISER)
    game.scenes.push(scene)
    scene.guards.clear()
    runner = Runner(game, scene, monkeypatch)
    tm = scene.tilemap
    for level in (1, 2, 3):
        card = next(s for s in tm.spawns_of("keycard") if s.level == level)
        runner.go((card.tx, card.ty))
    runner.use_terminal(CAMERAS, tile=(43, 16))  # un détour utile : on coupe les caméras
    assert all(not c.active for c in scene.cameras)
    runner.press("3")
    runner.use_terminal()
    assert scene.inventory.count_kind(ItemKind.DATA) == 1
    exit_ = tm.spawns_of("exit")[0]
    runner.go((exit_.tx, exit_.ty))
    scene.handle_event(KEY_E)
    runner.frames(2)
    assert scene.won
