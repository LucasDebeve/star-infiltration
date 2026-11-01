"""Objectifs de mission : vol de plans, coupure de l'alimentation, et le terrain préparé pour la libération de prisonnier."""

import json

import pygame
import pytest

from game.campaign import load_campaign
from game.core.events import EventBus
from game.core.input import InputState
from game.entities.exit_pad import ExitPad
from game.entities.power_console import PowerConsole
from game.items import Inventory, Item, ItemKind
from game.objectives import CUT_POWER, FREE_PRISONER, OBJECTIVES, STEAL_PLANS, get_objective, infer_objective
from game.scenes import play_scene
from game.settings import AMBIENT_BLACKOUT, MAPS_DIR, POWER_CUT_NOISE, POWER_CUT_TIME, POWER_FADE_TIME
from game.systems.interaction import InteractionContext, InteractionSystem
from game.ui.lighting import Lighting
from game.world.level_check import check_level, explore, route_distances
from game.world.tilemap import Tilemap
from tests.paths import BLACKOUT, CAMPAIGN, CRUISER, SANDBOX
from tests.runner import Runner

KEY_E = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_e)


# --- Le catalogue d'objectifs -----------------------------------------------------------------
def test_each_objective_has_its_texts_and_a_tile():
    for objective in OBJECTIVES.values():
        assert objective.tile and objective.goal and objective.done and objective.calm and objective.flee and objective.missing


def test_every_objective_is_playable_now():
    assert set(OBJECTIVES) == {"steal_plans", "cut_power", "free_prisoner", "steal_ship", "steal_uniform"}
    assert all(o.playable for o in OBJECTIVES.values())
    assert get_objective("cut_power") is CUT_POWER


def test_an_objective_is_inferred_from_the_points_of_the_map():
    assert infer_objective(Tilemap.from_file(CRUISER)) is STEAL_PLANS
    assert infer_objective(Tilemap.from_file(BLACKOUT)) is CUT_POWER
    assert infer_objective(Tilemap.from_text("####\n#PE#\n####")) is STEAL_PLANS  # défaut


def test_a_prisoner_makes_the_map_an_escape():
    tm = Tilemap.from_text("#####\n#PQE#\n#####")
    assert [(s.tx, s.ty) for s in tm.spawns_of("prisoner")] == [(2, 1)]
    assert not tm.is_solid(2, 1)
    assert infer_objective(tm) is FREE_PRISONER


# --- La console ---------------------------------------------------------------------------------
def test_the_console_cuts_the_power_after_a_hold_and_makes_noise():
    events, heard, cut = EventBus(), [], []
    events.subscribe("noise", lambda **p: heard.append(p))
    events.subscribe("power_cut", lambda **p: cut.append(p))
    console = PowerConsole(100, 100)
    assert console.hold_time == POWER_CUT_TIME and console.prompt(Inventory()).enabled
    console.interact(InteractionContext(None, Inventory(), events))
    assert console.cut and cut[0]["console"] is console
    assert heard[0]["radius"] == POWER_CUT_NOISE and heard[0]["pos"] == pygame.Vector2(100, 100)
    assert console.prompt(Inventory()) is None  # une seule fois


def test_holding_e_on_the_console_cuts_it_but_releasing_early_does_not():
    events = EventBus()
    system = InteractionSystem(events)
    console = PowerConsole(100, 100)
    ctx = dict(tilemap=None, inventory=Inventory(), interactables=[console])
    for _ in range(int(POWER_CUT_TIME * 60 * 0.5)):
        system.update(1 / 60, pygame.Vector2(100, 100), ctx["tilemap"], ctx["inventory"], ctx["interactables"], pressed=False, held=True)
    system.update(1 / 60, pygame.Vector2(100, 100), None, Inventory(), [console], pressed=False, held=False)
    assert not console.cut
    for _ in range(int(POWER_CUT_TIME * 60) + 5):
        system.update(1 / 60, pygame.Vector2(100, 100), None, Inventory(), [console], pressed=False, held=True)
    assert console.cut


