"""Sprites du joueur et des gardes : dessin de dessus, orientation, postures, état d'alerte, animation de la marche."""

import math

import pygame
import pytest

from game.ai.guard import Guard, GuardState
from game.core.input import InputState
from game.entities.player import Player, Stance
from game.settings import COLORS, SPRITE_LEAN, SPRITE_SCALE, SPRITE_SWING, STRIDE_RATE
from game.ui.sprites import Frame, draw_guard, draw_player, swing
from game.world.tilemap import Tilemap

V = pygame.Vector2
BG = (52, 60, 78)
MAP = Tilemap.from_text("#" * 30 + "\n" + ("#" + "." * 28 + "#\n") * 5 + "#" * 30)


class Cam:
    @staticmethod
    def world_to_screen(p):
        return (60, 60)


def canvas():
    surface = pygame.Surface((120, 120))
    surface.fill(BG)
    return surface


def painted(surface):
    return pygame.mask.from_threshold(surface, BG, (1, 1, 1, 255)).count() < 120 * 120


def image(surface):
    return pygame.image.tobytes(surface, "RGB")


def extent(surface):
    """Rectangle englobant de tout ce qui n'est pas du fond."""
    mask = pygame.mask.from_threshold(surface, BG, (1, 1, 1, 255))
    mask.invert()
    rects = mask.get_bounding_rects()
    return rects[0].unionall(rects[1:]) if rects else pygame.Rect(0, 0, 0, 0)


# --- Le repère du personnage -----------------------------------------------------------------------------------------
def test_the_frame_points_where_the_character_looks():
    f = Frame((100, 100), (1, 0), scale=1.0)
    assert f.point(0, 0) == pytest.approx((100, 100))
    assert f.point(10, 0)[0] > 100 and f.point(10, 0)[1] == pytest.approx(100)  # devant
    assert f.point(0, 10)[1] > 100  # la droite d'un personnage qui regarde à l'est est le sud (l'écran va vers le bas)
    north = Frame((100, 100), (0, -1), scale=1.0)
    assert north.point(10, 0)[1] < 100 and north.point(0, 10)[0] > 100


def test_a_zero_direction_does_not_break_the_frame():
    assert Frame((5, 5), (0, 0)).forward == V(1, 0)


def test_the_frame_scales_the_character_around_its_center():
    small, big = Frame((50, 50), (1, 0), 0.5), Frame((50, 50), (1, 0), 1.0)
    assert V(small.point(10, 4)).distance_to((50, 50)) == pytest.approx(V(big.point(10, 4)).distance_to((50, 50)) * 0.5, rel=0.01)


def test_legs_swing_in_opposition():
    assert swing(1.0, 5, 1.0, 1) == pytest.approx(-swing(1.0, 5, 1.0, -1))
    assert swing(1.0, 5, 0.0, 1) == 0.0  # à l'arrêt, les jambes ne bougent pas
    assert swing(math.pi / 2, 5, 1.0, 1) == pytest.approx(5.0 * 1.0)


# --- Le joueur ---------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("stance", ["crouch", "walk", "run"])
def test_the_player_is_drawn_in_every_stance(stance):
    surface = canvas()
    draw_player(surface, (60, 60), (1, 0), stance, 0.7, 1.0)
    assert painted(surface)
    box = extent(surface)
    assert box.collidepoint(60, 60) and 14 <= box.w <= 40 and 14 <= box.h <= 40


def test_the_player_turns_to_face_any_direction():
    images = set()
    for angle in range(0, 360, 45):
        surface = canvas()
        draw_player(surface, (60, 60), (math.cos(math.radians(angle)), math.sin(math.radians(angle))), "walk")
        images.add(image(surface))
    assert len(images) == 8  # huit orientations, huit images


def test_the_stance_changes_the_look():
    pictures = {}
    for stance in ("crouch", "walk", "run"):
        surface = canvas()
        draw_player(surface, (60, 60), (1, 0), stance, 0.0, 0.0)
        pictures[stance] = surface
    assert len({image(s) for s in pictures.values()}) == 3
    assert extent(pictures["crouch"]).w < extent(pictures["walk"]).w  # accroupi, le personnage se tasse
    crouch_vest = pictures["crouch"].get_at((57, 60))[:3]
    assert pictures["walk"].get_at((57, 60))[:3] != crouch_vest  # et la couleur du gilet suit la posture


