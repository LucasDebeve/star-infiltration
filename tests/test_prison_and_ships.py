"""Nouveaux objectifs : libérer un prisonnier (cellules, barreaux, terminal « cellules », prisonnier qui suit) et voler un vaisseau
(console de libération, rayons tracteurs et attaches, passerelle d'embarquement)."""
import pygame
import pytest

from game.ai.perception import can_see
from game.core.camera import Camera
from game.core.input import InputState
from game.entities.door import build_doors
from game.entities.power_console import POWER, RELEASE, PowerConsole
from game.items import Inventory
from game.objectives import FREE_PRISONER, STEAL_SHIP, infer_objective, objective_spawns
from game.scenes import play_scene
from game.settings import (
    CELLS_OPEN_NOISE,
    PRISONER_EXIT_RANGE,
    PRISONER_FOLLOW_DISTANCE,
    PRISONER_FREE_TIME,
    PRISONER_SPEED,
    SHIP_RELEASE_FADE,
    SHIP_RELEASE_NOISE,
    SHIP_RELEASE_TIME,
    TERMINAL_JOB_TIME,
)
from game.systems.interaction import InteractionContext
from game.world import prop_art, tile_art
from game.world.level_check import check_level, explore
from game.world.props import Prop
from game.world.raycast import cast_ray, line_of_sight
from game.world.tilemap import BARS, DOOR, OPEN_DOOR, Tilemap
from tests.paths import CAMPAIGN

V = pygame.Vector2
TS = 32
KEY_E = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_e)
# Une cellule à gauche (prisonnier Q derrière la porte J), un couloir, la sortie.
CELL = "\n".join(["##########", "#Q.J.....#", "#HHH.....#", "#........#", "#P......E#", "##########"])


def tile_center(x, y):
    return V((x + 0.5) * TS, (y + 0.5) * TS)


# --- Barreaux et portes de cellule -------------------------------------------------------------------------------------------------
def test_bars_block_the_body_but_not_the_view_or_the_light():
    tm = Tilemap.from_text(CELL)
    assert tm.tile_at(1, 2) == BARS and tm.is_solid(1, 2) and not tm.is_opaque(1, 2) and not tm.blocks_light(1, 2)
    a, b = tile_center(1, 1), tile_center(1, 3)
    assert line_of_sight(tm, a, b) and line_of_sight(tm, a, b, light=True) and not line_of_sight(tm, a, b, solid=True)
    assert cast_ray(tm, a, (0, 1), 3 * TS - 10, light=True) == 3 * TS - 10  # le rayon traverse les barreaux jusqu'à la tuile 4


def test_a_guard_sees_the_player_through_the_bars():
    tm = Tilemap.from_text(CELL)
    assert can_see(tm, tile_center(1, 1), 1.5707, 1.5, 300, tile_center(1, 4))


def test_a_cell_door_is_a_door_you_can_see_through():
    tm = Tilemap.from_text(CELL)
    assert tm.tile_at(3, 1) == DOOR and (3, 1) in tm.cell_doors
    assert tm.is_solid(3, 1) and not tm.is_opaque(3, 1) and not tm.blocks_light(3, 1)
    assert tm.door_groups() == [([(3, 1)], 0)]


def test_an_ordinary_door_still_blocks_the_view():
    tm = Tilemap.from_text("#####\n#.D.#\n#####")
    assert tm.is_opaque(2, 1) and tm.cell_doors == set()


def test_a_cell_door_without_a_badge_level_is_locked_electronically():
    tm = Tilemap.from_text(CELL)
    door = build_doors(tm)[0]
    assert door.cell and door.level == 0
    prompt = door.prompt(Inventory())
    assert not prompt.enabled and "terminal" in prompt.label  # un badge ne sert à rien : il faut un terminal


def test_a_cell_door_can_also_ask_for_a_badge():
    from game.items import Item, ItemKind

    tm = Tilemap.from_text(CELL + "\n@door 3,1 -> 2\n")
    door = build_doors(tm)[0]
    assert door.level == 2 and not door.prompt(Inventory()).enabled
    inventory = Inventory()
    inventory.add(Item(ItemKind.KEYCARD, 2))
    assert door.prompt(inventory).enabled and "cellule" in door.prompt(inventory).label


