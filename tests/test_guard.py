import pygame
import pytest

from game.ai.guard import Guard, GuardState
from game.entities.player import Player
from game.settings import (
    GUARD_AWARENESS_DECAY,
    GUARD_LOSE_SIGHT_TIME,
    GUARD_SEARCH_TIME,
    GUARD_WAIT_TIME,
)
from game.world.tilemap import Tilemap

DT = 1 / 60

# Long couloir (14 tuiles) : le garde à gauche regarde vers l'est.
HALL = Tilemap.from_text("################\n#..............#\n#..............#\n################")
# Deux salles reliées par une ouverture en (7, 2), et une salle scellée à droite.
ROOMS = Tilemap.from_text(
    """\
################
#......#.......#
#..............#
#......#.......#
################"""
)
SEALED = Tilemap.from_text("#########\n#...#...#\n#...#...#\n#########")


def tile_center(tx, ty):
    return pygame.Vector2((tx + 0.5) * 32, (ty + 0.5) * 32)


def make_guard(*tiles, angle=0.0):
    return Guard([tile_center(*t) for t in tiles], angle)


def make_player(tx, ty, **kwargs):
    return Player(*tile_center(tx, ty))


def run(guard, tilemap, seconds, target=None):
    for _ in range(round(seconds / DT)):
        guard.update(DT, tilemap, target)


# --- Patrouille --------------------------------------------------------------
def test_guard_starts_at_its_post_on_patrol():
    guard = make_guard((1, 1), (8, 1))
    assert guard.pos == tile_center(1, 1)
    assert guard.state is GuardState.PATROL and guard.awareness == 0


def test_guard_needs_a_route():
    with pytest.raises(ValueError):
        Guard([])


def test_patrol_visits_every_waypoint_in_a_loop():
    guard = make_guard((1, 1), (8, 1), (8, 2))
    visited = set()
    for _ in range(60 * 40):
        guard.update(DT, HALL)
        visited.add(guard.route_index)
    assert visited == {0, 1, 2}
    # Après un tour complet il est revenu vers son poste.
    assert guard.state is GuardState.PATROL


def test_patrol_pauses_at_each_waypoint():
    guard = make_guard((1, 1), (3, 1))
    run(guard, HALL, 1.2)  # 64 px à 70 px/s : arrivé en ~0,9 s, en pleine pause
    assert guard.pos.distance_to(tile_center(3, 1)) < 5
    before = guard.pos.copy()
    run(guard, HALL, GUARD_WAIT_TIME / 3)
    assert guard.pos == before
    run(guard, HALL, GUARD_WAIT_TIME)  # la pause est finie : il repart vers son poste
    assert guard.pos.x < before.x


def test_patrol_speed_is_slower_than_player_walk():
    guard = make_guard((1, 1), (14, 1))
    run(guard, HALL, 1.0)
    assert 0 < guard.pos.x - tile_center(1, 1).x < 150


def test_guard_turns_towards_its_direction_of_travel():
    guard = make_guard((1, 1), (1, 2), angle=0.0)
    run(guard, HALL, 0.6)
    assert guard.facing.y > 0.9


def test_sentry_stays_put_and_keeps_its_gaze():
    guard = make_guard((3, 1), angle=0.0)
    run(guard, HALL, 5.0)
    assert guard.pos == tile_center(3, 1)
    assert guard.angle == pytest.approx(0.0)


def test_from_spawn_uses_the_map_route():
    tm = Tilemap.from_text("########\n#G.....#\n########\n@patrol 1,1 -> 6,1\n")
    guard = Guard.from_spawn(tm, tm.spawns_of("guard")[0])
    assert guard.route == [tile_center(1, 1), tile_center(6, 1)]
    assert guard.angle == pytest.approx(0.0)


def test_sentry_from_spawn_faces_the_most_open_direction():
    tm = Tilemap.from_text("#########\n#G......#\n#########")
    guard = Guard.from_spawn(tm, tm.spawns_of("guard")[0])
    assert len(guard.route) == 1
    assert guard.angle == pytest.approx(0.0)


