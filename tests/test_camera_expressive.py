"""Caméra expressive : avance dans le sens du déplacement, inclinaison vers le curseur, zoom, secousses."""

import math

import pygame
import pytest

from game.ai.guard import GuardState
from game.core.camera import Camera
from game.core.input import InputState
from game.entities.player import Stance
from game.scenes import play_scene
from game.settings import (
    CAMERA_AIM_MAX,
    CAMERA_LOOKAHEAD,
    CAMERA_SHAKE_MAX,
    CAMERA_TRAUMA_DECAY,
    CAMERA_ZOOM,
    CAMERA_ZOOM_EPS,
    PLAYER_SPEED,
    SHAKE_DOOR,
    SHAKE_EVENTS,
    SHAKE_FIELD,
    SHAKE_RANGE,
)
from tests.paths import BLACKOUT, CAMPAIGN, SANDBOX

V = pygame.Vector2


def settle(camera, target, velocity=None, aim=None, seconds=3.0):
    for _ in range(int(seconds * 60)):
        camera.update(V(target), 1 / 60, velocity, aim)


def centered(world=4000):
    camera = Camera(1280, 720, world, world)
    camera.snap_to(V(2000, 2000))
    return camera


# --- Avance dans le sens du déplacement --------------------------------------------------------------
def test_without_velocity_or_aim_the_camera_simply_follows():
    camera = centered()
    settle(camera, (2200, 2000))
    assert camera.lead == V(0, 0) and camera.pos == camera.goal_for(V(2200, 2000))


def test_the_camera_looks_ahead_in_the_direction_of_travel():
    camera = centered()
    settle(camera, (2000, 2000), velocity=V(PLAYER_SPEED["run"], 0))
    assert camera.lead.x == pytest.approx(CAMERA_LOOKAHEAD, abs=1) and camera.lead.y == pytest.approx(0, abs=0.01)
    assert camera.pos.x > camera.goal_for(V(2000, 2000)).x + CAMERA_LOOKAHEAD - 2  # le joueur est en retrait du centre


def test_a_slower_pace_gives_a_shorter_lead():
    walking, running = centered(), centered()
    settle(walking, (2000, 2000), velocity=V(PLAYER_SPEED["walk"], 0))
    settle(running, (2000, 2000), velocity=V(PLAYER_SPEED["run"], 0))
    assert 0 < walking.lead.x < running.lead.x
    assert walking.lead.x == pytest.approx(CAMERA_LOOKAHEAD * PLAYER_SPEED["walk"] / PLAYER_SPEED["run"], abs=1)


def test_the_lead_never_exceeds_the_maximum_even_faster_than_a_run():
    camera = centered()
    settle(camera, (2000, 2000), velocity=V(0, -PLAYER_SPEED["run"] * 5))
    assert camera.lead.length() <= CAMERA_LOOKAHEAD + 0.01 and camera.lead.y < 0


def test_the_lead_relaxes_slowly_when_stopping_without_snapping():
    camera = centered()
    settle(camera, (2000, 2000), velocity=V(PLAYER_SPEED["run"], 0))
    full = camera.lead.x
    camera.update(V(2000, 2000), 1 / 60, V(0, 0))
    assert 0.9 * full < camera.lead.x < full  # pas de saut de caméra à l'arrêt
    settle(camera, (2000, 2000), velocity=V(0, 0))
    assert camera.lead.length() < 0.5


def test_the_lead_is_smoothed_not_instant_when_starting():
    camera = centered()
    camera.update(V(2000, 2000), 1 / 60, V(PLAYER_SPEED["run"], 0))
    assert 0 < camera.lead.x < CAMERA_LOOKAHEAD * 0.1


def test_the_lead_is_independent_of_the_frame_rate():
    a, b = centered(), centered()
    for _ in range(60):
        a.update(V(2000, 2000), 1 / 60, V(PLAYER_SPEED["run"], 0))
    for _ in range(30):
        b.update(V(2000, 2000), 1 / 30, V(PLAYER_SPEED["run"], 0))
    assert a.lead.x == pytest.approx(b.lead.x, rel=0.01)


