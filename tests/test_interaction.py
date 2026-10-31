import pygame
import pytest

from game.core.events import EventBus
from game.entities.decoy import Decoy
from game.entities.door import build_doors
from game.entities.exit_pad import ExitPad
from game.entities.pickup import Pickup
from game.entities.terminal import Terminal
from game.items import Inventory, Item, ItemKind
from game.settings import DECOY_BEEP_INTERVAL, DECOY_DURATION, DOOR_NOISE, HACK_TIME
from game.systems.interaction import InteractionSystem, Prompt, collect_pickups
from game.world.tilemap import Tilemap

DT = 1 / 60
KEY = lambda level: Item(ItemKind.KEYCARD, level)  # noqa: E731
DATA = Item(ItemKind.DATA)

# Deux salles séparées par une porte double de niveau 1 (en x = 4).
MAP = "#########\n#...#...#\n#...D...#\n#...D...#\n#...#...#\n#########\n@door 4,2 -> 1\n"


class Recorder:
    """Branche un EventBus et note tous les événements reçus."""

    def __init__(self, bus, *names):
        self.events = []
        for name in names:
            bus.subscribe(name, lambda _n=name, **payload: self.events.append((_n, payload)))

    def names(self):
        return [name for name, _ in self.events]


@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def world(bus):
    tm = Tilemap.from_text(MAP)
    return tm, build_doors(tm), Inventory(), InteractionSystem(bus)


def center(tx, ty):
    return pygame.Vector2((tx + 0.5) * 32, (ty + 0.5) * 32)


def tick(system, tm, inv, objects, pos, *, pressed=False, held=False, dt=DT):
    system.update(dt, pos, tm, inv, objects, pressed=pressed, held=held)


# --- Portes ------------------------------------------------------------------
def test_build_doors_groups_double_doors():
    tm = Tilemap.from_text(MAP)
    doors = build_doors(tm)
    assert len(doors) == 1 and doors[0].level == 1 and len(doors[0].tiles) == 2
    assert doors[0].anchor == pygame.Vector2(4.5 * 32, 3 * 32)  # centre de la porte double


def test_door_distance_is_to_the_nearest_tile():
    door = build_doors(Tilemap.from_text(MAP))[0]
    assert door.distance_to(center(3, 2)) == pytest.approx(32)
    assert door.distance_to(center(3, 3)) == pytest.approx(32)


def test_locked_door_prompt_and_denied_event(world, bus):
    tm, doors, inv, system = world
    rec = Recorder(bus, "interaction_denied", "door_opened")
    tick(system, tm, inv, doors, center(3, 2), pressed=True)
    assert system.prompt == Prompt("Badge niv. 1 requis", enabled=False)
    assert rec.names() == ["interaction_denied"]
    assert rec.events[0][1]["message"] == "Badge niv. 1 requis"
    assert tm.is_solid(4, 2) and not doors[0].is_open


def test_door_opens_with_the_right_keycard(world, bus):
    tm, doors, inv, system = world
    inv.add(KEY(1))
    rec = Recorder(bus, "door_opened", "noise")
    tick(system, tm, inv, doors, center(3, 2))
    assert system.prompt == Prompt("Ouvrir") and rec.events == []  # l'invite seule n'ouvre rien
    tick(system, tm, inv, doors, center(3, 2), pressed=True)
    assert not tm.is_solid(4, 2) and not tm.is_solid(4, 3) and doors[0].is_open
    assert rec.names() == ["door_opened", "noise"]
    noise = dict(rec.events)["noise"]
    assert noise["radius"] == DOOR_NOISE and noise["pos"] == doors[0].anchor


def test_badge_is_kept_after_opening(world):
    tm, doors, inv, system = world
    inv.add(KEY(1))
    tick(system, tm, inv, doors, center(3, 2), pressed=True)
    assert inv.has_keycard(1)  # le badge n'est pas consommé


def test_open_door_has_no_prompt(world):
    tm, doors, inv, system = world
    inv.add(KEY(1))
    tick(system, tm, inv, doors, center(3, 2), pressed=True)
    tick(system, tm, inv, doors, center(3, 2))
    assert system.target is None and system.prompt is None


