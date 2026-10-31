import pygame
import pytest

from game.ai.pathfinding import find_path
from game.ai.perception import can_see, hears
from game.core.camera import Camera
from game.settings import TILE_SIZE
from game.ui.lighting import Lighting
from game.world import prop_art
from game.world.collision import move_and_collide
from game.world.lights import Lamp, light_polygon
from game.world.props import BOX_KIND, SHIP_KIND, Prop, find_props
from game.world.raycast import cast_ray, count_solid_tiles, has_clearance, line_of_sight
from game.world.tilemap import BOX, DOOR, FIELD, FLOOR, OPEN_DOOR, SHIP, VOID, WALL, Tilemap

TS = TILE_SIZE


def center(tx, ty):
    return pygame.Vector2((tx + 0.5) * TS, (ty + 0.5) * TS)


def make(rows, *directives):
    return Tilemap.from_text("\n".join([*rows, *directives]))


# Une salle (gauche), un obstacle au milieu, une salle (droite) : le caractère `X` est remplacé par le test.
def corridor(obstacle: str) -> Tilemap:
    return make(["#########", f"#...{obstacle}...#", f"#...{obstacle}...#", "#########"])


# --- Propriétés des tuiles : solide / opaque ----------------------------------
@pytest.mark.parametrize(
    "char, tile, solid, opaque",
    [
        (".", FLOOR, False, False),
        ("#", WALL, True, True),
        ("D", DOOR, True, True),
        ("B", BOX, True, True),
        ("S", SHIP, True, True),
        ("F", FIELD, True, False),  # le champ de force arrête le corps, pas le regard
        (" ", VOID, True, True),
    ],
)
def test_tile_letters_solidity_and_opacity(char, tile, solid, opaque):
    tm = make(["#####", f"#.{char}.#", "#####"]) if char != "S" else make(["#####", "#.S.#", "#####"])
    assert tm.tile_at(2, 1) == tile
    assert tm.is_solid(2, 1) is solid and tm.is_opaque(2, 1) is opaque


def test_an_open_door_is_neither_solid_nor_opaque():
    tm = make(["#####", "#.D.#", "#####"])
    tm.open_door([(2, 1)])
    assert tm.tile_at(2, 1) == OPEN_DOOR and not tm.is_solid(2, 1) and not tm.is_opaque(2, 1)


def test_outside_the_map_is_solid_and_opaque():
    tm = corridor(".")
    assert tm.is_solid(-1, 0) and tm.is_opaque(99, 99)


# --- Regroupement en props ----------------------------------------------------
def kinds(tm):
    return sorted((p.kind, p.x, p.y, p.w, p.h) for p in tm.props)


def test_adjacent_boxes_form_a_single_container():
    tm = make(["######", "#BB..#", "#BB..#", "#..B.#", "######"])
    assert kinds(tm) == [("box", 1, 1, 2, 2), ("box", 3, 3, 1, 1)]


def test_an_irregular_box_group_falls_back_to_single_crates():
    tm = make(["#####", "#BB.#", "#B..#", "#####"])
    assert kinds(tm) == [("box", 1, 1, 1, 1), ("box", 1, 2, 1, 1), ("box", 2, 1, 1, 1)]


def test_a_ship_is_one_prop_with_a_default_nose_to_the_north():
    tm = make(["#######", "#SSS..#", "#SSS..#", "#######"])
    assert tm.props == [Prop(SHIP_KIND, 1, 1, 3, 2, "N")]


@pytest.mark.parametrize("facing", ["N", "E", "S", "O"])
def test_ship_directive_sets_the_nose_direction(facing):
    tm = make(["#######", "#SSS..#", "#SSS..#", "#######"], f"@ship 2,2 -> {facing}")
    assert tm.props[0].facing == facing


def test_each_ship_gets_its_own_facing():
    tm = make(["#########", "#SS.SS..#", "#SS.SS..#", "#########"], "@ship 1,1 -> E", "@ship 5,2 -> S")
    by_x = {p.x: p.facing for p in tm.props}
    assert by_x == {1: "E", 4: "S"}


@pytest.mark.parametrize(
    "directive, message",
    [
        ("@ship 2,1 -> X", "orientation"),
        ("@ship 1,1 -> N", "pas de vaisseau"),  # une tuile de sol
        ("@ship 2,1", "illisible"),
        ("@ship a,b -> N", "illisible"),
    ],
)
def test_bad_ship_directives_are_rejected(directive, message):
    with pytest.raises(ValueError, match=message):
        make(["######", "#.SS.#", "######"], directive)


