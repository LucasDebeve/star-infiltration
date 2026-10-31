"""La campagne monte en difficulté : chaque niveau est plus complexe que le précédent, introduit ses nouveautés au bon moment,
reste faisable de bout en bout et laisse le temps de fuir."""
import math

import pygame
import pytest

from game.ai.perception import can_see
from game.campaign import load_campaign
from game.difficulty import all_difficulties
from game.objectives import STEAL_PLANS, objective_spawns
from game.scenes import play_scene
from game.settings import GUARD_VISION_RANGE, HACK_TIME, PLAYER_SPEED, SHIP_RELEASE_FADE
from game.terminals import CAMERAS
from game.world.level_check import check_level, complexity, explore, route_distances
from game.world.tilemap import Tilemap
from tests.paths import CAMPAIGN
from tests.runner import Runner

ORDER = ["training", "outpost", "blackout", "endor", "uniform", "radar", "prison", "hangar", "theft", "hq", "cruiser", "destroyer"]
KEY_E = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_e)
MISSIONS = [CAMPAIGN.get(i) for i in ORDER]
MAPS = {m.id: Tilemap.from_file(m.map_path) for m in MISSIONS}


def utility_terminals(tm):
    return [s for s in tm.spawns_of("terminal") if not tm.terminal_spec((s.tx, s.ty)).can("data")]


# --- La courbe de difficulté ------------------------------------------------------------------------------------------
def test_the_campaign_order_is_the_intended_one():
    assert [m.id for m in CAMPAIGN.missions] == ORDER


def test_every_level_is_more_complex_than_the_one_before():
    scores = [complexity(MAPS[i]) for i in ORDER]
    assert all(a < b for a, b in zip(scores, scores[1:])), dict(zip(ORDER, scores))
    assert scores[-1] > 5 * scores[0]  # le dernier niveau n'a rien à voir avec l'entraînement


def test_the_danger_rating_never_goes_down_and_ends_at_the_top():
    ratings = [m.danger for m in MISSIONS]
    assert ratings == sorted(ratings) and ratings[0] == 1 and ratings[-1] == 5 and set(ratings) >= {1, 2, 3, 4, 5}


def test_reference_times_grow_with_the_levels():
    times = [m.par_time for m in MISSIONS]
    assert times == sorted(times) and len(set(times)) == len(times)


def test_the_number_of_guards_never_goes_down():
    guards = [len(MAPS[i].spawns_of("guard")) for i in ORDER]
    assert guards == sorted(guards) and guards[-1] >= 15 and guards[0] == 1


def test_maps_get_bigger_overall():
    areas = [MAPS[i].width * MAPS[i].height for i in ORDER]
    assert areas[0] == min(areas) and areas[-1] == max(areas)


def test_the_two_objectives_alternate_through_the_campaign():
    objectives = [m.objective for m in MISSIONS]
    assert objectives.count("cut_power") == 3 and objectives.count("steal_plans") == 6  # dont le quartier général, qui exige l'uniforme
    assert objectives.count("steal_uniform") == 1
    assert objectives.count("free_prisoner") == 1 and objectives.count("steal_ship") == 1  # une évasion et un vol de vaisseau
    assert objectives[0] == "steal_plans" and objectives[-1] == "cut_power"  # on finit en coupant le courant du vaisseau amiral


# --- Les nouveautés arrivent progressivement -----------------------------------------------------------------------------------
def first_level_with(predicate):
    return next(i for i in ORDER if predicate(MAPS[i]))


def test_each_mechanic_is_introduced_at_a_sensible_moment():
    assert first_level_with(lambda tm: tm.spawns_of("terminal")) == "training"
    assert first_level_with(lambda tm: tm.fields) == "training"  # champ de force et bouton : appris dès l'entraînement
    assert first_level_with(lambda tm: tm.cameras) == "outpost"  # les caméras viennent juste après
    assert first_level_with(utility_terminals) == "outpost"  # avec le terminal qui sait les couper
    assert first_level_with(lambda tm: any(lvl >= 2 for _, lvl in tm.door_groups())) == "blackout"
    assert first_level_with(lambda tm: len(tm.fields) >= 2) == "radar"
    assert first_level_with(lambda tm: any(lvl >= 3 for _, lvl in tm.door_groups())) == "hangar"
    assert first_level_with(lambda tm: tm.has_void) == "hangar"
    assert first_level_with(lambda tm: tm.spawns_of("uniform")) == "uniform"  # le casier d'abord, la porte du personnel ensuite
    assert first_level_with(lambda tm: tm.uniform_doors) == "hq"