def test_free_door_needs_no_badge():
    tm = Tilemap.from_text("#####\n#.D.#\n#####")
    door = build_doors(tm)[0]
    assert door.level == 0 and door.prompt(Inventory()) == Prompt("Ouvrir")


def test_out_of_reach_means_no_interaction(world, bus):
    tm, doors, inv, system = world
    rec = Recorder(bus, "interaction_denied")
    tick(system, tm, inv, doors, center(1, 1), pressed=True)
    assert system.target is None and rec.events == []


def test_pressed_without_target_does_nothing(world):
    tm, doors, inv, system = world
    tick(system, tm, inv, [], center(1, 1), pressed=True)
    assert system.progress == 0


# --- Terminal : un appui ouvre son menu ------------------------------------------
def make_terminal_world(bus, capabilities=("data",)):
    from game.terminals import TerminalSpec

    tm = Tilemap.from_text("#######\n#.....#\n#######")
    terminal = Terminal(*center(3, 1), TerminalSpec((3, 1), capabilities))
    return tm, terminal, Inventory(), InteractionSystem(bus)


def hold(system, tm, inv, objs, pos, seconds, held=True):
    for _ in range(round(seconds / DT)):
        tick(system, tm, inv, objs, pos, held=held)


def test_pressing_the_key_opens_the_terminal_menu(bus):
    tm, terminal, inv, system = make_terminal_world(bus)
    rec = Recorder(bus, "terminal_opened", "terminal_hacked")
    tick(system, tm, inv, [terminal], center(2, 1), pressed=True, held=False)
    assert rec.names() == ["terminal_opened"] and rec.events[0][1]["terminal"] is terminal
    assert not terminal.hacked and inv.count(DATA) == 0  # ouvrir le menu ne télécharge rien


def test_holding_the_key_no_longer_hacks_a_terminal(bus):
    tm, terminal, inv, system = make_terminal_world(bus)
    hold(system, tm, inv, [terminal], center(2, 1), HACK_TIME + 1.0)
    assert not terminal.hacked and inv.count(DATA) == 0 and system.progress == 0


def test_the_prompt_invites_to_use_the_terminal(bus):
    tm, terminal, inv, system = make_terminal_world(bus)
    assert terminal.prompt(inv) == Prompt("Utiliser le terminal") and terminal.hold_time == 0


def test_a_connection_takes_time_then_gives_the_data(bus):
    from game.settings import TERMINAL_JOB_TIME

    tm, terminal, inv, system = make_terminal_world(bus)
    terminal.start("data")
    assert terminal.job.duration == TERMINAL_JOB_TIME["data"] == HACK_TIME and terminal.prompt(inv) is None  # déjà en cours
    outcomes = [terminal.advance(DT, center(2, 1)) for _ in range(round((HACK_TIME - 0.3) / DT))]
    assert set(outcomes) == {None} and 0.8 < terminal.job.progress < 1
    outcomes = [terminal.advance(DT, center(2, 1)) for _ in range(round(0.5 / DT))]
    assert "data" in outcomes and terminal.job is None


def test_walking_away_cuts_the_connection(bus):
    tm, terminal, inv, system = make_terminal_world(bus)
    terminal.start("data")
    for _ in range(round(1.0 / DT)):
        terminal.advance(DT, center(2, 1))
    assert terminal.advance(DT, center(6, 1)) == "lost" and terminal.job is None  # il faudra recommencer
    terminal.start("data")
    assert terminal.job.elapsed == 0


def test_a_data_only_terminal_has_nothing_left_once_emptied(bus):
    tm, terminal, inv, system = make_terminal_world(bus)
    terminal.hacked = True
    assert terminal.prompt(inv) is None


def test_a_terminal_with_other_powers_stays_usable(bus):
    tm, terminal, inv, system = make_terminal_world(bus, ("data", "lights"))
    terminal.hacked = True
    assert terminal.prompt(inv) is not None  # on peut encore couper la lumière
    assert make_terminal_world(bus, ("cameras",))[1].prompt(inv) is not None


