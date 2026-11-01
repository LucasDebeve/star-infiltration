"""Uniforme impérial : casier à fouiller (objectif), enfiler l'uniforme, porte du personnel et détection en déguisement."""

import pygame
import pytest

from game.ai.guard import Guard, GuardState
from game.core import bindings
from game.core.input import InputState
from game.entities.door import build_doors
from game.entities.locker import Locker
from game.entities.player import Player, Stance
from game.items import Inventory, Item, ItemKind
from game.objectives import OBJECTIVES, STEAL_PLANS, STEAL_UNIFORM, infer_objective, objective_spawns
from game.scenes import play_scene
from game.settings import DISGUISE_CLOSE_FACTOR, DISGUISE_RANGE, LOCKER_NOISE, LOCKER_TIME, PLAYER_DETECTABILITY
from game.systems.interaction import InteractionContext
from game.ui import sprites
from game.world.level_check import check_level, explore, route_distances
from game.world.tilemap import Tilemap

V = pygame.Vector2
UNIFORM = Item(ItemKind.UNIFORM)
# Départ à gauche, casier à droite derrière un couloir ; la sortie est tout près du départ.
LOCKER_MAP = "#########\n#P.....U#\n#E......#\n#########\n"
# Les plans (T) ne sont accessibles que par la porte du personnel (D) : l'uniforme (U) est dans le premier salon.
STAFF_MAP = "###########\n#P..U#..T.#\n#....D....#\n#E...#....#\n###########\n@door 5,2 -> uniform\n"


def tile_center(x, y):
    return V((x + 0.5) * 32, (y + 0.5) * 32)


def make_scene(game, monkeypatch, tmp_path, text):
    path = tmp_path / "m.txt"
    path.write_text(text)
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState())
    scene = play_scene.PlayScene(game, path)
    game.scenes.push(scene)
    return scene


def ctx(tm=None, inventory=None):
    class Events:
        def __init__(self):
            self.log = []

        def emit(self, name, **payload):
            self.log.append((name, payload))

    events = Events()
    return InteractionContext(tm, inventory or Inventory(), events), events


# --- Objet et inventaire ---------------------------------------------------------------------------------------------------------
def test_the_uniform_is_worn_only_after_it_is_stolen():
    inv = Inventory()
    assert not inv.has_uniform and inv.toggle_uniform() is False  # rien à enfiler
    inv.add(UNIFORM)
    assert inv.has_uniform and not inv.uniform_worn
    assert inv.toggle_uniform() is True and inv.uniform_worn
    assert inv.toggle_uniform() is False and not inv.uniform_worn


def test_the_uniform_has_labels_and_an_icon():
    assert UNIFORM.label == "Uniforme impérial" and UNIFORM.short_label == "Uniforme"
    surface = pygame.Surface((32, 32), pygame.SRCALPHA)
    from game.ui.icons import draw_item_icon

    draw_item_icon(surface, UNIFORM, (16, 16), 22)
    assert pygame.mask.from_surface(surface).count() > 80


# --- Objectif ----------------------------------------------------------------------------------------------------------------------
def test_stealing_a_uniform_is_a_playable_objective_found_from_the_locker():
    assert OBJECTIVES["steal_uniform"] is STEAL_UNIFORM and STEAL_UNIFORM.playable
    tm = Tilemap.from_text(LOCKER_MAP)
    assert infer_objective(tm) is STEAL_UNIFORM
    assert [(s.tx, s.ty) for s in objective_spawns(tm, STEAL_UNIFORM)] == [(7, 1)]
    assert check_level(tm) == [] and explore(tm).can_finish


def test_a_terminal_still_wins_over_a_locker_for_the_objective():
    assert infer_objective(Tilemap.from_text(STAFF_MAP)) is STEAL_PLANS


def test_the_objective_is_done_when_the_uniform_is_in_the_bag(game, monkeypatch, tmp_path):
    scene = make_scene(game, monkeypatch, tmp_path, LOCKER_MAP)
    assert scene.goal is STEAL_UNIFORM and not scene.objective_done and not scene.exit_ready
    scene.inventory.add(UNIFORM)
    assert scene.objective_done


# --- Casier --------------------------------------------------------------------------------------------------------------------------
def test_a_locker_gives_the_uniform_once_and_makes_noise():
    locker = Locker(100, 100)
    inventory = Inventory()
    assert locker.prompt(inventory) is not None and locker.hold_time == LOCKER_TIME
    context, events = ctx(inventory=inventory)
    locker.interact(context)
    assert inventory.has_uniform and locker.taken and locker.prompt(inventory) is None
    names = [name for name, _ in events.log]
    assert {"item_picked", "uniform_stolen", "noise"} <= set(names)
    assert dict(events.log)["noise"]["radius"] == LOCKER_NOISE