def test_the_camera_stays_inside_the_world_even_with_a_lead():
    camera = Camera(1280, 720, 1500, 900)
    camera.snap_to(V(1400, 800))
    settle(camera, (1480, 880), velocity=V(PLAYER_SPEED["run"], PLAYER_SPEED["run"]))
    assert camera.pos.x <= 1500 - 1280 and camera.pos.y <= 900 - 720


# --- Inclinaison vers le curseur -----------------------------------------------------------------------
def test_the_camera_leans_toward_the_cursor_but_only_so_far():
    camera = centered()
    settle(camera, (2000, 2000), aim=V(300, 0))
    assert 0 < camera.lead.x <= CAMERA_AIM_MAX and camera.lead.y == pytest.approx(0, abs=0.01)
    settle(camera, (2000, 2000), aim=V(-5000, 0))
    assert camera.lead.length() == pytest.approx(CAMERA_AIM_MAX, abs=0.5) and camera.lead.x < 0


def test_the_lean_and_the_lead_add_up():
    camera = centered()
    settle(camera, (2000, 2000), velocity=V(PLAYER_SPEED["run"], 0), aim=V(200, 0))
    assert camera.lead.x > CAMERA_LOOKAHEAD


# --- Zoom --------------------------------------------------------------------------------------------------
def test_the_zoom_glides_toward_its_target_without_overshooting():
    camera = centered()
    camera.zoom_target = 1.1
    values = []
    for _ in range(180):
        camera.update(V(2000, 2000), 1 / 60)
        values.append(camera.zoom)
    assert values == sorted(values) and values[-1] == pytest.approx(1.1, abs=0.002) and max(values) <= 1.1
    assert values[0] - 1.0 < 0.01  # démarrage doux


def test_the_zoom_returns_to_normal():
    camera = centered()
    camera.zoom, camera.zoom_target = 1.1, 1.0
    settle(camera, (2000, 2000))
    assert camera.zoom == pytest.approx(1.0, abs=0.002)


def test_screen_points_map_back_to_the_same_world_point_with_the_zoom():
    camera = centered()
    camera.zoom = 1.25
    world = V(2100, 1950)
    shown = camera.zoom_point(camera.world_to_screen(world))
    back = camera.screen_to_world((round(shown[0]), round(shown[1])))
    assert back.distance_to(world) < 1.5  # viser un point à l'écran vise bien ce point du monde


def test_the_center_of_the_view_never_moves_with_the_zoom():
    camera = centered()
    camera.zoom = 1.3
    assert camera.zoom_point((640, 360)) == (640, 360)
    assert camera.screen_to_world((640, 360)) == camera.screen_to_world((640, 360))
    assert camera.zoom_point((0, 0)) == pytest.approx((640 - 640 * 1.3, 360 - 360 * 1.3))


def test_without_zoom_the_conversions_are_unchanged():
    camera = centered()
    assert camera.zoom == 1.0
    assert camera.zoom_point((100, 50)) == (100, 50)
    assert camera.screen_to_world((100, 50)) == V(camera.offset[0] + 100, camera.offset[1] + 50)


# --- Secousses -------------------------------------------------------------------------------------------------
def test_trauma_adds_up_is_capped_and_fades_out():
    camera = centered()
    camera.add_trauma(0.6)
    camera.add_trauma(0.6)
    assert camera.trauma == 1.0
    camera.update(V(2000, 2000), 1.0 / CAMERA_TRAUMA_DECAY / 2)
    assert 0.4 < camera.trauma < 0.6
    settle(camera, (2000, 2000), seconds=2)
    assert camera.trauma == 0 and camera.shake == V(0, 0)