def test_a_single_press_far_away_opens_nothing(bus):
    tm, terminal, inv, system = make_terminal_world(bus)
    rec = Recorder(bus, "terminal_opened")
    tick(system, tm, inv, [terminal], center(1, 1) - pygame.Vector2(30, 0), pressed=True)
    assert rec.events == []


# --- Sélection de la cible ---------------------------------------------------
def test_nearest_interactable_wins(bus):
    tm = Tilemap.from_text("#########\n#.......#\n#########")
    near, far = Terminal(*center(3, 1)), Terminal(*center(5, 1))
    system, inv = InteractionSystem(bus), Inventory()
    tick(system, tm, inv, [far, near], center(3, 1) + pygame.Vector2(4, 0))
    assert system.target is near
    tick(system, tm, inv, [far, near], center(5, 1) - pygame.Vector2(4, 0))
    assert system.target is far


def test_changing_target_resets_progress(bus):
    tm = Tilemap.from_text("#########\n#.......#\n#########")
    from game.entities.power_console import PowerConsole

    a, b = PowerConsole(*center(2, 1)), PowerConsole(*center(6, 1))  # une action maintenue : la console de la salle de contrôle
    system, inv = InteractionSystem(bus), Inventory()
    hold(system, tm, inv, [a, b], center(2, 1), 1.0)
    assert system.progress > 0.2
    tick(system, tm, inv, [a, b], center(6, 1), held=True)
    assert system.target is b and system.progress < 0.05


# --- Sortie ------------------------------------------------------------------
def test_exit_requires_the_data(bus):
    tm = Tilemap.from_text("#####\n#...#\n#####")
    pad, inv, system = ExitPad(*center(2, 1)), Inventory(), InteractionSystem(bus)
    rec = Recorder(bus, "interaction_denied", "mission_complete")
    tick(system, tm, inv, [pad], center(2, 1), pressed=True)
    assert rec.names() == ["interaction_denied"]
    assert not pad.is_ready(inv)

    inv.add(DATA)
    assert pad.is_ready(inv)
    tick(system, tm, inv, [pad], center(2, 1), pressed=True)
    assert rec.names() == ["interaction_denied", "mission_complete"]


# --- Objets ramassés ---------------------------------------------------------
def test_pickups_are_collected_by_touch(bus):
    inv = Inventory()
    rec = Recorder(bus, "item_picked")
    pickups = [Pickup(100, 100, KEY(2)), Pickup(300, 100, Item(ItemKind.DECOY))]
    collect_pickups(pygame.Vector2(110, 100), inv, pickups, bus)
    assert inv.has_keycard(2) and len(pickups) == 1
    assert rec.events[0][1]["item"] == KEY(2)
    collect_pickups(pygame.Vector2(110, 100), inv, pickups, bus)  # rien de plus à portée
    assert len(rec.events) == 1


def test_far_pickups_are_left_alone(bus):
    inv, pickups = Inventory(), [Pickup(100, 100, KEY(1))]
    collect_pickups(pygame.Vector2(200, 100), inv, pickups, bus)
    assert len(pickups) == 1 and inv.stacks() == []


# --- Leurre ------------------------------------------------------------------
def test_decoy_beeps_immediately_then_at_intervals_then_dies():
    decoy, beeps, frames = Decoy(0, 0), [], 0
    while not decoy.expired and frames < 60 * 20:
        decoy.update(DT)
        frames += 1
        if decoy.made_beep:
            beeps.append(frames * DT)
    assert beeps[0] <= DT * 1.5
    assert all(b - a == pytest.approx(DECOY_BEEP_INTERVAL, abs=0.03) for a, b in zip(beeps, beeps[1:]))
    assert len(beeps) == pytest.approx(DECOY_DURATION / DECOY_BEEP_INTERVAL, abs=1)
    decoy.update(DT)
    assert not decoy.made_beep  # une fois éteint, plus de bip