def test_opening_a_cell_door_makes_it_walkable():
    tm = Tilemap.from_text(CELL)
    door = build_doors(tm)[0]
    tm.open_door(door.tiles)
    assert tm.tile_at(3, 1) == OPEN_DOOR and not tm.is_solid(3, 1)


def test_cell_doors_and_bars_are_drawn():
    tm = Tilemap.from_text(CELL)
    camera = Camera(320, 192, 320, 192)
    surface = pygame.Surface((320, 192))
    surface.fill((0, 0, 0))
    tm.draw(surface, camera)
    door = build_doors(tm)[0]
    plain = pygame.image.tobytes(surface, "RGB")
    door.draw(surface, camera)
    assert pygame.image.tobytes(surface, "RGB") != plain
    door.is_open, door.progress = True, 1.0
    open_view = pygame.Surface((320, 192))
    open_view.fill((0, 0, 0))
    door.draw(open_view, camera)
    assert pygame.mask.from_threshold(open_view, (0, 0, 0), (1, 1, 1, 255)).count() > pygame.mask.from_threshold(surface, (0, 0, 0), (1, 1, 1, 255)).count() - 3000


def test_the_bars_tile_follows_the_direction_of_the_row():
    horizontal, vertical = tile_art.bars_tile(TS, True), tile_art.bars_tile(TS, False)
    assert horizontal is tile_art.bars_tile(TS, True) and horizontal.get_size() == (TS, TS)
    assert pygame.image.tobytes(horizontal, "RGBA") != pygame.image.tobytes(vertical, "RGBA")
    assert horizontal.get_at((TS // 2, 0)).a == 0  # transparent entre les rails : le sol se voit
    assert pygame.mask.from_surface(horizontal).count() > 100


def test_the_pathfinding_cannot_cross_a_closed_cell_door():
    from game.ai.pathfinding import find_path

    tm = Tilemap.from_text(CELL)
    assert not find_path(tm, (1, 1), (1, 4))  # le prisonnier est enfermé
    tm.open_door([(3, 1)])
    assert find_path(tm, (1, 1), (1, 4))


# --- Terminal « cellules » -------------------------------------------------------------------------------------------------------------
PRISON = CELL.replace("#P......E#", "#P..T...E#") + "\n@terminal 4,4 -> cells\n"


def test_the_cells_power_is_parsed_and_listed_last_but_one():
    from game.terminals import CAPABILITIES, CELLS, LABELS, parse_capabilities

    assert parse_capabilities("lights cells data") == (("data", "cells", "lights"), None) and CELLS in CAPABILITIES
    assert LABELS[CELLS] == "Ouvrir les cellules"


def test_a_cells_terminal_needs_cells_to_open():
    no_cells = Tilemap.from_text("#########\n#P.T..E.#\n#########\n@terminal 3,1 -> data cells\n")
    assert any("aucune porte de cellule" in p for p in check_level(no_cells))
    assert check_level(Tilemap.from_text(PRISON)) == []


def test_a_cell_is_only_reachable_through_the_terminal():
    locked = Tilemap.from_text(CELL)  # pas de terminal : la porte ne s'ouvre jamais
    assert any("inaccessible" in p for p in check_level(locked))
    assert not explore(locked).can_finish
    assert explore(Tilemap.from_text(PRISON)).can_finish
    badge = Tilemap.from_text(CELL.replace("#P......E#", "#P.K....E#") + "\n@door 3,1 -> 1\n")  # ou un badge, sans terminal
    assert explore(badge).can_finish


def test_the_prisoner_is_the_objective_of_a_map_with_one():
    tm = Tilemap.from_text(PRISON)
    assert infer_objective(tm) is FREE_PRISONER and [(s.tx, s.ty) for s in objective_spawns(tm, FREE_PRISONER)] == [(1, 1)]


# --- Dans la scène : le prisonnier -----------------------------------------------------------------------------------------------------------
@pytest.fixture
def prison(game, monkeypatch):
    mission = CAMPAIGN.get("prison")
    holder = {"input": InputState()}
    monkeypatch.setattr(play_scene, "read_input", lambda: holder["input"])
    scene = play_scene.PlayScene(game, mission.map_path, mission)
    game.scenes.push(scene)
    scene.guards.clear()
    scene.holder = holder
    return scene


def run(scene, seconds):
    for _ in range(int(seconds * 60)):
        scene.update(1 / 60)


def test_the_prison_mission_has_a_prisoner_and_locked_cells(prison):
    assert prison.goal is FREE_PRISONER and len(prison.prisoners) == 1 and not prison.prisoners[0].freed
    cells = [d for d in prison.doors if d.cell]
    assert len(cells) == 6 and all(d.level == 0 for d in cells)
    assert prison.objective == FREE_PRISONER.goal and not prison.objective_done and prison.consoles == []


def test_the_prisoner_is_delivered_by_holding_the_key_next_to_him(prison):
    prisoner = prison.prisoners[0]
    assert prisoner.prompt(Inventory()).label.startswith("Libérer") and prisoner.hold_time == PRISONER_FREE_TIME
    freed = []
    prison.game.events.subscribe("prisoner_freed", lambda prisoner, **_: freed.append(prisoner))
    heard = []
    prison.game.events.subscribe("noise", lambda pos, radius: heard.append(radius))
    prisoner.interact(InteractionContext(prison.tilemap, prison.inventory, prison.game.events))
    assert prisoner.freed and freed == [prisoner] and heard and prisoner.prompt(Inventory()) is None
    assert prison.objective_done and any("libéré" in t[0] for t in prison.hud._toasts)


def test_a_captive_prisoner_stays_where_he_is(prison):
    prisoner = prison.prisoners[0]
    start = V(prisoner.pos)
    prison.player.pos.update(start + V(0, 200))
    run(prison, 2)
    assert prisoner.pos == start and prisoner.stride < 0.05


def free(prison):
    prisoner = prison.prisoners[0]
    for door in prison.doors:
        if door.cell:
            prison.tilemap.open_door(door.tiles)
            door.is_open = True
    prisoner.freed = True
    return prisoner


def test_a_freed_prisoner_follows_the_player_around_obstacles(prison):
    prisoner = free(prison)
    target = prisoner.pos + V(0, 5 * TS)  # dans la salle des gardes, au sud
    prison.player.pos.update(target)
    run(prison, 4)
    assert prisoner.pos.distance_to(prison.player.pos) <= PRISONER_FOLLOW_DISTANCE + 10
    assert prisoner.walk_phase != 0 or prisoner.stride >= 0  # il a marché


def test_the_prisoner_walks_slower_than_a_running_player(prison):
    from game.settings import PLAYER_SPEED

    assert PRISONER_SPEED <= PLAYER_SPEED["walk"] < PLAYER_SPEED["run"]
    prisoner = free(prison)
    prison.player.pos.update(prisoner.pos + V(0, 6 * TS))
    run(prison, 1)
    assert prisoner.pos.distance_to(prison.player.pos) > PRISONER_FOLLOW_DISTANCE  # en une seconde il n'a pas rattrapé 6 tuiles


def test_the_prisoner_stops_near_the_player_and_faces_him(prison):
    prisoner = free(prison)
    prison.player.pos.update(prisoner.pos + V(0, 30))
    run(prison, 1)
    before = V(prisoner.pos)
    run(prison, 1)
    assert prisoner.pos.distance_to(before) < 2 and prisoner.stride < 0.2


def test_the_prisoner_waits_behind_a_closed_force_field(game, monkeypatch, tmp_path):
    text = "#########\n#P.a.Q..#\n#########\n@objective free_prisoner\n---\nfield a closed\nbutton 1 toggles a\n"
    text = text.replace("#P.a.Q..#", "#P.a.QE1#")
    path = tmp_path / "m.txt"
    path.write_text(text)
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState())
    scene = play_scene.PlayScene(game, path)
    game.scenes.push(scene)
    prisoner = scene.prisoners[0]
    prisoner.freed = True
    start = V(prisoner.pos)
    run(scene, 2)
    assert prisoner.pos.distance_to(start) < 2  # le champ barre la route : il attend de ce côté


def test_the_exit_waits_for_the_prisoner(prison):
    prisoner = free(prison)
    pad = prison.exit_pad
    prison.player.pos.update(pad.pos)
    prisoner.pos.update(pad.pos + V(0, 6 * TS))  # loin de la sortie
    assert prison.objective_done and not prison.exit_ready and prison.exit_missing == "Attendez le prisonnier"
    prompt = pad.prompt(prison.inventory)
    assert not prompt.enabled and prompt.label == "Attendez le prisonnier"
    prisoner.pos.update(pad.pos + V(PRISONER_EXIT_RANGE - 10, 0))
    assert prison.exit_ready and pad.prompt(prison.inventory).enabled


def test_the_exit_says_the_prisoner_is_missing_before_he_is_freed(prison):
    assert prison.exit_missing == FREE_PRISONER.missing and not prison.exit_ready


def test_a_restart_locks_the_cells_again_and_recaptures_the_prisoner(prison):
    free(prison)
    prison.restart()
    assert not prison.prisoners[0].freed and all(not d.is_open for d in prison.doors if d.cell)
    assert prison.tilemap.tile_at(*[t for d in prison.doors if d.cell for t in d.tiles][0]) == DOOR


def test_the_cells_menu_opens_every_cell_at_once_and_makes_noise(prison):
    terminal = next(t for t in prison.terminals if t.spec.can("cells"))
    prison.player.pos.update(terminal.pos + V(-24, 0))
    prison.handle_event(KEY_E)
    prison.update(1 / 60)
    prison.update(1 / 60)
    menu = prison.game.scenes.current
    actions = {a[0]: a for a in menu.actions}
    assert actions["cells"][2] and "6 cellule" in actions["cells"][3]
    heard, opened = [], []
    prison.game.events.subscribe("noise", lambda pos, radius: heard.append(radius))
    prison.game.events.subscribe("cells_opened", lambda terminal, count: opened.append(count))
    assert menu.choose("cells")
    run(prison, TERMINAL_JOB_TIME["cells"] + 0.3)
    assert opened == [6] and CELLS_OPEN_NOISE in heard and all(d.is_open for d in prison.doors if d.cell)
    assert any("Cellules ouvertes" in t[0] for t in prison.hud._toasts)
    prison.handle_event(KEY_E)
    prison.update(1 / 60)
    prison.update(1 / 60)
    assert prison.game.scenes.current.actions[0][2] is False or "déjà" in " ".join(a[3] for a in prison.game.scenes.current.actions)


def test_the_prisoner_sprite_is_drawn_captive_and_free():
    from game.ui.sprites import draw_prisoner

    pictures = set()
    for captive in (True, False):
        for phase in (0.0, 1.5):
            surface = pygame.Surface((60, 60))
            surface.fill((50, 56, 70))
            draw_prisoner(surface, (30, 30), (1, 0), captive, phase, 1.0)
            pictures.add(pygame.image.tobytes(surface, "RGB"))
    assert len(pictures) >= 3  # captif, libre qui marche : des silhouettes différentes
    suit = pygame.Surface((60, 60))
    draw_prisoner(suit, (30, 30), (1, 0), True)
    from game.settings import COLORS

    assert COLORS["prisoner_suit"] in {suit.get_at((x, y))[:3] for x in range(60) for y in range(60)}


def test_the_prison_map_is_a_valid_escape():
    tm = Tilemap.from_file(CAMPAIGN.get("prison").map_path)
    assert check_level(tm) == [] and explore(tm).can_finish
    assert len(tm.cell_doors) == 6 and tm.cells_openable and len(tm.spawns_of("prisoner")) == 1
    assert tm.spawns_of("console") == []


# --- Vol de vaisseau ---------------------------------------------------------------------------------------------------------------------------
@pytest.fixture
def theft(game, monkeypatch):
    mission = CAMPAIGN.get("theft")
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState())
    scene = play_scene.PlayScene(game, mission.map_path, mission)
    game.scenes.push(scene)
    scene.guards.clear()
    return scene