def test_the_vest_color_comes_from_the_stance_palette():
    for stance in ("crouch", "walk", "run"):
        surface = canvas()
        draw_player(surface, (60, 60), (1, 0), stance, 0.0, 0.0)
        colors = {surface.get_at((x, y))[:3] for x in range(40, 80) for y in range(40, 80)}
        assert COLORS[f"player_{stance}"] in colors


def test_the_walk_cycle_animates_the_player_but_a_standing_player_is_still():
    walking = {image(_player(phase, 1.0)) for phase in (0.0, 0.8, 1.6, 2.4, 3.2, 4.0)}
    assert len(walking) >= 5
    still = {image(_player(phase, 0.0)) for phase in (0.0, 1.0, 2.0)}
    assert len(still) == 1


def _player(phase, stride, stance="walk", time=0.0):
    surface = canvas()
    draw_player(surface, (60, 60), (1, 0), stance, phase, stride, time)
    return surface


def test_a_standing_player_breathes_slowly():
    assert image(_player(0, 0.0, time=0.0)) != image(_player(0, 0.0, time=0.65))


def test_running_swings_wider_than_walking():
    assert SPRITE_SWING["crouch"] < SPRITE_SWING["walk"] < SPRITE_SWING["run"]
    assert SPRITE_SCALE["crouch"] < SPRITE_SCALE["walk"] and SPRITE_LEAN["run"] > SPRITE_LEAN["walk"]
    spread = {s: extent(_player(math.pi / 2, 1.0, s)).w for s in ("walk", "run")}
    assert spread["run"] >= spread["walk"]


def test_the_player_sprite_stays_close_to_its_hitbox():
    box = extent(_player(1.0, 1.0))
    assert box.w <= 36 and box.h <= 36  # un personnage de 22 px de côté (collision) ne déborde pas beaucoup de sa boîte


def test_drawing_never_touches_pixels_far_from_the_character():
    surface = _player(1.0, 1.0)
    assert surface.get_at((5, 5))[:3] == BG and surface.get_at((115, 115))[:3] == BG


# --- Le garde ---------------------------------------------------------------------------------------------------------------------
def guard_image(state=GuardState.PATROL, facing=(1, 0), **kw):
    surface = canvas()
    draw_guard(surface, (60, 60), facing, COLORS[f"guard_{state.value}"], **kw)
    return surface


def test_the_guard_is_drawn_in_white_armor():
    surface = guard_image()
    colors = {surface.get_at((x, y))[:3] for x in range(40, 80) for y in range(40, 80)}
    assert COLORS["armor_white"] in colors and COLORS["guard_visor"] in colors and COLORS["guard_gun"] in colors


@pytest.mark.parametrize("state", [GuardState.PATROL, GuardState.INVESTIGATE, GuardState.CHASE])
def test_the_alert_state_shows_on_the_armor(state):
    surface = guard_image(state)
    colors = {surface.get_at((x, y))[:3] for x in range(40, 80) for y in range(40, 80)}
    assert COLORS[f"guard_{state.value}"] in colors  # liseré, épaulette et œil de la visière


def test_each_state_looks_different():
    pictures = {image(guard_image(state)) for state in (GuardState.PATROL, GuardState.INVESTIGATE, GuardState.CHASE)}
    assert len(pictures) == 3


def test_a_chasing_guard_shoulders_the_rifle():
    calm, aiming = guard_image(aiming=False), guard_image(aiming=True)
    assert image(calm) != image(aiming)
    assert extent(aiming).w >= extent(calm).w  # le fusil est plus avancé


def test_the_guard_turns_to_face_any_direction():
    images = {image(guard_image(facing=(math.cos(a), math.sin(a)))) for a in [i * math.pi / 4 for i in range(8)]}
    assert len(images) == 8


def test_the_guard_walk_cycle_and_the_reinforcement_band():
    steps = {image(guard_image(phase=p, stride=1.0)) for p in (0.0, 0.9, 1.8, 2.7)}
    assert len(steps) >= 3
    assert image(guard_image(reinforcement=True)) != image(guard_image(reinforcement=False))
    band = guard_image(reinforcement=True)
    assert COLORS["guard_reinforcement"] in {band.get_at((x, y))[:3] for x in range(45, 70) for y in range(50, 70)}


def test_the_guard_sprite_stays_inside_its_ring():
    box = extent(guard_image(stride=1.0, phase=1.0))
    assert box.w <= 40 and box.h <= 40


