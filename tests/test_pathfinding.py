import heapq
import math
import random

import pygame
import pytest

from game.ai.pathfinding import find_path, nearest_walkable, plan_route, smooth_path
from game.world.tilemap import Tilemap
from tests.paths import SANDBOX

OPEN = Tilemap.from_text("#######\n#.....#\n#.....#\n#.....#\n#######")
WALLED = Tilemap.from_text(
    """\
#########
#...#...#
#...#...#
#.......#
#########"""
)
SEALED = Tilemap.from_text("#######\n#..#..#\n#..#..#\n#######")


def path_cost(path):
    return sum(math.dist(a, b) for a, b in zip(path, path[1:]))


def test_trivial_paths():
    assert find_path(OPEN, (2, 2), (2, 2)) == [(2, 2)]
    assert find_path(OPEN, (1, 1), (2, 1)) == [(1, 1), (2, 1)]


def test_diagonal_is_taken_when_free():
    assert find_path(OPEN, (1, 1), (3, 3)) == [(1, 1), (2, 2), (3, 3)]


def test_goes_around_walls():
    path = find_path(WALLED, (1, 1), (7, 1))
    assert path[0] == (1, 1) and path[-1] == (7, 1)
    assert all(not WALLED.is_solid(*t) for t in path)
    assert (4, 3) in path  # seul passage


def test_steps_are_adjacent():
    path = find_path(WALLED, (1, 1), (7, 1))
    assert all(max(abs(a[0] - b[0]), abs(a[1] - b[1])) == 1 for a, b in zip(path, path[1:]))


def test_no_corner_cutting():
    tm = Tilemap.from_text("####\n#.##\n##.#\n####")
    # (1,1) et (2,2) ne se touchent que par un coin entre deux murs : interdit.
    assert find_path(tm, (1, 1), (2, 2)) == []


def test_diagonal_blocked_by_single_adjacent_wall():
    tm = Tilemap.from_text("#####\n#...#\n#.#.#\n#...#\n#####")
    path = find_path(tm, (1, 1), (3, 3))
    assert len(path) == 5  # il faut contourner le pilier ; aucune diagonale ne le frôle
    for a, b in zip(path, path[1:]):
        if a[0] != b[0] and a[1] != b[1]:
            assert not tm.is_solid(a[0], b[1]) and not tm.is_solid(b[0], a[1])


def test_unreachable_or_solid_endpoints():
    assert find_path(SEALED, (1, 1), (5, 1)) == []
    assert find_path(OPEN, (1, 1), (0, 0)) == []  # but dans un mur
    assert find_path(OPEN, (0, 0), (1, 1)) == []  # départ dans un mur
    assert find_path(OPEN, (1, 1), (50, 50)) == []  # hors carte


def test_door_is_an_obstacle():
    tm = Tilemap.from_text("#####\n#.D.#\n#####")
    assert find_path(tm, (1, 1), (3, 1)) == []


def test_nearest_walkable():
    assert nearest_walkable(OPEN, (2, 2)) == (2, 2)
    assert nearest_walkable(OPEN, (0, 2)) == (1, 2)
    assert nearest_walkable(OPEN, (-5, -5), max_radius=2) is None


def test_astar_is_optimal_on_random_grids():
    """Le coût doit égaler celui de Dijkstra (référence lente et évidente)."""

    def dijkstra(tm, start, goal):
        best, heap = {start: 0.0}, [(0.0, start)]
        while heap:
            cost, (x, y) = heapq.heappop(heap)
            if (x, y) == goal:
                return cost
            if cost > best[(x, y)]:
                continue
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if (dx, dy) == (0, 0) or tm.is_solid(x + dx, y + dy):
                        continue
                    if dx and dy and (tm.is_solid(x + dx, y) or tm.is_solid(x, y + dy)):
                        continue
                    nxt, new = (x + dx, y + dy), cost + math.hypot(dx, dy)
                    if new < best.get(nxt, math.inf):
                        best[nxt] = new
                        heapq.heappush(heap, (new, nxt))
        return None

    rng = random.Random(1234)
    for _ in range(30):
        rows = ["#" * 16] + ["#" + "".join("#" if rng.random() < 0.3 else "." for _ in range(14)) + "#" for _ in range(10)] + ["#" * 16]
        tm = Tilemap.from_text("\n".join(rows))
        start, goal = (rng.randint(1, 14), rng.randint(1, 10)), (rng.randint(1, 14), rng.randint(1, 10))
        expected = dijkstra(tm, start, goal) if not (tm.is_solid(*start) or tm.is_solid(*goal)) else None
        path = find_path(tm, start, goal)
        if expected is None:
            assert path == []
        else:
            assert path_cost(path) == pytest.approx(expected)


def test_astar_on_real_level_is_fast_and_valid():
    tm = Tilemap.from_file(SANDBOX)
    player = tm.spawns_of("player")[0]
    exit_ = tm.spawns_of("exit")[0]
    path = find_path(tm, (player.tx, player.ty), (exit_.tx, exit_.ty))
    assert path and all(not tm.is_solid(*t) for t in path)


# --- Lissage et planification en coordonnées monde ---------------------------
def centers(tiles, ts=32):
    return [pygame.Vector2((x + 0.5) * ts, (y + 0.5) * ts) for x, y in tiles]


def test_smoothing_removes_collinear_points():
    pts = centers([(1, 1), (2, 1), (3, 1), (4, 1)])
    assert smooth_path(OPEN, pts, 10) == [pts[0], pts[-1]]


def test_smoothing_keeps_corners():
    tiles = find_path(WALLED, (1, 1), (7, 1))
    pts = centers(tiles)
    smooth = smooth_path(WALLED, pts, 10)
    assert 2 < len(smooth) < len(pts)
    for a, b in zip(smooth, smooth[1:]):  # chaque segment lissé est réellement praticable
        from game.world.raycast import has_clearance

        assert has_clearance(WALLED, a, b, 10)


def test_smoothing_short_paths_untouched():
    pts = centers([(1, 1), (2, 1)])
    assert smooth_path(OPEN, pts, 10) == pts


def test_plan_route_excludes_start_and_reaches_goal():
    start, goal = pygame.Vector2(50, 50), pygame.Vector2(7.5 * 32, 1.5 * 32)
    route = plan_route(WALLED, start, goal, 11)
    assert route and route[0] != start
    assert route[-1].distance_to((7.5 * 32, 1.5 * 32)) < 1


def test_plan_route_already_there_and_unreachable():
    assert plan_route(OPEN, pygame.Vector2(50, 50), pygame.Vector2(60, 40), 11) == []
    assert plan_route(SEALED, pygame.Vector2(50, 50), pygame.Vector2(5.5 * 32, 48), 11) is None


def test_plan_route_to_solid_goal_uses_nearest_floor():
    route = plan_route(OPEN, pygame.Vector2(50, 50), pygame.Vector2(10, 50), 11)  # but dans le mur de gauche
    assert route == [] or route[-1].x > 32


def test_unreachable_goal_is_rejected_without_exploring(monkeypatch):
    """Zones séparées : on renonce avant de lancer l'A* (sinon il explorerait toute la zone)."""
    import game.ai.pathfinding as pf

    def boom(*args):
        raise AssertionError("l'A* n'aurait pas dû explorer les voisins")

    monkeypatch.setattr(pf, "_neighbors", boom)
    assert find_path(SEALED, (1, 1), (5, 1)) == []
