import math

import pygame
import pytest

from game.world.raycast import cast_ray, count_solid_tiles, has_clearance, line_of_sight, traverse
from game.world.tilemap import Tilemap

# Tuiles de 32 px. Mur plein en x = 5 (de 160 à 192 px), sur les rangées 1 à 3.
ROOM = Tilemap.from_text(
    """\
#########
#....#..#
#....#..#
#....#..#
#########"""
)


def test_ray_in_free_space_returns_max():
    assert cast_ray(ROOM, (48, 48), (0, 1), 40) == 40  # le mur du bas est à 80 px


def test_ray_hits_wall_at_exact_distance():
    assert cast_ray(ROOM, (48, 48), (1, 0), 500) == pytest.approx(160 - 48)


def test_ray_direction_need_not_be_normalised():
    assert cast_ray(ROOM, (48, 48), (7, 0), 500) == pytest.approx(112)


def test_ray_diagonal_stops_on_the_wall_it_hits():
    dist = cast_ray(ROOM, (80, 48), (1, 1), 500)
    hit = pygame.Vector2(80, 48) + pygame.Vector2(1, 1).normalize() * dist
    assert dist == pytest.approx((128 - 48) * math.sqrt(2))  # le mur du bas commence à y = 128
    assert hit.y == pytest.approx(128)


def test_ray_starting_in_wall_returns_zero():
    assert cast_ray(ROOM, (176, 48), (1, 0), 100) == 0


def test_zero_direction_does_not_loop_forever():
    assert cast_ray(ROOM, (48, 48), (0, 0), 100) == 100


def test_ray_grazing_a_corner_is_not_blocked():
    # Pilier en tuile (2, 2) = carré de 64 à 96 px.
    tm = Tilemap.from_text("#####\n#...#\n#.#.#\n#...#\n#####")
    assert line_of_sight(tm, (48, 48), (48, 112))  # le long du pilier, sans le toucher
    assert not line_of_sight(tm, (48, 48), (112, 112))  # à travers le pilier
    assert line_of_sight(tm, (48, 80), (80, 48))  # la diagonale passe pile par le coin (64, 64) sans entrer dedans


def test_traverse_yields_each_tile_once_in_order():
    tiles = [(tx, ty) for tx, ty, _ in traverse(32, 16, 16, 1, 0, 100)]
    assert tiles == [(0, 0), (1, 0), (2, 0), (3, 0)]


def test_traverse_distances_increase():
    dists = [d for _, _, d in traverse(32, 5, 7, 0.6, 0.8, 300)]
    assert dists == sorted(dists)


def test_line_of_sight():
    assert line_of_sight(ROOM, (48, 48), (112, 48))
    assert not line_of_sight(ROOM, (48, 48), (208, 48))  # le mur du milieu


def test_line_of_sight_is_symmetric():
    a, b = (40, 100), (230, 50)
    assert line_of_sight(ROOM, a, b) == line_of_sight(ROOM, b, a)


def test_count_solid_tiles():
    assert count_solid_tiles(ROOM, (48, 48), (112, 48)) == 0
    assert count_solid_tiles(ROOM, (48, 48), (208, 48)) == 1


def test_clearance_needs_room_for_the_whole_disc():
    corridor = Tilemap.from_text("#######\n#.....#\n#######")  # couloir de 32 px de large
    a, b = pygame.Vector2(48, 48), pygame.Vector2(176, 48)
    assert has_clearance(corridor, a, b, 10)
    assert not has_clearance(corridor, a, b, 20)  # le disque est plus large que le couloir


def test_clearance_refuses_to_clip_a_corner():
    tm = Tilemap.from_text("#####\n#...#\n#.#.#\n#...#\n#####")
    # Le segment central passe à 1 px du pilier... mais un disque de 11 px ne passe pas.
    assert not has_clearance(tm, (48, 48), (112, 112), 11)
    assert has_clearance(tm, (48, 48), (48, 112), 11)


def test_clearance_zero_length_segment():
    assert has_clearance(ROOM, (48, 48), (48, 48), 10)
    assert not has_clearance(ROOM, (176, 48), (176, 48), 10)