def test_the_first_levels_are_gentle():
    assert MAPS["training"].spawns_of("reinforcement") == [] and MAPS["training"].cameras == []
    assert len(MAPS["outpost"].spawns_of("guard")) <= 3 and len(MAPS["outpost"].cameras) == 1
    assert len(MAPS["outpost"].tip_zones) == 0


def test_the_last_levels_use_everything():
    last = MAPS["destroyer"]
    assert len(last.cameras) >= 5 and len(utility_terminals(last)) >= 3 and len(last.fields) >= 2
    assert max(lvl for _, lvl in last.door_groups()) == 3 and last.has_void and last.spawns_of("console")
    caps = {c for spec in last.terminal_specs.values() for c in spec.capabilities}
    assert {"lights", "cameras"} <= caps


@pytest.mark.parametrize("level", ORDER[1:])
def test_every_new_level_has_what_a_level_needs(level):
    tm = MAPS[level]
    assert check_level(tm) == [] and tm.warnings == []
    assert len(tm.spawns_of("decoy")) >= 3 and len(tm.spawns_of("reinforcement")) >= 2
    assert tm.spawns_of("player") and tm.spawns_of("exit")
    assert len(tm.spawns_of("guard")) >= 3


# --- Équilibre ------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("level", ORDER)
def test_the_level_beats_the_lockdown_even_on_hard(level):
    d = route_distances(MAPS[level])
    run_time = (d["to_goal"] + d["escape"]) / PLAYER_SPEED["run"] + HACK_TIME
    for difficulty in all_difficulties():
        lockdown = difficulty.for_map(MAPS[level].settings).lockdown_time  # avec les réglages de la carte
        assert run_time <= lockdown * 0.5, (level, difficulty.key)


@pytest.mark.parametrize("level", ORDER)
def test_the_escape_alone_leaves_a_margin_once_alerted_at_the_goal(level):
    d = route_distances(MAPS[level])
    for difficulty in all_difficulties():
        lockdown = difficulty.for_map(MAPS[level].settings).lockdown_time
        assert d["escape"] / PLAYER_SPEED["run"] <= lockdown * 0.35, (level, difficulty.key)


@pytest.mark.parametrize("level", ORDER)
def test_the_reference_time_leaves_room_for_the_detours(level):
    mission, d = CAMPAIGN.get(level), route_distances(MAPS[level])
    calm_walk = (d["to_goal"] + d["escape"]) / PLAYER_SPEED["walk"]
    assert mission.par_time >= 1.4 * calm_walk, level  # même à pas tranquilles, avec les détours de badges et de boutons


@pytest.mark.parametrize("level", ORDER)
def test_nobody_watches_the_start(level):
    tm = MAPS[level]
    start = tm.spawns_of("player")[0].center(32)
    for spawn in tm.spawns_of("guard"):
        guard_pos = spawn.center(32)
        assert guard_pos.distance_to(start) > GUARD_VISION_RANGE or not can_see(tm, guard_pos, 0, math.tau, GUARD_VISION_RANGE, start), spawn
    for camera in tm.cameras:
        mount = pygame.Vector2((camera.tile[0] + 0.5) * 32, (camera.tile[1] + 0.5) * 32)
        assert mount.distance_to(start) > 220, camera  # une caméra ne regarde pas le point de départ de près


@pytest.mark.parametrize("level", ORDER)
def test_every_patrol_is_reachable_and_guards_are_not_stacked(level):
    tm = MAPS[level]
    starts = [(s.tx, s.ty) for s in tm.spawns_of("guard")]
    assert len(set(starts)) == len(starts)
    assert all(not tm.is_solid(*tile) for tile in starts)


@pytest.mark.parametrize("level", ORDER)
def test_a_perfect_player_can_finish(level):
    assert explore(MAPS[level]).can_finish