def test_the_objective_directive_tells_both_console_objectives_apart():
    ship = Tilemap.from_text("#####\n#PEC#\n#####\n@objective steal_ship\n")
    power = Tilemap.from_text("#####\n#PEC#\n#####\n")
    assert infer_objective(ship) is STEAL_SHIP and infer_objective(power).id == "cut_power"
    assert ship.declared_objective == "steal_ship" and power.declared_objective is None


@pytest.mark.parametrize("line,message", [("@objective piller", "Objectif inconnu"), ("@objective cut_power\n@objective steal_ship", "déjà indiqué")])
def test_bad_objective_directives_are_explained(line, message):
    with pytest.raises(ValueError, match=rf"Ligne \d : .*{message}"):
        Tilemap.from_text("#####\n#PEC#\n#####\n" + line + "\n")


def test_the_release_console_asks_for_a_longer_hold_and_makes_more_noise():
    release, power = PowerConsole(10, 10, RELEASE), PowerConsole(10, 10, POWER)
    assert release.hold_time == SHIP_RELEASE_TIME > power.hold_time and "vaisseaux" in release.prompt(Inventory()).label
    events = []
    bus = type("Bus", (), {"emit": lambda self, name, **kw: events.append((name, kw))})()
    release.interact(InteractionContext(None, Inventory(), bus))
    assert events[0][0] == "ships_released" and events[1][1]["radius"] == SHIP_RELEASE_NOISE and release.cut and release.prompt(Inventory()) is None