# --- Animation des entités --------------------------------------------------------------------------------------------------------
def test_the_player_cycle_advances_with_the_distance_walked():
    player = Player(100, 100)
    walking = InputState(move=V(1, 0))
    for _ in range(30):
        player.update(1 / 60, MAP, walking)
    walked = player.pos.x - 100
    assert player.walk_phase == pytest.approx((walked * STRIDE_RATE) % math.tau, abs=0.05) and player.stride > 0.9


def test_a_faster_pace_covers_more_ground_and_more_cycles_per_second():
    def cycles(inp):
        player = Player(100, 100)
        start = V(player.pos)
        for _ in range(20):
            player.update(1 / 60, MAP, inp)
        return player.pos.distance_to(start) * STRIDE_RATE  # la phase avance avec la distance : on la lit sans le repli de 2 pi

    assert cycles(InputState(move=V(1, 0), run=True)) > cycles(InputState(move=V(1, 0))) > cycles(InputState(move=V(1, 0), crouch=True)) > 0


def test_the_player_stops_stepping_when_blocked_by_a_wall():
    player = Player(46, 100)  # collé au mur de droite... le mur de gauche est à x = 32
    player.pos.update(32 + 11 + 0.0, 100)
    before = player.walk_phase
    for _ in range(30):
        player.update(1 / 60, MAP, InputState(move=V(-1, 0)))
    assert player.walk_phase == pytest.approx(before, abs=0.5)  # il piétine à peine : la foulée suit la distance réellement parcourue


def test_the_legs_freeze_smoothly_when_the_player_stops():
    player = Player(100, 100)
    for _ in range(20):
        player.update(1 / 60, MAP, InputState(move=V(1, 0)))
    assert player.stride > 0.9
    player.update(1 / 60, MAP, InputState())
    assert 0.5 < player.stride < 0.95  # pas d'arrêt net
    for _ in range(40):
        player.update(1 / 60, MAP, InputState())
    assert player.stride < 0.05


def test_the_player_draws_through_the_entity():
    surface = canvas()
    player = Player(0, 0)
    player.facing = V(0, 1)
    player.update(1 / 60, MAP, InputState())
    player.draw(surface, Cam)
    assert painted(surface)
    player.stance = Stance.CROUCH
    other = canvas()
    player.draw(other, Cam)
    assert image(surface) != image(other)


def make_guard(tile=(3, 3), route=None):
    class S:
        kind, level = "guard", 0

    S.tx, S.ty = tile
    return Guard.from_spawn(MAP, S)


def test_a_patrolling_guard_walks_with_a_cycle_and_a_waiting_guard_stands():
    class Far:
        pos = V(2000, 2000)
        detectability = 1.0

    tm = Tilemap.from_text("#" * 30 + "\n#G" + "." * 27 + "#\n#" + "." * 28 + "#\n#.G" + "." * 26 + "#\n" + "#" * 30 + "\n@patrol 1,1 -> 20,1\n")
    walker, sentry = (Guard.from_spawn(tm, s) for s in tm.spawns_of("guard"))
    for _ in range(60):
        walker.update(1 / 60, tm, Far())
        sentry.update(1 / 60, tm, Far())
    assert walker.walk_phase > 0 and walker.stride > 0.5  # il marche : jambes et bras balancent
    assert sentry.stride < 0.05 and sentry.walk_phase == 0.0  # la sentinelle, immobile, ne piétine pas


def test_the_guard_draws_its_state_and_aims_when_chasing():
    guard = make_guard()
    surface = canvas()
    guard.draw(surface, Cam)
    calm = image(surface)
    guard.state = GuardState.CHASE
    chase = canvas()
    guard.draw(chase, Cam)
    assert image(chase) != calm
    assert COLORS["guard_chase"] in {chase.get_at((x, y))[:3] for x in range(40, 80) for y in range(40, 80)}


def test_the_scene_draws_the_new_sprites(game, monkeypatch):
    from game.scenes import play_scene
    from tests.paths import CAMPAIGN

    monkeypatch.setattr(play_scene, "read_input", lambda: InputState(move=V(1, 0), run=True))
    mission = CAMPAIGN.get("training")
    scene = play_scene.PlayScene(game, mission.map_path, mission)
    game.scenes.push(scene)
    for _ in range(40):
        game.step(1 / 60)
    assert scene.player.stride > 0.5 and scene.player.walk_phase > 0
    assert any(g.stride > 0.5 for g in scene.guards)  # le garde de l'entraînement patrouille
