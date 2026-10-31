import pygame
import pytest

from game.ai.guard import Guard, GuardState
from game.core.events import EventBus
from game.entities.player import Player
from game.settings import (
    ALERT_RESPONDERS,
    LOCKDOWN_TIME,
    RADIO_INTERVAL,
    REINFORCE_FIRST_DELAY,
    REINFORCE_INTERVAL,
    REINFORCE_PER_WAVE,
    REINFORCE_WAVES,
)
from game.systems.alert import AlertSystem, choose_spawns
from game.world.tilemap import Tilemap

DT = 1 / 20

# Couloir de 60 tuiles (assez long pour que les extrémités soient hors écran), plus une salle isolée.
HALL = Tilemap.from_text("#" * 64 + "\n#" + "." * 62 + "#\n#" + "." * 62 + "#\n" + "#" * 64)
BENT = Tilemap.from_text(  # un coude : (1,1) ne voit pas (14,6)
    """\
###############
#.............#
#######.#######
#######.#######
#######.#######
#######.#######
#.............#
###############"""
)
SEALED = Tilemap.from_text("#########\n#...#...#\n#...#...#\n#########")


def center(tx, ty):
    return pygame.Vector2((tx + 0.5) * 32, (ty + 0.5) * 32)


def guard_at(tx, ty):
    return Guard([center(tx, ty)], 0.0)


def player_at(tx, ty):
    return Player(*center(tx, ty))


class Events:
    def __init__(self, bus, *names):
        self.log = []
        for name in names:
            bus.subscribe(name, lambda _n=name, **payload: self.log.append((_n, payload)))

    def names(self):
        return [n for n, _ in self.log]


def make(tilemap=HALL, spawns=((2, 1), (61, 1)), post=(30, 1)):
    bus = EventBus()
    return AlertSystem(bus, tilemap, list(spawns), post), bus


def run(system, guards, player, seconds, dt=DT):
    arrivals = []
    for _ in range(round(seconds / dt)):
        arrivals += system.update(dt, guards, player)
    return arrivals


# --- Déclenchement -----------------------------------------------------------
def test_calm_world_stays_calm():
    system, bus = make()
    log = Events(bus, "alert_raised", "lockdown", "reinforcements_arrived")
    guards, player = [guard_at(5, 1)], player_at(30, 1)
    assert run(system, guards, player, 20) == []
    assert not system.active and log.log == []


def test_investigating_guard_does_not_raise_the_alarm():
    system, bus = make()
    guard = guard_at(5, 1)
    guard.hear(HALL, center(9, 1), 400)
    assert guard.state is GuardState.INVESTIGATE
    run(system, [guard], player_at(30, 1), 5)
    assert not system.active


def test_first_chase_raises_the_alert_once():
    system, bus = make()
    log = Events(bus, "alert_raised")
    guards, player = [guard_at(5, 1), guard_at(9, 1)], player_at(30, 1)
    guards[0]._start_chase(player)
    system.update(DT, guards, player)
    assert system.active and system.time_left == LOCKDOWN_TIME
    assert log.names() == ["alert_raised"]
    assert log.log[0][1]["pos"] == player.pos
    assert all(g.alerted for g in guards)
    run(system, guards, player, 3)
    assert log.names() == ["alert_raised"]  # une seule fois


def test_alert_never_stands_down():
    system, bus = make()
    guards, player = [guard_at(5, 1)], player_at(30, 1)
    guards[0]._start_chase(player)
    system.update(DT, guards, player)
    guards[0].state = GuardState.PATROL
    run(system, guards, player, 30)
    assert system.active


# --- Chronomètre -------------------------------------------------------------
def test_countdown_runs_and_lockdown_fires_once():
    system, bus = make()
    log = Events(bus, "lockdown")
    guards, player = [guard_at(5, 1)], player_at(30, 1)
    guards[0]._start_chase(player)
    system.update(DT, guards, player)
    run(system, guards, player, 10)
    assert system.time_left == pytest.approx(LOCKDOWN_TIME - 10, abs=0.2)
    assert not system.locked_down
    run(system, guards, player, LOCKDOWN_TIME)
    assert system.locked_down and system.time_left == 0
    assert log.names() == ["lockdown"]
    run(system, guards, player, 5)
    assert log.names() == ["lockdown"]