def test_the_theft_scene_has_a_release_console_and_held_ships(theft):
    assert theft.goal is STEAL_SHIP and len(theft.consoles) == 1 and theft.consoles[0].kind == RELEASE
    assert theft.tilemap.ship_hold == 0.0 and not theft.objective_done and theft.objective == STEAL_SHIP.goal
    assert theft.exit_pad.label == "Embarquer" and theft.exit_missing == STEAL_SHIP.missing
    assert not theft.exit_pad.prompt(theft.inventory).enabled and theft.exit_pad.prompt(theft.inventory).label == "Rayons tracteurs actifs"


def test_releasing_the_ships_does_not_turn_the_lights_off(theft):
    assert theft.power_on
    theft.consoles[0].cut = True
    assert theft.power_on and theft.objective_done  # la console libère les vaisseaux : l'alimentation reste


def test_the_tractor_beams_and_clamps_fade_after_the_release(theft):
    run(theft, 0.5)
    assert theft.tilemap.ship_hold == 0.0
    theft.game.events.emit("ships_released", console=theft.consoles[0])
    theft.consoles[0].cut = True
    run(theft, SHIP_RELEASE_FADE / 2)
    assert 0.3 < theft.tilemap.ship_hold < 0.7
    run(theft, SHIP_RELEASE_FADE)
    assert theft.tilemap.ship_hold == 1.0
    assert any("Rayons tracteurs" in t[0] for t in theft.hud._toasts)