def test_the_console_is_drawn_live_cutting_and_dead(game):
    from game.core.camera import Camera

    camera = Camera(200, 200, 400, 400)
    surface = pygame.Surface((200, 200))
    console = PowerConsole(100, 100)
    images = []
    for progress in (0.0, 0.7):
        surface.fill((0, 0, 0))
        console.draw(surface, camera, progress)
        images.append(pygame.image.tobytes(surface, "RGB"))
    console.cut = True
    surface.fill((0, 0, 0))
    console.draw(surface, camera)
    images.append(pygame.image.tobytes(surface, "RGB"))
    assert len(set(images)) == 3


# --- La sortie suit l'objectif ----------------------------------------------------------------------
def test_the_exit_follows_the_given_rule_and_names_what_is_missing():
    done = []
    pad = ExitPad(0, 0, ready=lambda inventory: bool(done), missing="Alimentation active")
    assert not pad.is_ready(Inventory()) and pad.prompt(Inventory()).label == "Alimentation active"
    assert not pad.prompt(Inventory()).enabled
    done.append(1)
    assert pad.is_ready(Inventory()) and pad.prompt(Inventory()).enabled


def test_the_default_exit_still_asks_for_the_data():
    pad = ExitPad(0, 0)
    inventory = Inventory()
    assert not pad.is_ready(inventory) and pad.prompt(inventory).label == "Données requises"
    inventory.add(Item(ItemKind.DATA))
    assert pad.is_ready(inventory)


# --- La scène -------------------------------------------------------------------------------------
@pytest.fixture
def blackout(game, monkeypatch):
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState())
    scene = play_scene.PlayScene(game, BLACKOUT, CAMPAIGN.get("blackout"))
    game.scenes.push(scene)
    return scene


def test_the_blackout_scene_loads_a_console_and_no_terminal(blackout):
    assert blackout.goal is CUT_POWER and len(blackout.consoles) == 1 and blackout.terminals == []
    assert blackout.objective == CUT_POWER.goal and blackout.power_on and not blackout.objective_done
    assert blackout.consoles[0] in blackout.interactables


def test_the_exit_is_locked_until_the_power_is_cut(blackout):
    exit_pad = blackout.exit_pad
    assert not exit_pad.is_ready(blackout.inventory)
    blackout.inventory.add(Item(ItemKind.DATA))  # des données ne suffisent pas ici
    assert not exit_pad.is_ready(blackout.inventory) and not blackout.objective_done
    blackout.consoles[0].interact(InteractionContext(blackout.tilemap, blackout.inventory, blackout.game.events))
    assert exit_pad.is_ready(blackout.inventory) and blackout.objective_done and not blackout.power_on
    assert blackout.objective == CUT_POWER.calm


def test_cutting_the_power_notifies_the_player(blackout):
    blackout.consoles[0].interact(InteractionContext(blackout.tilemap, blackout.inventory, blackout.game.events))
    assert any(toast[0] == CUT_POWER.done for toast in blackout.hud._toasts)


def test_cutting_the_power_makes_a_nearby_guard_investigate(blackout):
    console = blackout.consoles[0]
    guard = blackout.guards[0]
    start = pygame.Vector2(console.pos.x - 96, console.pos.y)
    blackout.guards[:] = [guard]
    guard.pos.update(start)
    assert guard.state.name == "PATROL"
    blackout.consoles[0].interact(InteractionContext(blackout.tilemap, blackout.inventory, blackout.game.events))
    assert guard.state.name == "INVESTIGATE" and guard.destination.distance_to(console.pos) < 40


def test_the_objective_text_while_fleeing_depends_on_the_alert(blackout):
    blackout.consoles[0].cut = True
    assert blackout.objective == CUT_POWER.calm
    blackout.alert.active = True
    assert blackout.objective == CUT_POWER.flee


def test_a_restart_turns_the_power_back_on(blackout):
    blackout.consoles[0].cut = True
    blackout.restart()
    assert blackout.power_on and not blackout.consoles[0].cut


