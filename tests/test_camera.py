import pygame

from game.core.camera import Camera


def make(smoothing=0):
    return Camera(200, 100, 1000, 600, smoothing=smoothing)


def test_centers_on_target():
    cam = make()
    cam.snap_to(pygame.Vector2(500, 300))
    assert tuple(cam.pos) == (400, 250)


def test_clamped_to_world_edges():
    cam = make()
    cam.snap_to(pygame.Vector2(0, 0))
    assert tuple(cam.pos) == (0, 0)
    cam.snap_to(pygame.Vector2(5000, 5000))
    assert tuple(cam.pos) == (800, 500)


def test_small_world_is_centered():
    cam = Camera(200, 100, 100, 50)
    cam.snap_to(pygame.Vector2(10, 10))
    assert tuple(cam.pos) == (-50, -25)


def test_smoothing_converges_without_overshoot():
    cam = make(smoothing=8)
    cam.snap_to(pygame.Vector2(200, 200))
    target = pygame.Vector2(600, 300)
    goal = cam.goal_for(target)
    previous = cam.pos.distance_to(goal)
    for _ in range(300):
        cam.update(target, 1 / 60)
        dist = cam.pos.distance_to(goal)
        assert dist <= previous
        previous = dist
    assert previous < 0.5


def test_world_screen_roundtrip():
    cam = make()
    cam.snap_to(pygame.Vector2(500, 300))
    world = pygame.Vector2(430, 260)
    screen = cam.world_to_screen(world)
    assert screen == (30, 10)
    assert cam.screen_to_world(screen) == world


def test_visible_rect():
    cam = make()
    cam.snap_to(pygame.Vector2(500, 300))
    assert cam.visible_rect == pygame.Rect(400, 250, 200, 100)
