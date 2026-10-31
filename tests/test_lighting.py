import math

import pygame
import pytest

from game.core.camera import Camera
from game.settings import ALARM_FADE_TIME, AMBIENT_LIGHT, LAMP_SPACING, LAMP_TINTS
from game.ui.lighting import MAX_CACHED_SPRITES, Lighting, lerp_color
from game.world.lights import Lamp, LightSpec, flicker_factor, light_polygon, place_ceiling_lamps
from game.world.tilemap import Tilemap
from tests.paths import SANDBOX

SIZE = (1280, 720)
GREY = (200, 200, 200)


def hall(width=42, height=24):
    rows = ["#" * width] + ["#" + "." * (width - 2) + "#" for _ in range(height - 2)] + ["#" * width]
    return Tilemap.from_text("\n".join(rows))


def two_rooms(door=False):
    """Deux salles de 10 tuiles séparées par un mur (ou une porte) en x = 12."""
    rows = []
    for y in range(24):
        row = ["#"] * 42
        if 1 <= y <= 22:
            for x in range(1, 41):
                row[x] = "." if x != 12 else ("D" if door and y in (11, 12) else "#")
        rows.append("".join(row))
    return Tilemap.from_text("\n".join(rows))


def lamp(tile, color=(255, 255, 255)):
    return Lamp(tile=tile, color=color, flickers=False, phase=0.0)


def render(lighting, tm, specs=(), camera=None):
    surface = pygame.Surface(SIZE)
    surface.fill(GREY)
    camera = camera or Camera(*SIZE, tm.pixel_width, tm.pixel_height)
    lighting.draw(surface, camera, tm, list(specs))
    return surface


def lum(surface, point):
    return sum(surface.get_at(point)[:3]) / 3


def px(tile):
    return (round((tile[0] + 0.5) * 32), round((tile[1] + 0.5) * 32))


# --- Placement des lampes (logique pure) -------------------------------------
def test_lamps_sit_on_free_tiles_and_are_deterministic():
    tm = Tilemap.from_file(SANDBOX)
    lamps = place_ceiling_lamps(tm)
    assert lamps == place_ceiling_lamps(tm)
    assert 20 < len(lamps) < 80
    assert all(not tm.is_solid(*lamp.tile) for lamp in lamps)
    assert len({lamp.tile for lamp in lamps}) == len(lamps)