def test_a_cruiser_scene_has_no_console(game, monkeypatch):
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState())
    scene = play_scene.PlayScene(game, CRUISER, CAMPAIGN.get("cruiser"))
    assert scene.goal is STEAL_PLANS and scene.consoles == [] and scene.power_on


def test_a_scene_without_mission_infers_its_objective(game):
    assert play_scene.PlayScene(game, BLACKOUT).goal is CUT_POWER
    assert play_scene.PlayScene(game, SANDBOX).goal is STEAL_PLANS


# --- La lumière -----------------------------------------------------------------------------------------
def test_the_ambient_light_fades_to_the_blackout_color():
    tm = Tilemap.from_file(BLACKOUT)
    lighting = Lighting(tm)
    assert lighting.ambient() == tm.theme.ambient
    lighting.update(POWER_FADE_TIME / 2, False, power=False)
    middle = lighting.ambient()
    assert all(b < m < a for a, m, b in zip(tm.theme.ambient, middle, AMBIENT_BLACKOUT))
    lighting.update(POWER_FADE_TIME, False, power=False)
    assert lighting.ambient() == AMBIENT_BLACKOUT
    lighting.update(POWER_FADE_TIME * 2, False, power=True)  # le courant revient (redémarrage)
    assert lighting.ambient() == tm.theme.ambient


def test_the_frame_is_darker_without_power(game):
    tm = Tilemap.from_file(BLACKOUT)
    from game.core.camera import Camera

    camera = Camera(1280, 720, tm.pixel_width, tm.pixel_height)
    camera.snap_to(pygame.Vector2(400, 400))

    def brightness(power):
        lighting = Lighting(tm)
        lighting.update(POWER_FADE_TIME * 2, False, power=power)
        surface = pygame.Surface((1280, 720))
        surface.fill((200, 200, 200))
        lighting.draw(surface, camera, tm, [])
        return sum(pygame.transform.average_color(surface)[:3])

    assert brightness(False) < brightness(True) * 0.6


def test_no_alarm_lights_without_power():
    lighting = Lighting(Tilemap.from_file(BLACKOUT))
    lighting.update(POWER_FADE_TIME * 2, True, power=False)
    lighting.update(POWER_FADE_TIME * 2, True, power=False)
    assert lighting.ambient() == AMBIENT_BLACKOUT  # ni teinte rouge ni gyrophare


# --- La carte livrée ------------------------------------------------------------------------------------------
def test_the_blackout_level_is_playable_and_has_one_console_one_exit():
    tm = Tilemap.from_file(BLACKOUT)
    assert check_level(tm) == []
    assert len(tm.spawns_of("console")) == 1 and len(tm.spawns_of("exit")) == 1 and not tm.spawns_of("terminal")
    assert explore(tm).can_finish


def test_the_blackout_has_guards_and_a_reachable_console_only_with_the_badges():
    tm = Tilemap.from_file(BLACKOUT)
    assert len(tm.spawns_of("guard")) >= 5
    assert {s.level for s in tm.spawns_of("keycard")} == {1, 2}
    console = tm.spawns_of("console")[0]
    assert tm.door_level(*(40, 10)) == 2  # la salle de contrôle demande le badge 2
    assert (console.tx, console.ty) in explore(tm).tiles


def test_check_level_demands_the_point_of_the_objective():
    only_console = Tilemap.from_text("#######\n#PC.#E#\n#######")
    assert any("exit inaccessible" in p for p in check_level(only_console))
    no_console = Tilemap.from_text("#######\n#P..E.#\n#######")
    assert infer_objective(no_console) is STEAL_PLANS and any("terminal" in p for p in check_level(no_console))


def test_check_level_flags_a_map_with_two_objectives_or_two_consoles():
    both = Tilemap.from_text("#########\n#PTC.E..#\n#########")
    assert any("un seul objectif" in p for p in check_level(both))
    two = Tilemap.from_text("#########\n#PCC.E..#\n#########")
    assert any("plusieurs points 'console'" in p for p in check_level(two))