# --- Vue ---------------------------------------------------------------------
def test_awareness_grows_while_player_is_in_view_then_chase():
    guard = make_guard((1, 1))
    player = make_player(6, 1)
    run(guard, HALL, 0.2, player)
    assert guard.sees_target and 0 < guard.awareness < 1
    assert guard.state is GuardState.PATROL
    run(guard, HALL, 2.0, player)
    assert guard.state is GuardState.CHASE and guard.awareness == 1


def test_guard_freezes_and_stares_while_unsure():
    guard = make_guard((1, 1), (14, 1), angle=0.0)
    player = make_player(5, 1)
    run(guard, HALL, 0.15, player)
    assert guard.state is GuardState.PATROL and guard.awareness > 0
    assert guard.pos == tile_center(1, 1)  # il n'a pas bougé


def test_closer_and_noisier_means_faster_detection():
    def awareness_after(tx, stance_input):
        guard, player = make_guard((1, 1)), make_player(tx, 1)
        player.stance = stance_input
        run(guard, HALL, 0.2, player)
        return guard.awareness

    from game.entities.player import Stance

    assert awareness_after(3, Stance.WALK) > awareness_after(6, Stance.WALK)
    assert awareness_after(5, Stance.CROUCH) < awareness_after(5, Stance.WALK) < awareness_after(5, Stance.RUN)


def test_player_behind_the_guard_is_not_seen():
    guard = make_guard((8, 1), angle=0.0)
    run(guard, HALL, 3.0, make_player(2, 1))
    assert not guard.sees_target and guard.awareness == 0


def test_player_out_of_range_is_not_seen():
    guard = make_guard((1, 1), angle=0.0)
    run(guard, HALL, 1.0, make_player(14, 1))  # ~13 tuiles : au-delà de la portée de 7
    assert guard.awareness == 0


def test_walls_hide_the_player():
    guard = make_guard((1, 1), angle=0.0)
    run(guard, SEALED, 2.0, make_player(6, 1))
    assert guard.awareness == 0 and guard.state is GuardState.PATROL


def test_awareness_decays_when_contact_is_lost():
    guard = make_guard((1, 1))
    run(guard, HALL, 0.3, make_player(4, 1))
    raised = guard.awareness
    assert raised > 0
    run(guard, HALL, 0.3, None)
    assert guard.awareness == pytest.approx(max(0.0, raised - GUARD_AWARENESS_DECAY * 0.3), abs=0.03)
    run(guard, HALL, 5.0, None)
    assert guard.awareness == 0


# --- Poursuite ---------------------------------------------------------------
def chasing_guard():
    guard = make_guard((1, 1))
    player = make_player(5, 1)
    run(guard, HALL, 3.0, player)
    assert guard.state is GuardState.CHASE
    return guard, player


def test_chase_closes_in_and_catches():
    guard, player = chasing_guard()
    caught = False
    for _ in range(60 * 3):
        guard.update(DT, HALL, player)
        caught = caught or guard.can_catch(player)
    assert caught


def test_only_a_chasing_guard_can_catch():
    guard = make_guard((1, 1))
    player = make_player(1, 1)
    assert guard.pos.distance_to(player.pos) == 0
    assert not guard.can_catch(player)


def test_chase_outpaces_walking_but_not_running():
    guard, player = chasing_guard()
    # À l'arrêt le garde rattrape ; vitesse de poursuite (185) entre marche (150) et course (240).
    from game.settings import GUARD_SPEED, PLAYER_SPEED

    assert PLAYER_SPEED["walk"] < GUARD_SPEED["chase"] < PLAYER_SPEED["run"]


def test_chase_follows_around_a_corner_with_astar():
    guard = make_guard((1, 1), angle=0.0)
    player = make_player(10, 3)
    # Joueur dans l'autre salle, mais visible en ligne droite par l'ouverture : on force la poursuite.
    guard._start_chase(player)
    for _ in range(60 * 6):
        guard.update(DT, ROOMS, player)
        if guard.can_catch(player):
            break
    assert guard.can_catch(player)


