"""Vaisseaux détaillés : ombre portée, détails du dessin, points d'attache (tuyères, feux), animation des moteurs et des feux."""
import pygame
import pytest

from game.settings import TILE_SIZE
from game.world import prop_art
from game.world.props import Prop

TS = TILE_SIZE
V = pygame.Vector2
SIZES = {"shuttle": (5, 4), "fighter": (3, 3)}


def prop_of(kind, facing, x=2, y=3):
    w, h = SIZES[kind]
    return Prop("ship", x, y, w, h, facing)


def distinct_colors(surface):
    return {surface.get_at((x, y))[:3] for x in range(surface.get_width()) for y in range(surface.get_height()) if surface.get_at((x, y)).a == 255}


# --- Plus de détails ---------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("kind", ["shuttle", "fighter"])
def test_ships_are_rich_in_detail(kind):
    sprite = prop_art.ship_sprite(*SIZES[kind], "N", TS)
    assert len(distinct_colors(sprite)) >= 12  # coque ombrée, panneaux, verrière à reflets, voyants, tuyères...


def test_the_shuttle_hull_is_shaded_light_on_the_left_dark_on_the_right():
    sprite = prop_art.ship_sprite(5, 4, "N", TS)
    left, right = sprite.get_at((70, 80))[:3], sprite.get_at((90, 80))[:3]
    assert sum(left) > sum(right)  # le côté éclairé est plus clair


def test_the_fighter_has_hexagonal_solar_panels():
    sprite = prop_art.ship_sprite(3, 3, "N", TS)
    assert sprite.get_at((13, 5)).a == 255  # la pointe haute de l'hexagone
    assert sprite.get_at((5, 5)).a == 0 and sprite.get_at((22, 5)).a == 0  # et ses coins coupés : ce n'est plus un rectangle
    assert sprite.get_at((48, 20)).a == 0  # le vide entre les deux panneaux


# --- Ombre portée -------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("facing", ["N", "E", "S", "O"])
@pytest.mark.parametrize("kind", ["shuttle", "fighter"])
def test_the_shadow_always_falls_to_the_lower_right(kind, facing):
    sprite = prop_art.ship_sprite(*SIZES[kind], facing, TS)
    shadow = [(x, y) for x in range(sprite.get_width()) for y in range(sprite.get_height()) if 0 < sprite.get_at((x, y)).a < 255]
    assert len(shadow) > 40
    hull = [(x, y) for x in range(sprite.get_width()) for y in range(sprite.get_height()) if sprite.get_at((x, y)).a == 255]
    hull_x, hull_y = sum(p[0] for p in hull) / len(hull), sum(p[1] for p in hull) / len(hull)
    shadow_x, shadow_y = sum(p[0] for p in shadow) / len(shadow), sum(p[1] for p in shadow) / len(shadow)
    assert shadow_x > hull_x and shadow_y > hull_y  # quelle que soit la direction du nez


def test_the_shadow_stays_inside_the_footprint_and_is_translucent():
    sprite = prop_art.ship_sprite(5, 4, "N", TS)
    assert sprite.get_size() == (5 * TS, 4 * TS)
    alphas = {sprite.get_at((x, y)).a for x in range(sprite.get_width()) for y in range(sprite.get_height())} - {0, 255}
    assert alphas and max(alphas) < 150


# --- Points d'attache ------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("kind", ["shuttle", "fighter"])
@pytest.mark.parametrize("facing", ["N", "E", "S", "O"])
def test_hardpoints_lie_inside_the_footprint(kind, facing):
    w, h = SIZES[kind]
    points = prop_art.ship_hardpoints(w, h, facing, TS)
    for x, y in points["engines"] + [(px, py) for px, py, _ in points["lights"]]:
        assert 0 <= x < w * TS and 0 <= y < h * TS


@pytest.mark.parametrize("kind", ["shuttle", "fighter"])
def test_the_engines_are_at_the_stern_whatever_the_heading(kind):
    w, h = SIZES[kind]
    centers = {f: prop_art.ship_hardpoints(w, h, f, TS)["engines"] for f in "NESO"}
    mean = lambda pts, i: sum(p[i] for p in pts) / len(pts)  # noqa: E731
    assert mean(centers["N"], 1) > h * TS / 2  # nez en haut : tuyères en bas
    assert mean(centers["S"], 1) < h * TS / 2
    assert mean(centers["E"], 0) < w * TS / 2  # nez à droite : tuyères à gauche
    assert mean(centers["O"], 0) > w * TS / 2