def test_check_level_flags_a_console_behind_a_door_that_needs_a_missing_badge():
    text = "###########\n#PK.D.C.E.#\n###########\n@door 4,1 -> 2\n"
    assert any("niveau 2" in p for p in check_level(Tilemap.from_text(text)))


def test_route_distances_go_to_the_console():
    tm = Tilemap.from_file(BLACKOUT)
    d = route_distances(tm)
    assert set(d) == {"to_goal", "escape"} and d["to_goal"] > d["escape"] > 0


# --- Un joueur virtuel termine la mission ---------------------------------------------------------------
def test_a_scripted_runner_completes_the_blackout(game, monkeypatch):
    mission = CAMPAIGN.get("blackout")
    scene = play_scene.PlayScene(game, mission.map_path, mission)
    game.scenes.push(scene)
    scene.guards.clear()
    runner = Runner(game, scene, monkeypatch)
    tm = scene.tilemap

    for level in (1, 2):
        card = next(s for s in tm.spawns_of("keycard") if s.level == level)
        runner.go((card.tx, card.ty))
        assert scene.inventory.has_keycard(level)
    runner.press("1")  # le bouton du magasin ouvre l'accès à la sortie
    assert not tm.fields["a"].active

    console = tm.spawns_of("console")[0]
    runner.go((console.tx, console.ty))
    runner.control["interact"] = True
    runner.frames(int(POWER_CUT_TIME * 60) + 20)
    runner.control["interact"] = False
    assert scene.consoles[0].cut and scene.objective_done and not scene.power_on

    exit_ = tm.spawns_of("exit")[0]
    runner.go((exit_.tx, exit_.ty))
    scene.handle_event(KEY_E)
    runner.frames(2)
    assert scene.won and game.progress.is_completed("blackout")


def test_a_player_cannot_leave_before_cutting_the_power(game, monkeypatch):
    mission = CAMPAIGN.get("blackout")
    scene = play_scene.PlayScene(game, mission.map_path, mission)
    game.scenes.push(scene)
    scene.guards.clear()
    runner = Runner(game, scene, monkeypatch)
    for level in (1, 2):
        card = next(s for s in scene.tilemap.spawns_of("keycard") if s.level == level)
        runner.go((card.tx, card.ty))
    runner.press("1")
    exit_ = scene.tilemap.spawns_of("exit")[0]
    runner.go((exit_.tx, exit_.ty))
    scene.handle_event(KEY_E)
    runner.frames(2)
    assert not scene.won


# --- La campagne -----------------------------------------------------------------------------------------
def write_campaign(tmp_path, objective):
    entry = {
        "id": "x",
        "title": "X",
        "map": "blackout.txt",
        "par_time": 60,
        "episode": "ÉPISODE I",
        "summary": "Résumé.",
        "intro": ["Un paragraphe."],
    }
    if objective is not None:
        entry["objective"] = objective
    path = tmp_path / "campaign.json"
    path.write_text(json.dumps({"missions": [entry]}), encoding="utf-8")
    return path


def test_a_mission_defaults_to_stealing_the_plans(tmp_path):
    assert load_campaign(write_campaign(tmp_path, None), MAPS_DIR).missions[0].objective == "steal_plans"


def test_a_mission_can_name_its_objective(tmp_path):
    assert load_campaign(write_campaign(tmp_path, "cut_power"), MAPS_DIR).missions[0].objective == "cut_power"


def test_an_unknown_objective_is_explained(tmp_path):
    with pytest.raises(ValueError, match="objectif inconnu 'piller'"):
        load_campaign(write_campaign(tmp_path, "piller"), MAPS_DIR)


def test_every_objective_can_be_chosen_by_a_mission(tmp_path):
    for objective in OBJECTIVES:
        assert load_campaign(write_campaign(tmp_path, objective), MAPS_DIR).missions[0].objective == objective


@pytest.mark.parametrize("mission", CAMPAIGN.missions, ids=lambda m: m.id)
def test_every_mission_objective_matches_the_points_of_its_map(mission):
    assert infer_objective(Tilemap.from_file(mission.map_path)).id == mission.objective