def test_guard_gives_up_and_investigates_last_known_position():
    guard, player = chasing_guard()
    last = pygame.Vector2(player.pos)
    player.pos.update(*tile_center(1, 2))  # il se glisse derrière le garde, hors du cône
    guard.angle = 0.0
    guard.pos.update(*tile_center(10, 1))
    run(guard, HALL, GUARD_LOSE_SIGHT_TIME + 0.2, player)
    assert guard.state is GuardState.INVESTIGATE
    assert guard.destination.distance_to(last) < 40
    assert 0 < guard.awareness < 1


def test_investigation_ends_in_search_then_back_to_patrol():
    guard = make_guard((1, 1), (10, 1))
    assert guard.hear(HALL, tile_center(6, 2), 400)
    assert guard.state is GuardState.INVESTIGATE
    run(guard, HALL, 4.0)
    assert guard.state is GuardState.SEARCH
    run(guard, HALL, GUARD_SEARCH_TIME + 0.2)
    assert guard.state is GuardState.PATROL


# --- Ouïe --------------------------------------------------------------------
def test_noise_in_range_starts_an_investigation():
    guard = make_guard((1, 1))
    assert guard.hear(HALL, tile_center(4, 1), 120)
    assert guard.state is GuardState.INVESTIGATE
    assert guard.destination == tile_center(4, 1)


def test_guard_walks_to_the_noise_and_searches_there():
    guard = make_guard((1, 1))
    guard.hear(HALL, tile_center(5, 2), 200)
    run(guard, HALL, 4.0)
    assert guard.state is GuardState.SEARCH
    assert guard.pos.distance_to(tile_center(5, 2)) < 10


def test_noise_out_of_range_is_ignored():
    guard = make_guard((1, 1))
    assert not guard.hear(HALL, tile_center(10, 1), 96)
    assert guard.state is GuardState.PATROL


def test_noise_from_sealed_area_is_heard_but_cannot_be_reached():
    guard = make_guard((1, 1))
    assert not guard.hear(SEALED, tile_center(5, 1), 400)  # pas de chemin : il ne bouge pas
    assert guard.state is GuardState.PATROL


def test_chasing_guard_ignores_noise():
    guard = make_guard((1, 1))
    guard._start_chase(None)
    assert not guard.hear(HALL, tile_center(3, 1), 400)
    assert guard.state is GuardState.CHASE


def test_new_noise_redirects_the_investigation():
    guard = make_guard((1, 1))
    guard.hear(HALL, tile_center(5, 1), 400)
    run(guard, HALL, 0.3)
    guard.hear(HALL, tile_center(12, 2), 600)
    assert guard.destination == tile_center(12, 2)


def test_repeated_noise_at_same_spot_does_not_restart_the_path():
    guard = make_guard((1, 1))
    guard.hear(HALL, tile_center(8, 1), 400)
    run(guard, HALL, 0.5)
    path_before = list(guard.follower.waypoints)
    assert guard.hear(HALL, tile_center(8, 1) + pygame.Vector2(5, 0), 400)
    assert list(guard.follower.waypoints) == path_before


def test_noise_interrupts_a_search():
    guard = make_guard((1, 1))
    guard.hear(HALL, tile_center(3, 1), 400)
    run(guard, HALL, 2.0)
    assert guard.state is GuardState.SEARCH
    guard.hear(HALL, tile_center(10, 1), 800)
    assert guard.state is GuardState.INVESTIGATE


def test_threat_levels_are_ordered():
    assert GuardState.PATROL.threat < GuardState.INVESTIGATE.threat == GuardState.SEARCH.threat < GuardState.CHASE.threat


def test_guard_never_enters_walls():
    guard = make_guard((1, 1), (14, 2), (1, 2))
    for _ in range(60 * 30):
        guard.update(DT, HALL)
        tx, ty = HALL.world_to_tile(*guard.pos)
        assert not HALL.is_solid(tx, ty)