def test_a_shuttle_has_three_engines_and_two_wing_lights_a_fighter_one_each():
    shuttle, fighter = prop_art.ship_hardpoints(5, 4, "N", TS), prop_art.ship_hardpoints(3, 3, "N", TS)
    assert len(shuttle["engines"]) == 3 and len(shuttle["lights"]) == 2
    assert len(fighter["engines"]) == 1 and len(fighter["lights"]) == 1


def test_port_is_red_and_starboard_green_on_the_shuttle():
    lights = prop_art.ship_hardpoints(5, 4, "N", TS)["lights"]
    red = next(x for x, y, c in lights if c[0] > c[1])
    green = next(x for x, y, c in lights if c[1] > c[0])
    assert red < 5 * TS / 2 < green  # rouge à gauche, vert à droite quand le nez est en haut
    sideways = prop_art.ship_hardpoints(5, 4, "E", TS)["lights"]
    red_y = next(y for x, y, c in sideways if c[0] > c[1])
    green_y = next(y for x, y, c in sideways if c[1] > c[0])
    assert red_y < green_y  # le côté gauche du nez à l'est est le nord : le rouge reste à bâbord


# --- Animation ------------------------------------------------------------------------------------------------------------------------------
def render(facing="N", time=0.0, kind="shuttle"):
    w, h = SIZES[kind]
    surface = pygame.Surface((w * TS + 20, h * TS + 20))
    surface.fill((30, 34, 44))
    rect = pygame.Rect(10, 10, w * TS, h * TS)
    surface.blit(prop_art.ship_sprite(w, h, facing, TS), rect)
    prop_art.draw_ship_lights(surface, rect, prop_of(kind, facing), TS, time)
    return surface


def test_the_engines_glow_and_pulse():
    plain = pygame.Surface((180, 148))
    plain.fill((30, 34, 44))
    plain.blit(prop_art.ship_sprite(5, 4, "N", TS), (10, 10))
    lit = render(time=0.0)
    assert sum(pygame.transform.average_color(lit)[:3]) > sum(pygame.transform.average_color(plain)[:3])  # la lueur éclaire autour des tuyères
    images = {pygame.image.tobytes(render(time=t / 10), "RGB") for t in range(0, 20)}
    assert len(images) > 3  # la lueur pulse, les feux clignotent


def test_the_position_lights_blink():
    x, y, color = prop_art.ship_hardpoints(5, 4, "N", TS)["lights"][0]
    seen = {render(time=t * prop_art.LIGHT_BLINK_PERIOD / 10).get_at((10 + x, 10 + y))[:3] for t in range(10)}
    assert len(seen) == 2  # allumé (couleur vive) puis éteint (teinte sombre) au fil de la période
    assert max(sum(c) for c in seen) > 1.5 * min(sum(c) for c in seen)


def test_two_ships_do_not_pulse_in_step():
    a, b = prop_of("shuttle", "N", 2, 3), prop_of("shuttle", "N", 9, 11)
    pictures = []
    for prop in (a, b):
        surface = pygame.Surface((180, 148))
        surface.fill((30, 34, 44))
        rect = pygame.Rect(10, 10, 160, 128)
        surface.blit(prop_art.ship_sprite(5, 4, "N", TS), rect)
        prop_art.draw_ship_lights(surface, rect, prop, TS, 1.0)
        pictures.append(pygame.image.tobytes(surface, "RGB"))
    assert pictures[0] != pictures[1]


def test_draw_prop_draws_the_sprite_and_its_lights():
    surface = pygame.Surface((300, 260))
    surface.fill((30, 34, 44))
    prop = prop_of("shuttle", "S")
    prop_art.draw_prop(surface, prop, pygame.Rect(20, 20, 160, 128), TS, 0.3)
    again = pygame.Surface((300, 260))
    again.fill((30, 34, 44))
    again.blit(prop_art.ship_sprite(5, 4, "S", TS), (20, 20))
    assert pygame.image.tobytes(surface, "RGB") != pygame.image.tobytes(again, "RGB")  # draw_prop a ajouté la lueur et les feux


def test_hardpoints_are_cached():
    assert prop_art.ship_hardpoints(5, 4, "N", TS) is prop_art.ship_hardpoints(5, 4, "N", TS)