def test_searching_a_locker_takes_time_in_the_game(game, monkeypatch, tmp_path):
    scene = make_scene(game, monkeypatch, tmp_path, LOCKER_MAP)
    scene.guards.clear()
    scene.player.pos = tile_center(7, 1)
    pressed = {"on": True}
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState(interact=pressed["on"]))
    for _ in range(int(LOCKER_TIME * 60 / 2)):
        scene.update(1 / 60)
    assert not scene.inventory.has_uniform  # trop tôt
    for _ in range(int(LOCKER_TIME * 60)):
        scene.update(1 / 60)
    assert scene.inventory.has_uniform and scene.lockers[0].taken


def test_the_locker_is_drawn_both_closed_and_taken():
    from game.core.camera import Camera

    camera = Camera(320, 240, 320, 240)
    shots = []
    for taken in (False, True):
        surface = pygame.Surface((320, 240))
        locker = Locker(160, 120)
        locker.taken = taken
        locker.draw(surface, camera, 0.0)
        shots.append(pygame.image.tostring(surface, "RGB"))
    assert shots[0] != shots[1]


# --- Enfiler l'uniforme ------------------------------------------------------------------------------------------------------------
def press_disguise(scene):
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=bindings.current.keys("disguise")[0]))


def test_the_disguise_key_is_a_rebindable_action_on_u_and_lb():
    assert "disguise" in bindings.ACTIONS and bindings.current.keys("disguise") == (pygame.K_u,)
    assert bindings.label("disguise") == "U"


def test_the_player_puts_on_and_takes_off_the_uniform(game, monkeypatch, tmp_path):
    scene = make_scene(game, monkeypatch, tmp_path, LOCKER_MAP)
    scene.guards.clear()
    press_disguise(scene)
    assert not scene.inventory.uniform_worn and scene.disguise_state is None  # pas d'uniforme : rien ne se passe
    scene.inventory.add(UNIFORM)
    assert scene.disguise_state == "stowed"
    press_disguise(scene)
    scene.update(1 / 60)
    assert scene.disguise_state == "worn" and scene.player.disguised
    press_disguise(scene)
    scene.update(1 / 60)
    assert scene.disguise_state == "stowed" and not scene.player.disguised


def test_the_general_alert_blows_the_cover(game, monkeypatch, tmp_path):
    scene = make_scene(game, monkeypatch, tmp_path, LOCKER_MAP)
    scene.guards.clear()
    scene.inventory.add(UNIFORM)
    press_disguise(scene)
    scene.update(1 / 60)
    assert scene.player.disguised
    scene.alert.active = True
    scene.update(1 / 60)
    assert scene.disguise_state == "blown" and not scene.player.disguised


def test_a_disguised_player_walking_makes_no_footstep_noise(game, monkeypatch, tmp_path):
    scene = make_scene(game, monkeypatch, tmp_path, LOCKER_MAP)
    scene.guards.clear()
    heard = []
    game.events.subscribe("noise", lambda **kw: heard.append(kw))
    scene.inventory.add(UNIFORM)
    press_disguise(scene)
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState(move=V(1, 0)))
    for _ in range(90):
        scene.update(1 / 60)
    assert scene.player.disguised and not heard


# --- Détection en déguisement --------------------------------------------------------------------------------------------------------
def disguised_player(stance=Stance.WALK):
    player = Player(100, 100)
    player.disguised = True
    player.stance = stance
    return player


def test_without_the_uniform_nothing_changes():
    player = Player(100, 100)
    player.stance = Stance.WALK
    assert player.detectability_at(10) == player.detectability_at(1000) == PLAYER_DETECTABILITY["walk"]
    assert player.heard_radius == player.noise_radius


def test_a_disguised_walker_is_ignored_from_afar_and_barely_noticed_up_close():
    player = disguised_player()
    assert player.detectability_at(DISGUISE_RANGE + 1) == 0
    assert player.detectability_at(DISGUISE_RANGE - 1) == pytest.approx(PLAYER_DETECTABILITY["walk"] * DISGUISE_CLOSE_FACTOR)
    assert player.heard_radius == 0


def test_running_or_crouching_in_uniform_gives_the_player_away():
    run = disguised_player(Stance.RUN)
    assert run.detectability_at(500) == PLAYER_DETECTABILITY["run"] and run.heard_radius == run.noise_radius
    crouch = disguised_player(Stance.CROUCH)
    assert crouch.detectability_at(500) == PLAYER_DETECTABILITY["walk"]  # se tapir en uniforme est suspect : pas de bonus


HALL = Tilemap.from_text("#" * 16 + "\n#" + "." * 14 + "#\n#" + "." * 14 + "#\n" + "#" * 16)


def watch(player, tile):
    guard = Guard([tile_center(1, 1), tile_center(1, 2)], 0.0)
    player.pos = tile_center(*tile)
    for _ in range(120):
        guard.update(1 / 60, HALL, player)
    return guard