# --- Alerte globale ----------------------------------------------------------
def test_alarm_sends_the_guard_to_the_reported_position():
    guard = make_guard((1, 1))
    assert guard.alarm(HALL, tile_center(9, 1))
    assert guard.state is GuardState.INVESTIGATE
    assert guard.destination == tile_center(9, 1)


def test_alarm_does_not_interrupt_a_chase_and_ignores_unreachable_places():
    guard = make_guard((1, 1))
    assert not guard.alarm(SEALED, tile_center(5, 1))  # zone fermée
    guard._start_chase(None)
    assert not guard.alarm(HALL, tile_center(9, 1))
    assert guard.state is GuardState.CHASE


def test_alert_makes_patrols_faster():
    calm, alerted = make_guard((1, 1), (14, 1)), make_guard((1, 1), (14, 1))
    alerted.alerted = True
    run(calm, HALL, 1.0)
    run(alerted, HALL, 1.0)
    walked = lambda g: g.pos.x - tile_center(1, 1).x  # noqa: E731
    assert walked(alerted) == pytest.approx(walked(calm) * 1.25, rel=0.08)


def test_alert_does_not_change_chase_speed():
    from game.settings import ALERT_SPEED_MULT, GUARD_SPEED

    guard = make_guard((1, 1))
    guard.alerted = True
    assert guard._speed("chase") == GUARD_SPEED["chase"]
    assert guard._speed("patrol") == GUARD_SPEED["patrol"] * ALERT_SPEED_MULT


def test_alerted_guards_spot_the_player_faster():
    def awareness(alerted):
        guard, player = make_guard((1, 1)), make_player(6, 1)
        guard.alerted = alerted
        run(guard, HALL, 0.2, player)
        return guard.awareness

    assert awareness(True) == pytest.approx(awareness(False) * 1.5, rel=0.05)


def test_reinforcement_hunts_then_guards_the_post():
    guard = Guard.reinforcement(HALL, (1, 1), (12, 1))
    assert guard.is_reinforcement and guard.alerted
    assert guard.pos == tile_center(1, 1)
    assert guard.route == [tile_center(1, 1), tile_center(12, 1)]
    guard.alarm(HALL, tile_center(5, 2))
    run(guard, HALL, 2.0)  # ~4 tuiles à 137 px/s : arrivé, il fouille
    assert guard.state is GuardState.SEARCH
    run(guard, HALL, GUARD_SEARCH_TIME + 6)
    assert guard.state is GuardState.PATROL
    assert guard.pos.x > tile_center(5, 1).x  # il file vers son poste


def test_reinforcement_is_drawn_with_its_ring():
    pygame.display.init()
    surface = pygame.Surface((100, 100))

    class Cam:
        @staticmethod
        def world_to_screen(p):
            return (50, 50)

    guard = Guard.reinforcement(HALL, (1, 1), (5, 1))
    guard.draw(surface, Cam)
    assert surface.get_at((50 + 13, 50))[:3] != (0, 0, 0)  # l'anneau est dessiné autour du corps
    plain = pygame.Surface((100, 100))
    make_guard((1, 1)).draw(plain, Cam)
    assert plain.get_at((50 + 13, 50))[:3] == (0, 0, 0)


def test_reinforcement_leaves_after_its_stay():
    from game.settings import REINFORCE_STAY_TIME

    guard = Guard.reinforcement(HALL, (1, 1), (12, 1))
    assert guard.lifetime == REINFORCE_STAY_TIME and not guard.expired
    run(guard, HALL, REINFORCE_STAY_TIME - 1)
    assert not guard.expired
    run(guard, HALL, 1.5)
    assert guard.expired


def test_regular_guards_never_expire():
    guard = make_guard((1, 1))
    run(guard, HALL, 600)
    assert guard.lifetime is None and not guard.expired


def test_a_chasing_reinforcement_does_not_vanish():
    guard = Guard.reinforcement(HALL, (1, 1), (12, 1))
    guard._start_chase(make_player(8, 1))
    guard.lifetime = 0.0
    assert not guard.expired  # on ne disparaît pas sous le nez du joueur en pleine poursuite
    guard.state = GuardState.PATROL
    assert guard.expired