# --- Parties jouées par un joueur virtuel -------------------------------------------------------------------------------------------
def hold_console(runner, scene):
    console = scene.tilemap.spawns_of("console")[0]
    runner.go((console.tx, console.ty))
    runner.control["interact"] = True
    runner.frames(int(scene.consoles[0].hold_time * 60) + 20)
    runner.control["interact"] = False
    assert scene.consoles[0].cut


def take(runner, level, scene):
    card = next(s for s in scene.tilemap.spawns_of("keycard") if s.level == level)
    runner.go((card.tx, card.ty))
    assert scene.inventory.has_keycard(level)


def leave(runner, scene):
    exit_ = scene.tilemap.spawns_of("exit")[0]
    runner.go((exit_.tx, exit_.ty))
    scene.handle_event(KEY_E)
    runner.frames(2)


def play_outpost(runner, scene):
    take(runner, 1, scene)
    util = utility_terminals(scene.tilemap)[0]
    runner.use_terminal(CAMERAS, tile=(util.tx, util.ty))
    assert not scene.cameras[0].active
    runner.use_terminal()
    leave(runner, scene)


def play_radar(runner, scene):
    take(runner, 1, scene)
    runner.press("1")  # le poste de garde (porte à badge 1) : le bouton ouvre le champ de l'entrepôt
    take(runner, 2, scene)
    hold_console(runner, scene)
    runner.press("2")
    leave(runner, scene)


def play_hangar(runner, scene):
    take(runner, 1, scene)
    take(runner, 2, scene)
    runner.press("1")
    take(runner, 3, scene)
    runner.press("2")
    runner.use_terminal()
    leave(runner, scene)


def play_destroyer(runner, scene):
    take(runner, 1, scene)
    take(runner, 2, scene)
    runner.press("1")
    take(runner, 3, scene)
    runner.press("2")
    hold_console(runner, scene)
    leave(runner, scene)