def test_a_shake_moves_the_view_and_stays_within_the_maximum():
    camera = centered()
    camera.add_trauma(1.0)
    seen = set()
    for _ in range(40):
        camera.update(V(2000, 2000), 1 / 120)
        seen.add(camera.offset)
        assert abs(camera.shake.x) <= CAMERA_SHAKE_MAX and abs(camera.shake.y) <= CAMERA_SHAKE_MAX
    assert len(seen) > 10  # elle bouge vraiment, dans les deux axes
    assert len({o[0] for o in seen}) > 3 and len({o[1] for o in seen}) > 3


def test_small_shocks_are_discreet():
    small, big = centered(), centered()
    small.add_trauma(0.2)
    big.add_trauma(1.0)

    def peak(c):
        return max((c.update(V(2000, 2000), 1 / 120), c.shake.length())[1] for _ in range(30))

    assert peak(small) < peak(big) / 5


def test_the_shake_is_deterministic():
    a, b = centered(), centered()
    for camera in (a, b):
        camera.add_trauma(0.8)
        for _ in range(20):
            camera.update(V(2000, 2000), 1 / 60)
    assert a.shake == b.shake


def test_the_shake_moves_what_is_drawn_and_what_is_visible():
    camera = centered()
    before = camera.world_to_screen((2000, 2000))
    camera.add_trauma(1.0)
    camera.update(V(2000, 2000), 0.05)
    assert camera.world_to_screen((2000, 2000)) != before
    assert camera.visible_rect.topleft == camera.offset


def test_disabling_the_shake_ignores_shocks():
    camera = centered()
    camera.shake_enabled = False
    camera.add_trauma(1.0)
    camera.update(V(2000, 2000), 0.05)
    assert camera.trauma == 0 and camera.shake == V(0, 0)


# --- Dans la scène ------------------------------------------------------------------------------------------------
@pytest.fixture
def scene(game, monkeypatch):
    holder = {"input": InputState()}
    monkeypatch.setattr(play_scene, "read_input", lambda: holder["input"])
    s = play_scene.PlayScene(game, SANDBOX)
    game.scenes.push(s)
    s.guards.clear()
    s.holder = holder
    return s


def run(scene, seconds):
    for _ in range(int(seconds * 60)):
        scene.update(1 / 60)


def open_direction(scene):
    """Le sens (vecteur) dans lequel le joueur a le plus de place pour courir depuis sa position."""
    tm, here = scene.tilemap, V(scene.tilemap.world_to_tile(*scene.player.pos))

    def room(d):
        n = 0
        while not tm.is_solid(int(here.x + d.x * (n + 1)), int(here.y + d.y * (n + 1))):
            n += 1
        return n

    return max((V(1, 0), V(-1, 0), V(0, 1), V(0, -1)), key=room)


def test_running_pulls_the_camera_ahead_of_the_player(scene):
    direction = open_direction(scene)
    scene.holder["input"] = InputState(move=direction, run=True)
    run(scene, 1.0)
    assert scene.camera.lead.length() > CAMERA_LOOKAHEAD * 0.3
    assert scene.camera.lead.normalize().dot(direction) > 0.99  # dans le sens de la course


def test_standing_still_has_no_lead_and_no_zoom(scene):
    run(scene, 2)
    assert scene.camera.lead.length() < 0.01 and scene.camera.zoom == pytest.approx(1.0, abs=0.001)


def test_the_cursor_only_pulls_the_camera_when_it_is_in_the_window(scene):
    scene.holder["input"] = InputState(aim_screen=(1200, 360), aim_active=False)
    run(scene, 1.5)
    assert scene.camera.lead.length() < 0.01
    scene.holder["input"] = InputState(aim_screen=(1200, 360), aim_active=True)
    run(scene, 1.5)
    assert scene.camera.lead.x > 10


def test_crouching_zooms_in_slightly(scene):
    scene.holder["input"] = InputState(crouch=True)
    run(scene, 2)
    assert scene.player.stance is Stance.CROUCH
    assert scene.camera.zoom == pytest.approx(CAMERA_ZOOM["crouch"], abs=0.005)
    scene.holder["input"] = InputState()
    run(scene, 3)
    assert scene.camera.zoom == pytest.approx(1.0, abs=0.005)