def test_a_ship_must_be_a_full_rectangle():
    with pytest.raises(ValueError, match="rectangle plein"):
        make(["#####", "#SS.#", "#S..#", "#####"])


def test_a_force_field_must_be_a_straight_line():
    assert kinds(make(["#######", "#FFFFF#", "#######"])) == [("field", 1, 1, 5, 1)]
    assert kinds(make(["#####", "#F###", "#F###", "#F###", "#####"])) == [("field", 1, 1, 1, 3)]
    with pytest.raises(ValueError, match="ligne droite"):
        make(["#####", "#FF.#", "#F..#", "#####"])
    with pytest.raises(ValueError, match="ligne droite"):
        make(["#####", "#FF##", "#FF##", "#####"])  # trop épais


def test_props_come_back_in_a_stable_order():
    rows = ["###########", "#B.SS.F...#", "#..SS.F...#", "###########"]
    assert make(rows).props == make(rows).props


def test_find_props_on_empty_input():
    assert find_props({}, {}) == []


def test_prop_lists_its_tiles():
    assert Prop(BOX_KIND, 2, 3, 2, 2).tiles == [(2, 3), (3, 3), (2, 4), (3, 4)]


def test_has_void_flag():
    assert make(["#####", "#...#", "#####"]).has_void is False
    assert make(["#####", "#.F.#", "#. .#", "#####"]).has_void is True


# --- Collisions : tout bloque le corps -----------------------------------------
@pytest.mark.parametrize("char", ["B", "S", "F", "#"])
def test_the_player_cannot_walk_through_any_obstacle(char):
    tm = corridor(char)
    result = move_and_collide(tm, 2.4 * TS, 1.2 * TS, 22, 22, 6 * TS, 0)
    assert result.hit_x and result.x + 22 <= 4 * TS + 1e-6  # arrêté avant la colonne 4


@pytest.mark.parametrize("char", ["B", "S", "F"])
def test_pathfinding_goes_around_but_not_through(char):
    open_room = make(["#########", f"#...{char}...#", "#.......#", "#########"])  # obstacle d'une tuile, rangée libre dessous
    path = find_path(open_room, (1, 1), (7, 1))
    assert path and all(not open_room.is_solid(*t) for t in path)  # contourne par la rangée libre
    closed = corridor(char)
    assert find_path(closed, (1, 1), (7, 1)) == []  # rien à contourner : pas de chemin


def test_a_force_field_splits_regions_like_a_wall():
    tm = corridor("F")
    assert not tm.same_region((1, 1), (7, 1))
    assert tm.region_of(4, 1) == 0


# --- Vue, lumière et bruit : le champ de force est transparent -------------------
def test_sight_passes_through_a_force_field_but_not_a_box_or_a_ship():
    a, b = center(1, 1), center(7, 1)
    assert line_of_sight(corridor("F"), a, b)
    assert not line_of_sight(corridor("B"), a, b)
    assert not line_of_sight(corridor("S"), a, b)


def test_solid_rays_stop_at_the_force_field_while_sight_rays_do_not():
    tm = corridor("F")
    assert cast_ray(tm, center(1, 1), (1, 0), 200) == 200  # le regard passe (la salle fait 7 tuiles, on reste dedans)
    assert cast_ray(tm, center(1, 1), (1, 0), 200, solid=True) == pytest.approx(4 * TS - center(1, 1).x)  # le corps non
    assert not line_of_sight(tm, center(1, 1), center(7, 1), solid=True)


def test_body_clearance_refuses_to_cross_a_force_field():
    tm = corridor("F")
    assert not has_clearance(tm, center(1, 1), center(7, 1), 8)  # même si on voit de l'autre côté
    assert has_clearance(corridor("."), center(1, 1), center(7, 1), 8)


def test_guards_see_across_a_force_field():
    tm = corridor("F")
    assert can_see(tm, center(1, 1), 0.0, 1.5, 400, center(7, 1))
    assert not can_see(corridor("B"), center(1, 1), 0.0, 1.5, 400, center(7, 1))


def test_noise_crosses_a_force_field_but_is_muffled_by_cargo():
    far = center(7, 1)
    assert count_solid_tiles(corridor("F"), center(1, 1), far) == 0
    assert count_solid_tiles(corridor("B"), center(1, 1), far) == 1
    assert hears(corridor("F"), center(5, 1), center(7, 1), 70)
    assert not hears(corridor("B"), center(3, 1), center(5, 1), 70)  # le conteneur étouffe : 64 + 48 > 70