def play_prison(runner, scene):
    from game.settings import PRISONER_FREE_TIME

    take(runner, 1, scene)
    take(runner, 2, scene)  # la caserne (badge 1) : badge 2 et bouton 1
    runner.press("1")
    cells = next(s for s in scene.tilemap.spawns_of("terminal") if scene.tilemap.terminal_spec((s.tx, s.ty)).can("cells"))
    runner.use_terminal("cells", tile=(cells.tx, cells.ty))  # les portes de cellule ne s'ouvrent pas à la main : le terminal les ouvre
    assert all(d.is_open for d in scene.doors if d.cell)
    prisoner = scene.prisoners[0]
    runner.go((int(prisoner.pos.x // 32), int(prisoner.pos.y // 32) + 1))
    runner.control["interact"] = True
    runner.frames(int(PRISONER_FREE_TIME * 60) + 20)
    runner.control["interact"] = False
    assert prisoner.freed and scene.objective_done
    exit_ = scene.tilemap.spawns_of("exit")[0]
    runner.go((exit_.tx, exit_.ty))
    scene.handle_event(KEY_E)
    runner.frames(2)
    assert not scene.won and scene.exit_missing == "Attendez le prisonnier"  # il suit à la marche : on ne part pas sans lui
    for _ in range(60 * 40):
        runner.frames(1)
        if scene.exit_ready:
            break
    scene.handle_event(KEY_E)
    runner.frames(2)


def play_theft(runner, scene):
    take(runner, 1, scene)
    runner.press("1")  # opérations : le bouton ouvre la cloison de la baie
    take(runner, 3, scene)
    runner.press("2")  # quartiers : le bouton ouvre la coursive vers la tour
    hold_console(runner, scene)
    assert scene.tilemap.ship_hold is not None
    runner.frames(int(SHIP_RELEASE_FADE * 60) + 10)
    assert scene.tilemap.ship_hold == 1.0
    leave(runner, scene)


def play_uniform(runner, scene):
    take(runner, 1, scene)
    runner.press("1")  # le réfectoire : le bouton ouvre le champ de la coursive
    take(runner, 2, scene)
    runner.take_uniform(wear=False)
    assert scene.objective_done
    leave(runner, scene)


def play_hq(runner, scene):
    runner.press("1")  # le poste de garde : la coursive vers les casernes
    runner.press("2")  # la cloison du réfectoire
    take(runner, 1, scene)
    runner.take_uniform()
    take(runner, 2, scene)  # l'aile est : réservée au personnel
    runner.use_terminal()
    leave(runner, scene)


PLAYTHROUGHS = {
    "uniform": play_uniform, "hq": play_hq, "outpost": play_outpost, "radar": play_radar, "prison": play_prison, "hangar": play_hangar, "theft": play_theft, "destroyer": play_destroyer,
}


@pytest.mark.parametrize("level", list(PLAYTHROUGHS))
def test_a_virtual_player_completes_the_new_levels(game, monkeypatch, level):
    mission = CAMPAIGN.get(level)
    scene = play_scene.PlayScene(game, mission.map_path, mission)
    game.scenes.push(scene)
    scene.guards.clear()
    PLAYTHROUGHS[level](Runner(game, scene, monkeypatch), scene)
    assert scene.won and game.progress.is_completed(level)


def test_a_player_cannot_skip_the_badges_of_the_hangar(game, monkeypatch):
    mission = CAMPAIGN.get("hangar")
    scene = play_scene.PlayScene(game, mission.map_path, mission)
    game.scenes.push(scene)
    scene.guards.clear()
    runner = Runner(game, scene, monkeypatch)
    terminal = next(t for t in scene.terminals if t.spec.can("data"))
    with pytest.raises(AssertionError):
        runner.go((int(terminal.pos.x // 32), int(terminal.pos.y // 32)))  # sans badge ni bouton, la tour est hors d'atteinte


def test_the_headquarters_cannot_be_infiltrated_the_classic_way():
    """Sans l'uniforme, même un joueur parfait n'atteint ni les plans ni la sortie : la méthode est obligatoire."""
    tm = MAPS["hq"]
    assert tm.uniform_doors and tm.spawns_of("uniform")
    assert explore(tm).can_finish and not explore(tm, allow_uniform=False).can_finish
    terminal = objective_spawns(tm, STEAL_PLANS)[0]
    assert (terminal.tx, terminal.ty) not in explore(tm, allow_uniform=False).tiles


def test_a_player_without_the_uniform_is_stopped_by_the_staff_door(game, monkeypatch):
    mission = CAMPAIGN.get("hq")
    scene = play_scene.PlayScene(game, mission.map_path, mission)
    game.scenes.push(scene)
    scene.guards.clear()
    runner = Runner(game, scene, monkeypatch)
    runner.press("1")
    runner.press("2")
    take(runner, 1, scene)
    terminal = next(t for t in scene.terminals if t.spec.can("data"))
    with pytest.raises(AssertionError):
        runner.go((int(terminal.pos.x // 32), int(terminal.pos.y // 32)))


# --- Affichage de la menace ------------------------------------------------------------------------------------------------------------------
def test_the_campaign_map_shows_every_mission_with_its_danger(game):
    from game.scenes.campaign_scene import CampaignScene
    from game.scenes.main_menu import MainMenuScene

    game.scenes.push(MainMenuScene(game))
    from game.progress import MissionStats, compute_result

    for mission in MISSIONS:
        game.progress.record(mission.id, compute_result(MissionStats(60, 0, 0), 100))
    scene = CampaignScene(game, CAMPAIGN.get("destroyer"))
    game.scenes.push(scene)
    surface = pygame.Surface(game.screen.get_size())
    for index in range(len(MISSIONS)):
        scene.index = index
        scene.draw(surface)  # ne plante pas, avec huit nœuds et l'indicateur de menace


def test_danger_is_validated_when_loading_the_campaign(tmp_path):
    import json

    from game.settings import MAPS_DIR

    def write(danger):
        entry = {"id": "x", "title": "X", "map": "training.txt", "par_time": 60, "episode": "ÉPISODE I", "summary": "R.", "intro": ["Un."], "danger": danger}
        path = tmp_path / "c.json"
        path.write_text(json.dumps({"missions": [entry]}), encoding="utf-8")
        return load_campaign(path, MAPS_DIR)

    assert write(3).missions[0].danger == 3
    for bad in (0, 6, "dur", 2.5, True):
        with pytest.raises(ValueError, match="'danger' doit être un entier de 1 à 5"):
            write(bad)