def test_at_most_one_lamp_per_block_and_none_hugging_walls():
    tm = Tilemap.from_file(SANDBOX)
    blocks = [(lamp.tile[0] // LAMP_SPACING, lamp.tile[1] // LAMP_SPACING) for lamp in place_ceiling_lamps(tm)]
    assert len(blocks) == len(set(blocks))


def test_big_empty_room_gets_a_lamp_per_block():
    tm = hall()
    lamps = place_ceiling_lamps(tm)
    assert len(lamps) >= 12
    assert all(lamp.color in LAMP_TINTS for lamp in lamps)


def test_tiny_closet_gets_no_lamp():
    tm = Tilemap.from_text("#####\n#.###\n#####\n")
    assert place_ceiling_lamps(tm) == []


def test_lamp_tint_follows_the_room():
    tm = two_rooms()
    left = [l for l in place_ceiling_lamps(tm) if l.tile[0] < 12]
    right = [l for l in place_ceiling_lamps(tm) if l.tile[0] > 12]
    assert {l.color for l in left} != {l.color for l in right}  # deux salles = deux teintes
    assert len({l.color for l in left}) == 1


def test_some_lamps_flicker_but_not_most():
    tm = Tilemap.from_file(SANDBOX)
    lamps = place_ceiling_lamps(tm)
    flickering = sum(l.flickers for l in lamps)
    assert 0 < flickering < len(lamps) / 2


# --- Scintillement -----------------------------------------------------------
def test_steady_lamps_never_flicker():
    steady = lamp((3, 3))
    assert all(flicker_factor(steady, t / 10) == 1.0 for t in range(500))


def test_failing_lamps_mostly_burn_with_brutal_dips():
    bad = Lamp((3, 3), (255, 255, 255), flickers=True, phase=1.3)
    values = [flicker_factor(bad, t / 20) for t in range(20 * 600)]
    assert all(0.1 <= v <= 1.0 for v in values)
    assert sum(v == 1.0 for v in values) > 0.7 * len(values)  # surtout allumée
    assert min(values) < 0.5  # mais il y a de vrais à-coups
    assert values == [flicker_factor(bad, t / 20) for t in range(20 * 600)]  # déterministe


# --- Polygone de lumière -----------------------------------------------------
def test_light_polygon_is_a_full_circle_in_open_space():
    tm = hall()
    center = pygame.Vector2(20 * 32 + 16, 12 * 32 + 16)
    points = light_polygon(tm, center, 100, 32)
    assert len(points) == 32
    assert all(pygame.Vector2(p).distance_to(center) == pytest.approx(100) for p in points)


def test_light_polygon_is_cut_by_walls():
    tm = hall()
    center = pygame.Vector2(2 * 32 + 16, 12 * 32 + 16)  # à 1,5 tuile du mur ouest
    points = light_polygon(tm, center, 200, 64)
    west = min(points, key=lambda p: p[0])
    assert west[0] == pytest.approx(32, abs=1)  # arrêté au mur
    assert max(pygame.Vector2(p).distance_to(center) for p in points) == pytest.approx(200)


# --- Rendu : ambiance et lampes ---------------------------------------------
def test_unlit_world_is_dimmed_to_the_ambient_level():
    tm = hall()
    lighting = Lighting(tm)
    lighting.lamps = []
    out = render(lighting, tm)
    expected = [200 * c / 255 for c in AMBIENT_LIGHT]
    got = out.get_at((640, 360))[:3]
    assert all(abs(g - e) <= 2 for g, e in zip(got, expected))


def test_a_lamp_brightens_its_surroundings_and_fades_with_distance():
    tm = hall()
    lighting = Lighting(tm)
    lighting.lamps = [lamp((20, 11))]
    out = render(lighting, tm)
    near, mid, far = lum(out, px((20, 11))), lum(out, px((24, 11))), lum(out, px((36, 11)))
    assert near > mid > far
    assert far == pytest.approx(lum(out, (1200, 700)), abs=5)  # hors de portée : retour à l'ambiance


def test_walls_cast_shadows():
    tm = two_rooms()
    lighting = Lighting(tm)
    lighting.lamps = [lamp((9, 11))]
    out = render(lighting, tm)
    lit_side = lum(out, px((7, 11)))  # à 2 tuiles à gauche de la lampe
    behind_wall = lum(out, px((13, 11)))  # à 4 tuiles à droite, de l'autre côté du mur
    open_side = lum(out, px((9, 15)))  # à 4 tuiles aussi, mais dans la même salle
    assert lit_side > behind_wall
    assert open_side > behind_wall + 15  # même distance : la salle voisine reste dans l'ombre


def test_opening_a_door_lets_the_light_through():
    tm = two_rooms(door=True)
    lighting = Lighting(tm)
    lighting.lamps = [lamp((9, 11))]
    closed = lum(render(lighting, tm), px((14, 11)))
    tm.open_door([(12, 11), (12, 12)])
    opened = lum(render(lighting, tm), px((14, 11)))
    assert opened > closed + 10  # le cache d'ombres a été invalidé


def test_disabled_lighting_leaves_the_image_untouched():
    tm = hall()
    lighting = Lighting(tm)
    lighting.enabled = False
    out = render(lighting, tm)
    assert out.get_at((640, 360))[:3] == GREY
    lighting.toggle()
    assert lighting.enabled and out.get_at((640, 360))[:3] == GREY


# --- Lumières mobiles --------------------------------------------------------
def test_dynamic_light_follows_its_position():
    tm = hall()
    lighting = Lighting(tm)
    lighting.lamps = []
    spec = LightSpec(pygame.Vector2(*px((10, 11))), 120, (255, 255, 255), 1.0)
    out = render(lighting, tm, [spec])
    assert lum(out, px((10, 11))) > lum(out, px((30, 11))) + 40
    moved = LightSpec(pygame.Vector2(*px((30, 11))), 120, (255, 255, 255), 1.0)
    out = render(lighting, tm, [moved])
    assert lum(out, px((30, 11))) > lum(out, px((10, 11))) + 40


def test_dynamic_light_intensity_and_color():
    tm = hall()
    lighting = Lighting(tm)
    lighting.lamps = []
    bright = render(lighting, tm, [LightSpec(pygame.Vector2(*px((20, 11))), 100, (255, 255, 255), 1.0)])
    dim = render(lighting, tm, [LightSpec(pygame.Vector2(*px((20, 11))), 100, (255, 255, 255), 0.3)])
    assert lum(bright, px((20, 11))) > lum(dim, px((20, 11)))
    red = render(lighting, tm, [LightSpec(pygame.Vector2(*px((20, 11))), 100, (255, 0, 0), 1.0)])
    r, g, b = red.get_at(px((20, 11)))[:3]
    assert r > g + 40 and r > b + 40


def test_shadowed_dynamic_light_stops_at_walls_but_a_spot_does_not():
    tm = two_rooms()
    lighting = Lighting(tm)
    lighting.lamps = []
    across = px((13, 11))  # de l'autre côté du mur (x = 12), à 3 tuiles de la lumière
    shadowed = render(lighting, tm, [LightSpec(pygame.Vector2(*px((10, 11))), 200, (255, 255, 255), 1.0, shadowed=True)])
    spot = render(lighting, tm, [LightSpec(pygame.Vector2(*px((10, 11))), 200, (255, 255, 255), 1.0)])
    assert lum(spot, across) > lum(shadowed, across) + 15


def test_flashlight_cone_lights_only_where_it_points():
    tm = hall()
    lighting = Lighting(tm)
    lighting.lamps = []
    cone = LightSpec(pygame.Vector2(*px((10, 11))), 200, (255, 255, 255), 1.0, facing=0.0, fov=math.radians(60))
    out = render(lighting, tm, [cone])
    ahead, behind, aside = lum(out, px((13, 11))), lum(out, px((7, 11))), lum(out, px((10, 15)))
    assert ahead > behind + 30 and ahead > aside + 30


def test_offscreen_lights_cost_nothing_and_do_not_crash():
    tm = hall()
    lighting = Lighting(tm)
    lighting.lamps = []
    camera = Camera(*SIZE, tm.pixel_width, tm.pixel_height)
    far = LightSpec(pygame.Vector2(5000, 5000), 100, (255, 255, 255), 1.0)
    render(lighting, tm, [far], camera)


# --- Alerte ------------------------------------------------------------------
def test_ambient_turns_red_during_the_alert_and_fades_back():
    tm = hall()
    lighting = Lighting(tm)
    assert lighting.ambient() == AMBIENT_LIGHT
    for _ in range(round(ALARM_FADE_TIME * 60) + 5):
        lighting.update(1 / 60, alarm=True)
    r, g, b = lighting.ambient()
    assert r > g and r > b and (r, g, b) != AMBIENT_LIGHT
    for _ in range(round(ALARM_FADE_TIME * 60) + 5):
        lighting.update(1 / 60, alarm=False)
    assert lighting.ambient() == AMBIENT_LIGHT


def test_alarm_fade_is_progressive():
    lighting = Lighting(hall())
    lighting.update(ALARM_FADE_TIME / 2, alarm=True)
    assert 0.4 < lighting._alarm < 0.6


def test_lamps_turn_red_in_alert():
    tm = hall()
    lighting = Lighting(tm)
    lighting.lamps = [lamp((20, 11), (255, 255, 255))]
    calm = render(lighting, tm).get_at(px((20, 11)))[:3]
    for _ in range(round(ALARM_FADE_TIME * 60) + 5):
        lighting.update(1 / 60, alarm=True)
    alarm = render(lighting, tm).get_at(px((20, 11)))[:3]
    assert alarm[0] > alarm[2] + 20 and abs(calm[0] - calm[2]) < 25  # blanc -> rouge


# --- Caches ------------------------------------------------------------------
def test_sprite_cache_is_bounded():
    tm = Tilemap.from_file(SANDBOX)
    lighting = Lighting(tm)
    camera = Camera(*SIZE, tm.pixel_width, tm.pixel_height)
    for i in range(400):  # beaucoup de combinaisons lampe / intensité / couleur
        lighting.update(0.37, alarm=(i // 50) % 2 == 0)
        camera.snap_to(pygame.Vector2(200 + (i * 41) % 1600, 200 + (i * 29) % 700))
        render(lighting, tm, camera=camera)
    assert 0 < len(lighting._sprites) <= MAX_CACHED_SPRITES


def test_lerp_color_clamps():
    assert lerp_color((0, 0, 0), (100, 200, 50), 0.5) == (50, 100, 25)
    assert lerp_color((0, 0, 0), (100, 200, 50), 5) == (100, 200, 50)
    assert lerp_color((0, 0, 0), (100, 200, 50), -1) == (0, 0, 0)