def test_no_reinforcements_after_lockdown():
    system, bus = make()
    guards, player = [guard_at(5, 1)], player_at(30, 1)
    guards[0]._start_chase(player)
    system.update(DT, guards, player)
    system.time_left = 0.01
    assert system.update(1.0, guards, player) == []
    assert system.locked_down
    assert run(system, guards, player, 60) == []


# --- Radio -------------------------------------------------------------------
def test_alert_dispatches_only_the_nearest_responders():
    system, bus = make()
    guards = [guard_at(x, 1) for x in (8, 12, 16, 40, 50)]
    chaser = guard_at(30, 1)
    chaser._start_chase(player_at(31, 1))
    system.update(DT, [chaser, *guards], player_at(31, 1))
    states = [g.state for g in guards]
    assert states.count(GuardState.INVESTIGATE) == ALERT_RESPONDERS
    # Les plus proches du joueur (30) : x = 40, 16, 12.
    assert guards[3].state is guards[2].state is guards[1].state is GuardState.INVESTIGATE
    assert guards[0].state is guards[4].state is GuardState.PATROL
    assert chaser.state is GuardState.CHASE  # un garde en poursuite ne reçoit pas d'ordre


def test_radio_follows_the_player_but_is_rate_limited(monkeypatch):
    system, bus = make()
    seen_by, player = guard_at(5, 1), player_at(30, 1)
    seen_by._start_chase(player)
    system.update(DT, [seen_by], player)
    calls = []
    other = guard_at(20, 1)
    monkeypatch.setattr(Guard, "alarm", lambda self, tm, pos: (self is other and calls.append(pygame.Vector2(pos))) or True)
    for _ in range(round(10 / DT)):  # 10 s en vue
        player.pos.x += 0.5
        seen_by.sees_target = True
        system.update(DT, [seen_by, other], player)
    assert 10 / RADIO_INTERVAL - 1 <= len(calls) <= 10 / RADIO_INTERVAL + 1
    assert calls[-1].x > calls[0].x  # le message suit le joueur
    assert system.last_known.distance_to(player.pos) < 20


def test_no_radio_when_nobody_sees_the_player(monkeypatch):
    system, bus = make()
    guard, player = guard_at(5, 1), player_at(30, 1)
    guard._start_chase(player)
    system.update(DT, [guard], player)
    guard.sees_target = False
    calls = []
    monkeypatch.setattr(Guard, "alarm", lambda self, tm, pos: calls.append(pos) or True)
    run(system, [guard, guard_at(9, 1)], player, 5)
    assert calls == []


# --- Renforts ----------------------------------------------------------------
def alerted_system(player, guards):
    system, bus = make()
    guards[0]._start_chase(player)
    system.update(DT, guards, player)
    return system, bus