def test_light_shines_through_a_force_field_but_not_through_cargo():
    def reach(char):
        tm = corridor(char)
        polygon = light_polygon(tm, center(2, 1), 240, 64)
        return max(x for x, _ in polygon)

    assert reach("F") > 6 * TS  # la lumière passe au-delà du champ
    assert reach("B") < 4 * TS + 1  # arrêtée net par le conteneur


def render(tm, lamp_tile, size=(1280, 720)):
    lighting = Lighting(tm)
    lighting.lamps = [Lamp(lamp_tile, (255, 255, 255), False, 0.0)]
    surface = pygame.Surface(size)
    surface.fill((200, 200, 200))
    lighting.draw(surface, Camera(*size, tm.pixel_width, tm.pixel_height), tm, [])
    return surface


def lum(surface, tile):
    x, y = (round((tile[0] + 0.5) * TS), round((tile[1] + 0.5) * TS))
    return sum(surface.get_at((x, y))[:3]) / 3


def test_a_lamp_lights_the_space_behind_a_force_field_but_not_behind_a_crate():
    through = lum(render(corridor("F"), (2, 1)), (5, 1))
    behind = lum(render(corridor("B"), (2, 1)), (5, 1))
    assert through > behind + 15


# --- Dessin ---------------------------------------------------------------------
@pytest.mark.parametrize("facing, size", [("N", (160, 128)), ("S", (160, 128)), ("E", (160, 128)), ("O", (160, 128))])
def test_a_ship_sprite_always_fills_its_footprint(facing, size):
    sprite = prop_art.ship_sprite(5, 4, facing, TS)
    assert sprite.get_size() == size
    assert pygame.mask.from_surface(sprite).count() > 0.2 * size[0] * size[1]  # il y a bien de la coque


def test_a_ship_footprint_keeps_its_dimensions_when_the_nose_points_sideways():
    assert prop_art.ship_sprite(3, 5, "E", TS).get_size() == (3 * TS, 5 * TS)


def test_small_hulls_are_fighters_and_big_ones_shuttles():
    fighter, shuttle = prop_art.ship_sprite(3, 3, "N", TS), prop_art.ship_sprite(5, 4, "N", TS)
    assert fighter.get_size() == (96, 96) and shuttle.get_size() == (160, 128)
    # Le chasseur a deux grands panneaux séparés par du vide ; la navette est d'un seul tenant.
    assert fighter.get_at((48, 4)).a == 0 and shuttle.get_at((80, 20)).a == 255


def test_the_nose_points_where_it_should():
    """Verrière (bleue) du côté du nez : en haut pour N, en bas pour S, à droite pour E, à gauche pour O."""
    def glass_center(facing):
        sprite = prop_art.ship_sprite(5, 4, facing, TS)
        pts = [(x, y) for x in range(sprite.get_width()) for y in range(sprite.get_height())
               if sprite.get_at((x, y))[2] > 180 and sprite.get_at((x, y))[0] < 110 and sprite.get_at((x, y)).a == 255]
        return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts), sprite.get_size()

    x, y, (w, h) = glass_center("N")
    assert y < h / 2
    x, y, (w, h) = glass_center("S")
    assert y > h / 2
    x, y, (w, h) = glass_center("E")
    assert x > w / 2
    x, y, (w, h) = glass_center("O")
    assert x < w / 2


def test_sprites_are_cached():
    assert prop_art.ship_sprite(5, 4, "S", TS) is prop_art.ship_sprite(5, 4, "S", TS)
    assert prop_art.box_sprite(2, 2, 1, TS) is prop_art.box_sprite(2, 2, 1, TS)