def test_hacking_focuses_the_camera_on_the_action(scene):
    terminal = scene.terminals[0]
    scene.player.pos.update(terminal.pos.x - 20, terminal.pos.y)
    terminal.start("data")  # le joueur a choisi « télécharger » dans le menu : il doit rester près du terminal
    run(scene, 1.6)
    assert terminal.job is not None and scene.hack_progress > 0 and scene.camera.zoom > 1.04
    assert scene._zoom_target() == CAMERA_ZOOM["focus"]


def test_a_chase_or_an_alert_zooms_in(scene):
    from game.ai.guard import Guard

    guard = Guard.from_spawn(scene.tilemap, scene.tilemap.spawns_of("guard")[0])
    scene.guards.append(guard)
    guard.state = GuardState.CHASE
    assert scene._zoom_target() == CAMERA_ZOOM["chase"]
    scene.guards.clear()
    assert scene._zoom_target() == 1.0
    scene.alert.active = True
    assert scene._zoom_target() == CAMERA_ZOOM["chase"]


def test_being_caught_zooms_in_the_most_and_victory_does_not(scene):
    scene.caught = True
    assert scene._zoom_target() == CAMERA_ZOOM["caught"] == max(CAMERA_ZOOM.values())
    scene.caught, scene.won = False, True
    assert scene._zoom_target() == 1.0


def test_the_zoom_priorities(scene):
    scene.player.stance = Stance.CROUCH
    assert scene._zoom_target() == CAMERA_ZOOM["crouch"]
    scene.alert.active = True
    assert scene._zoom_target() == CAMERA_ZOOM["chase"] > CAMERA_ZOOM["crouch"]


def test_events_shake_the_camera(scene):
    for event, amount in SHAKE_EVENTS.items():
        if event in ("power_cut", "ships_released"):  # testés avec une vraie console
            continue
        scene.camera.trauma = 0.0
        scene.game.events.emit(event, **{"alert_raised": {"pos": V()}, "reinforcements_arrived": {"count": 1}, "power_cut": {"console": None}}.get(event, {}))
        assert scene.camera.trauma == pytest.approx(amount), event


def test_a_nearby_door_shakes_more_than_a_distant_one(scene):
    door = scene.doors[0]
    scene.player.pos.update(door.anchor.x + 30, door.anchor.y)
    scene.camera.trauma = 0
    scene.game.events.emit("door_opened", door=door)
    near = scene.camera.trauma
    scene.player.pos.update(door.anchor.x + SHAKE_RANGE + 50, door.anchor.y)
    scene.camera.trauma = 0
    scene.game.events.emit("door_opened", door=door)
    assert near > 0.7 * SHAKE_DOOR and scene.camera.trauma == 0


def test_a_field_toggling_close_by_shakes_the_camera(scene):
    field = next(iter(scene.tilemap.fields.values()))
    scene.player.pos.update(scene._field_center(field) + V(20, 0))
    scene.camera.trauma = 0
    scene.game.events.emit("field_toggled", field=field.id, active=True)
    assert 0.6 * SHAKE_FIELD < scene.camera.trauma <= SHAKE_FIELD


def test_cutting_the_power_shakes_the_screen(game, monkeypatch):
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState())
    s = play_scene.PlayScene(game, BLACKOUT, CAMPAIGN.get("blackout"))
    game.scenes.push(s)
    s.consoles[0].interact(__import__("game.systems.interaction", fromlist=["x"]).InteractionContext(s.tilemap, s.inventory, game.events))
    assert s.camera.trauma == pytest.approx(SHAKE_EVENTS["power_cut"])


def test_the_preference_disables_the_scene_shake(game, monkeypatch):
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState())
    game.prefs.screen_shake = False
    s = play_scene.PlayScene(game, SANDBOX)
    game.scenes.push(s)
    s.game.events.emit("player_caught")
    assert s.camera.trauma == 0


def test_a_restart_resets_the_camera(scene):
    scene.camera.add_trauma(1.0)
    scene.camera.zoom = 1.2
    scene.restart()
    assert scene.camera.trauma == 0 and scene.camera.zoom == 1.0 and scene.camera.lead.length() == 0