def test_ships_in_the_shipped_maps_all_draw(game):
    from game.core.camera import Camera
    from game.world.tilemap import Tilemap
    from tests.paths import CAMPAIGN

    for mission in CAMPAIGN.missions:
        tm = Tilemap.from_file(mission.map_path)
        if not any(p.kind == "ship" for p in tm.props):
            continue
        surface = pygame.Surface((tm.pixel_width, tm.pixel_height))
        camera = Camera(tm.pixel_width, tm.pixel_height, tm.pixel_width, tm.pixel_height)
        tm.draw(surface, camera, 1.7)  # dessine tous les vaisseaux de la carte, lueurs et feux compris


# --- Pas d'ombre rectangulaire : la lumière survole les vaisseaux ------------------------------------------------------------------------------
from game.world.exposure import light_at  # noqa: E402
from game.world.lights import light_polygon  # noqa: E402
from game.world.raycast import cast_ray, line_of_sight  # noqa: E402
from game.world.tilemap import Tilemap  # noqa: E402

HANGAR = "\n".join(["#" * 20, "#" + "." * 18 + "#", "#...SSSS" + "." * 11 + "#", "#...SSSS" + "." * 11 + "#", "#" + "." * 18 + "#", "#" * 20])
CRATES = HANGAR.replace("SSSS", "BBBB")


def test_a_ship_blocks_sight_but_not_light():
    tm = Tilemap.from_text(HANGAR)
    here, behind = V(2.5 * TS, 2.5 * TS), V(12.5 * TS, 2.5 * TS)
    assert not line_of_sight(tm, here, behind)  # un garde ne voit pas à travers un vaisseau
    assert line_of_sight(tm, here, behind, light=True)  # mais la lumière passe au-dessus
    assert tm.is_opaque(4, 2) and not tm.blocks_light(4, 2)  # opaque pour la vue, transparent pour la lumière


def test_a_lamp_shines_past_a_ship_instead_of_casting_a_rectangle_of_shadow():
    ship, crates = Tilemap.from_text(HANGAR), Tilemap.from_text(CRATES)
    lamp = V(2.5 * TS, 2.5 * TS)
    over_ship = cast_ray(ship, lamp, (1, 0), 200, light=True)
    behind_crates = cast_ray(crates, lamp, (1, 0), 200, light=True)
    assert over_ship == 200 and behind_crates < 100  # les caisses projettent toujours leur ombre, pas le vaisseau
    assert sum(V(p).distance_to(lamp) for p in light_polygon(ship, lamp, 200, 36)) > sum(V(p).distance_to(lamp) for p in light_polygon(crates, lamp, 200, 36))


def test_walls_still_cast_shadows():
    tm = Tilemap.from_text(HANGAR)
    assert cast_ray(tm, V(2.5 * TS, 2.5 * TS), (-1, 0), 200, light=True) < 60  # le mur de gauche


def test_the_light_under_a_ship_is_not_cut_off_behind_it():
    ship, crates = Tilemap.from_text(HANGAR), Tilemap.from_text(CRATES)
    lamp = [(V(2.5 * TS, 2.5 * TS), 260, (255, 255, 255), 1.0)]
    behind = V(9.5 * TS, 2.5 * TS)
    assert light_at(ship, behind, 0.3, lamp) > 0.3 and light_at(crates, behind, 0.3, lamp) == 0.3  # on se voit derrière un vaisseau éclairé


def test_the_game_sees_no_rectangle_around_a_lit_ship(game):
    """Au centre du rectangle du vaisseau, la scène n'est pas plus sombre que le sol voisin éclairé par la même lampe."""
    from game.core.camera import Camera
    from game.ui.lighting import Lighting

    tm = Tilemap.from_text(HANGAR)
    lighting = Lighting(tm)
    lighting.lamps = lighting.lamps[:1] if lighting.lamps else lighting.lamps
    camera = Camera(20 * TS, 6 * TS, 20 * TS, 6 * TS)
    surface = pygame.Surface((20 * TS, 6 * TS))
    surface.fill((200, 200, 200))
    lighting.update(1.0, False)
    lighting.draw(surface, camera, tm, [])
    ship_pixel = sum(surface.get_at((5 * TS, 2 * TS + 16))[:3])
    floor_pixel = sum(surface.get_at((5 * TS, 4 * TS + 16))[:3])
    assert ship_pixel >= floor_pixel * 0.7  # pas un trou noir en forme de rectangle
