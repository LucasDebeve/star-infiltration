import pytest

from game.world.collision import move_and_collide
from game.world.tilemap import Tilemap

# Tuiles de 32 px. Pièce libre : x de 32 à 160, y de 32 à 128.
ROOM = Tilemap.from_text(
    """\
######
#....#
#....#
#....#
######
"""
)
W = H = 20


def test_free_move():
    r = move_and_collide(ROOM, 50, 50, W, H, 10, 5)
    assert (r.x, r.y, r.hit_x, r.hit_y) == (60, 55, False, False)


def test_stops_flush_against_right_wall():
    r = move_and_collide(ROOM, 100, 50, W, H, 500, 0)
    assert r.x == 160 - W and r.hit_x and not r.hit_y


def test_stops_flush_against_left_wall():
    r = move_and_collide(ROOM, 50, 50, W, H, -500, 0)
    assert r.x == 32 and r.hit_x


def test_stops_against_top_and_bottom():
    up = move_and_collide(ROOM, 50, 50, W, H, 0, -500)
    down = move_and_collide(ROOM, 50, 50, W, H, 0, 500)
    assert up.y == 32 and up.hit_y
    assert down.y == 128 - H and down.hit_y


def test_slides_along_wall_on_diagonal():
    # On pousse vers le mur de droite et vers le bas : X bloqué, Y libre.
    r = move_and_collide(ROOM, 140, 40, W, H, 30, 30)
    assert r.x == 160 - W and r.hit_x
    assert r.y == 70 and not r.hit_y


def test_flush_against_wall_does_not_stick():
    # Collé au mur de droite, on doit pouvoir descendre sans être « accroché ».
    r = move_and_collide(ROOM, 160 - W, 40, W, H, 0, 40)
    assert r.y == 80 and not r.hit_y and not r.hit_x


def test_no_tunneling_through_thin_wall():
    # Mur d'une tuile (colonne 4) entre deux pièces : un déplacement de 250 px d'un coup
    # ne doit pas le traverser.
    walled = Tilemap.from_text("#...#...#\n#...#...#\n#########")
    r = move_and_collide(walled, 40, 40, W, H, 250, 0)
    assert r.x == 4 * 32 - W and r.hit_x


def test_out_of_map_is_solid():
    open_map = Tilemap.from_text("...\n...")
    r = move_and_collide(open_map, 10, 10, W, H, -100, -100)
    assert r.x == 0 and r.y == 0


@pytest.mark.parametrize("dx,dy", [(3, 0), (-3, 0), (0, 3), (0, -3), (2, 2), (-2, 2)])
def test_never_ends_inside_a_wall(dx, dy):
    x, y = 60.0, 60.0
    for _ in range(500):
        r = move_and_collide(ROOM, x, y, W, H, dx * 4, dy * 4)
        x, y = r.x, r.y
        assert 32 <= x <= 160 - W and 32 <= y <= 128 - H