def test_leaving_the_scene_stops_listening_to_shocks(game, scene):
    camera = scene.camera
    game.scenes.clear()
    game.events.emit("player_caught")
    assert camera.trauma == 0


# --- Dessin zoomé -------------------------------------------------------------------------------------------------------
def test_a_zoomed_frame_is_drawn_and_differs_from_the_normal_one(game, scene):
    surface = pygame.Surface((1280, 720))
    scene.draw(surface)
    normal = pygame.image.tobytes(surface, "RGB")
    scene.camera.zoom = 1.2
    scene.draw(surface)
    assert pygame.image.tobytes(surface, "RGB") != normal and scene._world_buffer is not None


def test_a_tiny_zoom_skips_the_costly_scaling(scene):
    surface = pygame.Surface((1280, 720))
    scene.camera.zoom = 1.0 + CAMERA_ZOOM_EPS / 2
    scene.draw(surface)
    assert scene._world_buffer is None


def test_the_prompt_follows_the_zoomed_object(game, scene):
    terminal = scene.terminals[0]
    scene.player.pos.update(terminal.pos.x - 20, terminal.pos.y)
    scene.camera.snap_to(scene.player.pos)
    scene.update(1 / 60)
    calls = []
    scene.hud.draw_prompt = lambda surface, pos, prompt, progress=0.0: calls.append(pos)
    surface = pygame.Surface((1280, 720))
    scene.draw(surface)
    flat = calls[-1]
    scene.camera.zoom = 1.3
    scene.draw(surface)
    zoomed = calls[-1]
    cx, cy = scene.camera.pivot  # le zoom est centré sur le joueur
    assert zoomed[0] == pytest.approx(cx + (flat[0] - cx) * 1.3, abs=1) and zoomed[1] == pytest.approx(cy + (flat[1] - cy) * 1.3, abs=1)


def test_aiming_stays_accurate_while_zoomed(scene):
    scene.camera.zoom = 1.2
    cursor = (900, 200)
    world = scene.camera.screen_to_world(cursor)
    shown = scene.camera.zoom_point(scene.camera.world_to_screen(world))
    assert math.dist(shown, cursor) < 2


# --- La pause « respire » -----------------------------------------------------------------------------------------
def test_the_pause_background_creeps_closer_then_settles():
    from game.settings import PAUSE_ZOOM
    from game.ui.backdrop import SnapshotBackdrop

    frame = pygame.Surface((320, 180))
    pygame.draw.circle(frame, (255, 255, 255), (160, 90), 40)
    backdrop = SnapshotBackdrop(frame)
    assert backdrop.scale == 1.0
    scales = []
    for _ in range(300):
        backdrop.update(1 / 60)
        scales.append(backdrop.scale)
    assert scales == sorted(scales) and scales[-1] == pytest.approx(1 + PAUSE_ZOOM, abs=0.002) and scales[-1] <= 1 + PAUSE_ZOOM
    near = pygame.Surface((320, 180))
    backdrop.draw(near)
    start = pygame.Surface((320, 180))
    SnapshotBackdrop(frame).draw(start)
    assert pygame.image.tobytes(near, "RGB") != pygame.image.tobytes(start, "RGB")  # l'image a bien grossi


def test_the_pause_scene_uses_the_breathing_background(game, monkeypatch):
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState())
    s = play_scene.PlayScene(game, SANDBOX)
    game.scenes.push(s)
    s.pause()
    for _ in range(120):
        game.step(1 / 60)
    assert game.scenes.current.backdrop.scale > 1.03


# --- Le zoom se fait autour du joueur, pas du centre de l'écran -------------------------------------------------------------------
def test_the_pivot_defaults_to_the_center_and_follows_the_target():
    camera = Camera(1280, 720, 4000, 4000)
    assert camera.pivot == V(640, 360)
    camera.snap_to(V(100, 100))  # près du coin : la caméra bute sur le bord du monde, le joueur n'est pas au centre
    camera.follow_pivot(V(100, 100))
    assert camera.pivot == V(*camera.world_to_screen((100, 100))) and camera.pivot.x < 200 and camera.pivot.y < 200