def test_the_exit_opens_once_the_ships_are_free(theft):
    theft.consoles[0].cut = True
    assert theft.exit_ready and theft.exit_pad.prompt(theft.inventory).label == "Embarquer"


def test_the_target_ship_is_the_one_next_to_the_exit(theft):
    target = theft.tilemap.target_ship()
    assert target is not None and target.x == 50
    ex = theft.tilemap.spawns_of("exit")[0].tx
    assert abs(target.x + target.w / 2 - ex) < 5


def test_other_maps_do_not_hold_their_ships(game, monkeypatch):
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState())
    scene = play_scene.PlayScene(game, CAMPAIGN.get("hangar").map_path, CAMPAIGN.get("hangar"))
    assert scene.tilemap.ship_hold is None  # le hangar a des vaisseaux, mais personne ne les retient


def test_check_level_wants_a_ship_next_to_the_exit():
    def build(*rows):
        return Tilemap.from_text("\n".join(rows) + "\n@objective steal_ship\n")

    no_ship = build("#" * 20, "#PE.....C" + "." * 10 + "#", "#" * 20)
    assert any("aucun vaisseau" in p for p in check_level(no_ship))
    far = build("#" * 20, "#PE" + "." * 4 + "C.SS" + "." * 8 + "#", "#" * 20)
    assert any("contre le vaisseau" in p for p in check_level(far))
    near = build("#" * 12, "#P.C.SSE...#", "#....SS....#", "#..........#", "#" * 12)
    assert check_level(near) == []


