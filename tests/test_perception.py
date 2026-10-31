import math

import pygame
import pytest

from game.ai.perception import can_see, hears, most_open_angle, vision_points
from game.world.tilemap import Tilemap

HALL = Tilemap.from_text(
    """\
###########
#.........#
#....#....#
#.........#
###########"""
)
FOV = math.radians(90)
EYE = pygame.Vector2(48, 48)  # tuile (1, 1)


def test_sees_in_front_within_range():
    assert can_see(HALL, EYE, 0.0, FOV, 200, (150, 48))


def test_does_not_see_beyond_range():
    assert not can_see(HALL, EYE, 0.0, FOV, 90, (150, 48))


def test_does_not_see_behind_or_outside_the_cone():
    assert not can_see(HALL, (150, 48), 0.0, FOV, 400, (48, 48))  # derrière
    assert not can_see(HALL, EYE, 0.0, FOV, 400, (70, 110))  # ~70° de l'axe : hors du cône de 90°


def test_cone_edge():
    inside = EYE + pygame.Vector2(math.cos(math.radians(40)), math.sin(math.radians(40))) * 60
    outside = EYE + pygame.Vector2(math.cos(math.radians(50)), math.sin(math.radians(50))) * 60
    assert can_see(HALL, EYE, 0.0, FOV, 200, inside)
    assert not can_see(HALL, EYE, 0.0, FOV, 200, outside)


def test_wall_blocks_sight():
    # Pilier en (5, 2) : de (48, 80) à (272, 80) la ligne passe par lui.
    assert not can_see(HALL, (48, 80), 0.0, FOV, 400, (272, 80))
    assert can_see(HALL, (48, 48), 0.0, FOV, 400, (272, 48))


def test_cone_wraps_around_pi():
    assert can_see(HALL, (150, 48), math.pi, FOV, 400, (48, 48))
    assert can_see(HALL, (150, 48), -math.pi, FOV, 400, (48, 48))


def test_sees_point_on_itself():
    assert can_see(HALL, EYE, 0.0, FOV, 100, EYE)


# --- Ouïe --------------------------------------------------------------------
def test_hears_within_radius_only():
    assert hears(HALL, (48, 48), (112, 48), 96)
    assert not hears(HALL, (48, 48), (112, 48), 50)


def test_silence_is_never_heard():
    assert not hears(HALL, (48, 48), (48, 48), 0)


def test_walls_muffle_noise():
    # Même distance (96 px) : libre dans le couloir, mais avec un mur entre les deux.
    assert hears(HALL, (112, 48), (208, 48), 100)  # rien entre les deux
    assert not hears(HALL, (112, 80), (208, 80), 100)  # le pilier (5, 2) étouffe : 96 + 48 > 100
    assert hears(HALL, (112, 80), (208, 80), 100, wall_penalty=0)


# --- Géométrie du cône -------------------------------------------------------
def test_vision_points_count_and_range():
    pts = vision_points(HALL, EYE, 0.0, FOV, 80, 9)
    assert len(pts) == 9
    for p in pts:
        assert EYE.distance_to(p) <= 80 + 1e-6


def test_vision_points_stop_at_walls():
    pts = vision_points(HALL, (48, 80), 0.0, FOV, 400, 5)
    middle = pts[len(pts) // 2]
    assert middle[0] == pytest.approx(160)  # face au pilier de la tuile (5, 2)


def test_vision_points_minimum_two_rays():
    assert len(vision_points(HALL, EYE, 0.0, FOV, 80, 0)) == 2


def test_most_open_angle_points_down_the_hall():
    corner = pygame.Vector2(48, 48)
    angle = most_open_angle(HALL, corner, 400)
    assert angle == pytest.approx(0.0)  # vers l'est : le plus long couloir