@pytest.mark.parametrize("w, h", [(1, 1), (2, 1), (1, 2), (2, 2), (3, 2), (5, 1)])
def test_crates_and_containers_fill_their_footprint_with_a_margin(w, h):
    sprite = prop_art.box_sprite(w, h, 0, TS)
    assert sprite.get_size() == (w * TS, h * TS)
    assert sprite.get_at((0, 0)).a == 0 and sprite.get_at((w * TS // 2, h * TS // 2)).a == 255


def test_neighbouring_containers_do_not_all_look_the_same():
    variants = {prop_art._variant(Prop(BOX_KIND, x, 3, 2, 2), 5) for x in range(0, 30, 3)}
    assert len(variants) >= 3


def test_the_force_field_is_animated():
    def frame(time):
        surface = pygame.Surface((256, 64))
        prop_art.draw_force_field(surface, pygame.Rect(0, 16, 256, 32), time)
        return pygame.image.tostring(surface, "RGB")

    assert frame(0.0) != frame(0.4)  # les impulsions avancent
    assert frame(1.0) == frame(1.0)  # et le dessin est déterministe


def test_the_force_field_draws_vertically_too():
    surface = pygame.Surface((64, 256))
    prop_art.draw_force_field(surface, pygame.Rect(16, 0, 32, 256), 0.3)
    assert surface.get_at((32, 128))[:3] != (0, 0, 0)


def test_tilemap_draws_every_prop_kind_and_the_void_without_error():
    rows = ["###########", "#B..SSS..F#", "#..BSSS..F#", "#.........#", "#FFFFFFFFF#", "#         #", "###########"]
    tm = make(rows, "@ship 4,1 -> E")
    surface = pygame.Surface((400, 300))
    camera = Camera(400, 300, tm.pixel_width, tm.pixel_height)
    for t in (0.0, 0.7):
        tm.draw(surface, camera, t)
    assert tm.has_void


def test_off_screen_props_are_not_drawn(monkeypatch):
    tm = make(["#######################", "#B..................SS#", "#...................SS#", "#######################"])
    drawn = []
    monkeypatch.setattr(prop_art, "draw_prop", lambda surface, prop, rect, ts, time=0.0: drawn.append(prop))
    camera = Camera(200, 100, tm.pixel_width, tm.pixel_height)
    tm.draw(pygame.Surface((200, 100)), camera)
    assert [p.kind for p in drawn] == [BOX_KIND]  # le vaisseau est à l'autre bout de la carte


# --- Portes animées ---------------------------------------------------------------
from game.core.events import EventBus  # noqa: E402
from game.entities.door import build_doors, ease_out  # noqa: E402
from game.items import Inventory, Item, ItemKind  # noqa: E402
from game.settings import DOOR_OPEN_TIME  # noqa: E402
from game.systems.interaction import InteractionContext  # noqa: E402


def door_scene(vertical=False):
    """Une porte de deux tuiles : côte à côte (vantaux qui coulissent horizontalement) ou l'une sur l'autre."""
    if vertical:
        tm = make(["###", "#D#", "#D#", "###"])
    else:
        tm = make(["######", "#.DD.#", "######"])
    return tm, build_doors(tm)[0]


def open_door(tm, door, level=3):
    inv = Inventory()
    inv.add(Item(ItemKind.KEYCARD, level))
    door.interact(InteractionContext(tm, inv, EventBus()))


def test_ease_out_is_monotonic_and_bounded():
    values = [ease_out(i / 50) for i in range(-5, 60)]
    assert values == sorted(values) and values[0] == 0.0 and values[-1] == 1.0
    assert ease_out(0.5) > 0.5  # départ vif


def test_a_closed_door_does_not_animate():
    tm, door = door_scene()
    door.update(5.0)
    assert door.progress == 0 and not door.opening


def test_opening_starts_instantly_for_gameplay_and_animates_visually():
    tm, door = door_scene()
    open_door(tm, door)
    assert door.is_open and not tm.is_solid(2, 1) and not tm.is_solid(3, 1)  # praticable tout de suite
    assert door.progress == 0 and door.opening
    door.update(DOOR_OPEN_TIME / 2)
    assert 0.4 < door.progress < 0.6 and door.opening
    door.update(DOOR_OPEN_TIME)
    assert door.progress == 1.0 and not door.opening
    door.update(1.0)
    assert door.progress == 1.0  # ne dépasse pas


def test_door_orientation_follows_its_tiles():
    _, side_by_side = door_scene()
    _, stacked = door_scene(vertical=True)
    assert side_by_side.horizontal is True  # les vantaux coulissent de gauche à droite
    assert stacked.horizontal is False  # ... ou de haut en bas


def test_door_rect_covers_its_tiles():
    _, door = door_scene()
    assert door.rect == pygame.Rect(2 * TS, TS, 2 * TS, TS)
    _, stacked = door_scene(vertical=True)
    assert stacked.rect == pygame.Rect(TS, TS, TS, 2 * TS)


@pytest.mark.parametrize("vertical", [False, True])
@pytest.mark.parametrize("progress", [0.0, 0.05, 0.3, 0.6, 0.97, 1.0])
def test_a_door_draws_at_every_stage_of_its_opening(vertical, progress):
    tm, door = door_scene(vertical)
    door.is_open, door.progress = progress > 0, progress
    surface = pygame.Surface((400, 300))
    camera = Camera(400, 300, tm.pixel_width, tm.pixel_height)
    for unlocked in (True, False):
        door.draw(surface, camera, unlocked)


def lamp_color(door, tm, **state):
    for key, value in state.items():
        setattr(door, key, value)
    surface = pygame.Surface((400, 300))
    camera = Camera(400, 300, tm.pixel_width, tm.pixel_height)
    door.draw(surface, camera, state.get("unlocked", True))
    return surface.get_at(camera.world_to_screen(door.anchor))[:3]


def test_the_status_lamp_tells_locked_ready_opening_and_open_apart():
    tm, door = door_scene()
    ready = lamp_color(door, tm)
    door.is_open, door.progress = True, 0.0
    opening = lamp_color(door, tm)
    door.progress = 1.0
    opened = lamp_color(door, tm)
    assert len({ready, opening, opened}) == 3
    assert opening == (255, 255, 255)
    assert opened[1] > opened[0] and opened[1] > opened[2]  # vert


def test_a_locked_door_lamp_is_red():
    tm, door = door_scene()
    surface = pygame.Surface((400, 300))
    camera = Camera(400, 300, tm.pixel_width, tm.pixel_height)
    door.draw(surface, camera, unlocked=False)
    r, g, b = surface.get_at(camera.world_to_screen(door.anchor))[:3]
    assert r > g + 40 and r > b + 40


def test_leaves_retract_into_the_walls():
    """Plus la porte s'ouvre, moins il reste de métal visible dans l'encadrement."""
    tm, door = door_scene()
    camera = Camera(400, 300, tm.pixel_width, tm.pixel_height)

    def metal_pixels(progress):
        door.is_open, door.progress = progress > 0, progress
        surface = pygame.Surface((400, 300))
        surface.fill((0, 0, 0))
        door.draw(surface, camera, True)
        r = pygame.Rect(camera.world_to_screen(door.rect.topleft), door.rect.size)
        return sum(surface.get_at((x, y))[:3] != (0, 0, 0) for x in range(r.x, r.right) for y in range(r.y, r.bottom))

    counts = [metal_pixels(p) for p in (0.0, 0.25, 0.5, 0.75, 1.0)]
    assert counts == sorted(counts, reverse=True) and counts[0] > counts[-1]


# --- Espace étoilé ----------------------------------------------------------------
from game.ui.backdrop import SpaceLayer  # noqa: E402


def test_space_is_the_same_every_time_but_follows_the_camera_with_parallax():
    camera = Camera(400, 300, 4000, 3000)

    def stars_at(offset):
        camera.pos.update(offset)
        surface = pygame.Surface((400, 300))
        SpaceLayer((400, 300)).draw(surface, camera, 0.0)
        return pygame.image.tostring(surface, "RGB")

    assert stars_at((0, 0)) == stars_at((0, 0))  # déterministe
    assert stars_at((0, 0)) != stars_at((300, 120))  # la caméra bouge : le ciel défile


def star_column(depth, camera_x):
    """Colonne où apparaît une étoile unique de profondeur `depth` quand la caméra est en `camera_x`."""
    layer = SpaceLayer((400, 300))
    layer.stars = [(200.0, 100.0, depth, 1, 0.0)]
    camera = Camera(400, 300, 4000, 3000)
    camera.pos.update(camera_x, 0)
    surface = pygame.Surface((400, 300))
    layer.draw(surface, camera, 0.0)
    return next(x for x in range(400) for y in range(300) if surface.get_at((x, y))[:3] != (0, 0, 0))


def test_distant_stars_move_less_than_near_ones():
    shifts = {depth: star_column(depth, 0) - star_column(depth, 100) for depth in (0.08, 0.4)}
    assert shifts[0.08] == pytest.approx(8, abs=2) and shifts[0.4] == pytest.approx(40, abs=2)  # 100 px de caméra × profondeur
    assert shifts[0.4] > 3 * shifts[0.08]


def test_space_layer_draws_at_any_surface_size():
    SpaceLayer((400, 300)).draw(pygame.Surface((800, 600)), Camera(800, 600, 4000, 3000), 3.0)