def test_the_theft_map_is_valid(game):
    tm = Tilemap.from_file(CAMPAIGN.get("theft").map_path)
    assert check_level(tm) == [] and explore(tm).can_finish and len(tm.spawns_of("console")) == 1
    assert sum(p.kind == "ship" for p in tm.props) >= 4 and tm.has_void


# --- Dessin des rayons tracteurs et des attaches ---------------------------------------------------------------------------------------------
def render(hold, target=False, time=0.4):
    surface = pygame.Surface((260, 220))
    surface.fill((30, 34, 44))
    prop = Prop("ship", 2, 2, 5, 4, "N")
    prop_art.draw_prop(surface, prop, pygame.Rect(50, 40, 160, 128), TS, time, hold=hold, target=target)
    return surface


def image(surface):
    return pygame.image.tobytes(surface, "RGB")


def test_a_held_ship_looks_different_from_a_free_one():
    held, half, free = image(render(0.0)), image(render(0.5)), image(render(1.0))
    assert len({held, half, free}) == 3
    assert image(render(None)) != held  # un vaisseau non retenu n'a ni rayon ni attaches


def test_the_tractor_beam_surrounds_the_ship_and_fades_out():
    beam = render(0.0).get_at((38, 100))[:3]  # hors de la coque : seul le rayon éclaire
    assert beam != (30, 34, 44)
    assert render(1.0).get_at((38, 100))[:3] == (30, 34, 44)


def test_the_rings_move_with_time():
    assert image(render(0.0, time=0.0)) != image(render(0.0, time=0.5))


def test_clamps_open_and_their_lamp_turns_green():
    def lamp_colors(hold):
        surface = render(hold)
        return {surface.get_at((x, y))[:3] for x in range(40, 230) for y in range(40, 170)}

    assert (255, 70, 70) in lamp_colors(0.0) and (90, 235, 130) in lamp_colors(1.0)


def test_the_boarding_arrow_only_marks_the_target_once_free():
    def arrow(surface):
        return surface.subsurface(pygame.Rect(110, 10, 60, 30))

    held_target, free_target, free_other = render(0.0, True), render(1.0, True), render(1.0, False)
    assert image(arrow(held_target)) == image(arrow(render(0.0, False)))
    assert image(arrow(free_target)) != image(arrow(free_other))


def test_the_engines_glow_harder_when_the_ship_is_ready():
    held, ready = render(0.0), render(1.0)
    assert sum(pygame.transform.average_color(ready)[:3]) != sum(pygame.transform.average_color(held)[:3])


def test_the_scene_draws_held_and_free_ships_without_error(theft, game):
    theft.player.pos.update(tile_center(48, 12))
    theft.camera.snap_to(theft.player.pos)
    for _ in range(20):
        game.step(1 / 60)
    theft.consoles[0].cut = True
    for _ in range(120):
        game.step(1 / 60)
    assert theft.tilemap.ship_hold == 1.0


def test_the_events_have_their_sounds():
    from game.core.events import EventBus
    from game.systems.sound_director import SoundDirector

    calls = []

    class Audio:
        def play(self, name, volume=1.0, pan=0.0): calls.append(name)
        def play_at(self, *a, **k): pass
        def stop_loop(self, name): pass

    bus = EventBus()
    SoundDirector(Audio(), bus).attach()
    for event, payload in (("ships_released", {"console": None}), ("cells_opened", {"terminal": None, "count": 2}), ("prisoner_freed", {"prisoner": None})):
        bus.emit(event, **payload)
    assert calls == ["tractor_off", "cell_open", "hack_done"]
    from game.settings import SOUNDS_DIR

    assert (SOUNDS_DIR / "tractor_off.wav").exists() and (SOUNDS_DIR / "cell_open.wav").exists()