def test_a_guard_ignores_a_disguised_officer_in_plain_sight():
    guard = watch(disguised_player(), (8, 1))
    assert guard.state is GuardState.PATROL and guard.awareness == 0
    assert guard.pos != tile_center(1, 1)  # il n'est pas figé à fixer l'intrus : il continue sa ronde


def test_the_same_guard_spots_the_player_without_the_uniform():
    player = Player(0, 0)
    player.stance = Stance.WALK
    guard = watch(player, (8, 1))
    assert guard.state is not GuardState.PATROL or guard.awareness > 0


def test_a_security_camera_ignores_a_disguised_walker_from_afar():
    from game.entities.security_camera import SecurityCamera
    from game.world.surveillance import CameraSpec

    tm = Tilemap.from_text("#" * 16 + "\n#" + "." * 14 + "#\n#" + "." * 14 + "#\n" + "#" * 16)
    spec = CameraSpec(tile=(0, 1), facing="E", group="a", sweep=45)
    camera = SecurityCamera(spec, 32)
    player = disguised_player()
    player.pos = tile_center(10, 1)
    spotted = False
    for _ in range(240):
        spotted = camera.update(1 / 60, tm, player) or spotted
    assert not spotted


# --- Porte du personnel ----------------------------------------------------------------------------------------------------------------
def test_a_staff_door_is_declared_and_marked_in_the_map():
    tm = Tilemap.from_text(STAFF_MAP)
    assert tm.uniform_doors == {(5, 2)}
    door = build_doors(tm)[0]
    assert door.staff


def test_a_map_with_a_staff_door_but_no_locker_is_rejected():
    tm = Tilemap.from_text("###########\n#P...D..TE#\n###########\n@door 5,1 -> uniform\n")
    assert any("casier" in problem for problem in check_level(tm))


def test_the_staff_door_prompt_follows_what_the_player_wears():
    door = build_doors(Tilemap.from_text(STAFF_MAP))[0]
    inv = Inventory()
    prompt = door.prompt(inv)
    assert not prompt.enabled and "uniforme" in prompt.label.lower()
    inv.add(UNIFORM)
    prompt = door.prompt(inv)
    assert not prompt.enabled and "Enfilez" in prompt.label  # dans le sac : le lecteur ne le voit pas
    inv.toggle_uniform()
    assert door.prompt(inv).enabled


def test_a_keycard_never_opens_a_staff_door():
    door = build_doors(Tilemap.from_text(STAFF_MAP))[0]
    inv = Inventory()
    inv.add(Item(ItemKind.KEYCARD, 3))
    assert not door.prompt(inv).enabled


def test_the_staff_door_is_needed_to_finish_the_level():
    tm = Tilemap.from_text(STAFF_MAP)
    assert check_level(tm) == []
    assert explore(tm).can_finish and not explore(tm, allow_uniform=False).can_finish
    assert route_distances(tm)["to_goal"] > 0


def test_stealing_the_uniform_then_wearing_it_opens_the_staff_door_in_the_game(game, monkeypatch, tmp_path):
    scene = make_scene(game, monkeypatch, tmp_path, STAFF_MAP)
    scene.guards.clear()
    door = scene.doors[0]
    scene.player.pos = tile_center(6, 3)  # contre la porte, loin du casier
    scene.interaction.update(0.1, scene.player.pos, scene.tilemap, scene.inventory, scene.interactables, pressed=True, held=False)
    assert not door.is_open  # sans uniforme : refusé
    scene.inventory.add(UNIFORM)
    scene.inventory.toggle_uniform()
    scene.interaction.update(0.1, scene.player.pos, scene.tilemap, scene.inventory, scene.interactables, pressed=True, held=False)
    assert door.is_open


# --- Dessin ------------------------------------------------------------------------------------------------------------------------------
def test_the_disguised_agent_looks_different():
    shots = []
    for disguised in (False, True):
        surface = pygame.Surface((64, 64), pygame.SRCALPHA)
        sprites.draw_player(surface, (32, 32), V(1, 0), "walk", disguised=disguised)
        shots.append(pygame.image.tostring(surface, "RGBA"))
    assert shots[0] != shots[1]


def test_the_hud_shows_the_state_of_the_disguise(game, monkeypatch, tmp_path):
    scene = make_scene(game, monkeypatch, tmp_path, LOCKER_MAP)
    from game.ui.hud import DISGUISE_LABELS

    assert set(DISGUISE_LABELS) == {"worn", "blown", "stowed"}
    shots = {}
    for state in (None, "stowed", "worn", "blown"):
        surface = pygame.Surface(game.screen.get_size())
        scene.hud.draw(surface, fps=60, player=scene.player, tile=(1, 1), debug=False, inventory=scene.inventory, disguise=state)
        shots[state] = pygame.image.tostring(surface, "RGB")
    assert len(set(shots.values())) == 4
