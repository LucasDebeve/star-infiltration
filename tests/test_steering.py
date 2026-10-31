import math

import pygame
import pytest

from game.ai.steering import PathFollower, angle_difference, rotate_towards


def test_angle_difference_takes_the_short_way():
    assert angle_difference(math.radians(10), math.radians(350)) == pytest.approx(math.radians(20))
    assert angle_difference(math.radians(350), math.radians(10)) == pytest.approx(math.radians(-20))
    assert abs(angle_difference(0, 0)) < 1e-9


def test_rotate_towards_is_limited_and_never_overshoots():
    assert rotate_towards(0, math.pi / 2, 0.1) == pytest.approx(0.1)
    assert rotate_towards(0, 0.05, 0.1) == 0.05
    # Passe par le chemin court à travers ±π.
    assert rotate_towards(math.radians(170), math.radians(-170), math.radians(5)) == pytest.approx(math.radians(175))


def test_follower_walks_through_points_in_order():
    f = PathFollower(tolerance=1)
    f.set_path([pygame.Vector2(10, 0), pygame.Vector2(10, 10)])
    pos = pygame.Vector2()
    for _ in range(30):
        pos += f.step(pos, 2)
    assert f.finished
    assert pos.distance_to((10, 10)) <= 1


def test_follower_never_overshoots_a_point():
    f = PathFollower(tolerance=0.1)
    f.set_path([pygame.Vector2(5, 0)])
    assert f.step(pygame.Vector2(), 100) == pygame.Vector2(5, 0)
    assert f.finished


def test_follower_empty_and_clear():
    f = PathFollower()
    assert f.finished and f.step(pygame.Vector2(), 5) == pygame.Vector2()
    f.set_path([pygame.Vector2(50, 50)])
    assert not f.finished
    f.clear()
    assert f.finished


def test_follower_copies_its_input():
    point = pygame.Vector2(10, 0)
    f = PathFollower()
    f.set_path([point])
    point.x = 999
    assert f.waypoints[0].x == 10