def test_first_wave_arrives_after_the_delay_and_hunts_the_player():
    player, guards = player_at(30, 1), [guard_at(5, 1)]
    system, bus = alerted_system(player, guards)
    log = Events(bus, "reinforcements_arrived")
    assert run(system, guards, player, REINFORCE_FIRST_DELAY - 1) == []
    arrivals = run(system, guards, player, 2)
    assert len(arrivals) == REINFORCE_PER_WAVE
    assert log.log == [("reinforcements_arrived", {"count": REINFORCE_PER_WAVE})]
    for guard in arrivals:
        assert guard.is_reinforcement and guard.alerted
        assert guard.state is GuardState.INVESTIGATE  # briefés sur la dernière position connue
        assert guard.destination.distance_to(player.pos) < 40
    spots = {(int(g.route[0].x // 32), int(g.route[0].y // 32)) for g in arrivals}
    assert spots <= {(2, 1), (61, 1)}  # un point d'arrivée de la carte


def test_waves_stop_after_the_planned_number():
    player, guards = player_at(30, 1), [guard_at(5, 1)]
    system, bus = alerted_system(player, guards)
    waves = []
    for _ in range(round((REINFORCE_FIRST_DELAY + REINFORCE_INTERVAL * (REINFORCE_WAVES + 3)) / DT)):
        arrivals = system.update(DT, guards, player)
        if arrivals:
            waves.append(len(arrivals))
            guards.extend(arrivals)
    assert len(waves) == REINFORCE_WAVES == system.waves
    assert sum(waves) == REINFORCE_WAVES * REINFORCE_PER_WAVE
    assert waves[0] == REINFORCE_PER_WAVE


def test_simultaneous_reinforcements_are_capped(monkeypatch):
    import game.systems.alert as alert_module

    monkeypatch.setattr(alert_module, "REINFORCE_MAX", 1)
    player, guards = player_at(30, 1), [guard_at(5, 1)]
    system, bus = alerted_system(player, guards)
    for _ in range(round((REINFORCE_FIRST_DELAY + REINFORCE_INTERVAL * 3) / DT)):
        guards.extend(system.update(DT, guards, player))
    assert sum(g.is_reinforcement for g in guards) == 1  # les suivants attendent qu'une place se libère


def test_wave_spacing():
    player, guards = player_at(30, 1), [guard_at(5, 1)]
    system, bus = alerted_system(player, guards)
    times, t = [], 0.0
    for _ in range(round(80 / DT)):
        t += DT
        arrivals = system.update(DT, guards, player)
        if arrivals:
            times.append(t)
            guards.extend(arrivals)
    assert times[0] == pytest.approx(REINFORCE_FIRST_DELAY, abs=0.2)
    assert times[1] - times[0] == pytest.approx(REINFORCE_INTERVAL, abs=0.2)


def test_failed_wave_is_retried_quickly():
    """Joueur trop près de tous les points d'arrivée : rien n'arrive, mais on réessaie vite, pas 25 s plus tard."""
    player, guards = player_at(3, 1), [guard_at(5, 1)]
    system, bus = alerted_system(player, guards)
    system.reinforcement_tiles = [(2, 1)]  # à 1 tuile du joueur
    assert run(system, guards, player, REINFORCE_FIRST_DELAY + 1) == []
    player.pos.update(center(40, 1))  # il s'éloigne
    arrivals = run(system, guards, player, RADIO_INTERVAL + 0.5)
    assert len(arrivals) == 1


def test_no_arrival_without_a_post():
    system, bus = make(post=None)
    player, guards = player_at(30, 1), [guard_at(5, 1)]
    guards[0]._start_chase(player)
    system.update(DT, guards, player)
    assert run(system, guards, player, 30) == []


# --- Choix des points d'arrivée ---------------------------------------------
def test_spawns_too_close_are_rejected_even_when_hidden():
    # (1, 1) est caché par le mur (aucune vue directe sur le joueur) mais à ~7 tuiles seulement : trop près.
    assert choose_spawns(BENT, [(1, 1)], center(7, 5), 5) == []


def test_spawns_in_view_are_rejected_but_far_ones_are_fine():
    # À 5 tuiles (160 px) en vue directe : refusé ; à 28 tuiles (> écran) : accepté même en ligne droite.
    assert choose_spawns(HALL, [(35, 1)], center(30, 1), 5) == []
    assert choose_spawns(HALL, [(61, 1)], center(30, 1), 5) == [(61, 1)]


def test_spawns_hidden_by_a_corner_are_accepted():
    near_but_hidden = (1, 1)
    assert choose_spawns(BENT, [near_but_hidden], center(13, 6), 5) == [near_but_hidden]  # >10 tuiles, coin entre les deux


def test_unreachable_spawns_are_rejected():
    assert choose_spawns(SEALED, [(6, 1)], center(1, 1), 5) == []


def test_spawns_are_nearest_first_and_limited():
    tiles = [(61, 1), (2, 1), (56, 2)]  # à 30, 29 et 25 tuiles du joueur
    assert choose_spawns(HALL, tiles, center(31, 1), 2) == [(56, 2), (2, 1)]
    assert choose_spawns(HALL, tiles, center(31, 1), 9) == [(56, 2), (2, 1), (61, 1)]