def test_the_pivot_stays_fixed_whatever_the_zoom():
    camera = Camera(1280, 720, 4000, 4000)
    camera.snap_to(V(100, 100))
    camera.follow_pivot(V(100, 100))
    point = camera.world_to_screen((100, 100))
    for zoom in (1.0, 1.05, 1.2, 1.5):
        camera.zoom = zoom
        assert camera.zoom_point(point) == pytest.approx(point)  # le joueur ne bouge pas à l'écran
    camera.zoom = 1.3
    far = camera.world_to_screen((500, 400))
    assert camera.zoom_point(far)[0] > far[0] and camera.zoom_point(far)[1] > far[1]  # le reste s'écarte de lui


def test_the_crop_keeps_the_pivot_in_place_and_stays_inside_the_image():
    camera = Camera(1280, 720, 4000, 4000)
    for pivot in (V(640, 360), V(30, 20), V(1250, 700), V(0, 0), V(1280, 720), V(100, 650)):
        camera.pivot.update(pivot)
        for zoom in (1.04, 1.16, 1.5):
            camera.zoom = zoom
            crop = camera.crop_rect()
            assert pygame.Rect(0, 0, 1280, 720).contains(crop)
            assert crop.w == pytest.approx(1280 / zoom, abs=1) and crop.h == pytest.approx(720 / zoom, abs=1)
            # le pivot est au même endroit relatif dans la zone agrandie : il ne glisse pas
            assert (pivot.x - crop.x) * zoom == pytest.approx(pivot.x, abs=zoom + 1)
            assert (pivot.y - crop.y) * zoom == pytest.approx(pivot.y, abs=zoom + 1)


def test_aiming_stays_accurate_with_an_off_center_pivot():
    camera = Camera(1280, 720, 4000, 4000)
    camera.snap_to(V(100, 100))
    camera.follow_pivot(V(100, 100))
    camera.zoom = 1.2
    world = V(300, 220)
    shown = camera.zoom_point(camera.world_to_screen(world))
    assert camera.screen_to_world((round(shown[0]), round(shown[1]))).distance_to(world) < 1.5


def test_a_player_in_a_corner_stays_in_view_when_zoomed(scene):
    scene.player.pos.update(48, 48)  # le coin de la carte : la caméra ne peut pas le centrer
    scene.camera.snap_to(scene.player.pos)
    scene.holder["input"] = InputState(crouch=True)
    run(scene, 3)
    assert scene.camera.zoom > 1.03
    on_screen = V(scene.camera.world_to_screen(scene.player.pos))
    assert on_screen.x < 200 and on_screen.y < 200  # bien dans le coin, pas au centre
    shown = V(scene.camera.zoom_point(on_screen))
    assert shown.distance_to(on_screen) < 1.5  # et le zoom ne le repousse pas hors de l'écran
    surface = pygame.Surface((1280, 720))
    scene.draw(surface)


def test_the_player_is_drawn_at_the_same_place_zoomed_or_not(scene):
    scene.player.pos.update(48, 48)
    scene.camera.snap_to(scene.player.pos)
    scene.camera.follow_pivot(scene.player.pos)
    spot = scene.camera.world_to_screen(scene.player.pos)
    surface = pygame.Surface((1280, 720))
    scene.camera.zoom = 1.0
    scene.draw(surface)
    plain = [surface.get_at((spot[0] + dx, spot[1])) for dx in (0,)]
    scene.camera.zoom = 1.25
    scene.draw(surface)
    zoomed = [surface.get_at((spot[0] + dx, spot[1])) for dx in (0,)]
    assert max(abs(a[i] - b[i]) for a, b in zip(plain, zoomed) for i in range(3)) < 40  # le torse du joueur est toujours sur place (le zoom ne le pousse pas vers le bord)
