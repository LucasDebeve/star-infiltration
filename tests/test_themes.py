"""Thèmes visuels : directive @theme, tuiles dessinées par thème, lumière, poussière, missions livrées."""

import pygame
import pytest

from game.campaign import load_campaign
from game.core.camera import Camera
from game.settings import AMBIENT_LIGHT, DUST_COLOR, LAMP_TINTS, TILE_SIZE
from game.systems.effects import Effects
from game.ui.lighting import Lighting
from game.world import tile_art
from game.world.level_check import check_level
from game.world.lights import place_ceiling_lamps
from game.world.themes import DEFAULT_THEME, ENDOR, IMPERIAL, TATOOINE, THEMES, get_theme
from game.world.tilemap import Tilemap
from tests.paths import CAMPAIGN

MAP = "#####\n#P.E#\n#####\n"


def luminance(color):
    return 0.2126 * color[0] + 0.7152 * color[1] + 0.0722 * color[2]


# --- Les thèmes ---------------------------------------------------------------------------------
def test_the_three_themes_exist_with_their_names():
    assert list(THEMES) == ["imperial", "endor", "tatooine"]
    assert [t.label for t in THEMES.values()] == ["Vaisseau impérial", "Base terrestre d'Endor", "Base terrestre de Tatooine"]
    assert get_theme("endor") is ENDOR and DEFAULT_THEME == "imperial"


def test_the_imperial_theme_keeps_the_original_look():
    assert IMPERIAL.ambient == AMBIENT_LIGHT and IMPERIAL.lamp_tints == LAMP_TINTS and IMPERIAL.dust == DUST_COLOR
    assert (IMPERIAL.floor_style, IMPERIAL.wall_style) == ("deck", "plate")


def test_each_theme_has_its_own_palette_and_mood():
    assert len({(t.floor_a, t.wall, t.ambient) for t in THEMES.values()}) == 3
    assert luminance(TATOOINE.floor_a) > 2 * luminance(ENDOR.floor_a)  # le désert est bien plus clair que la forêt de nuit
    assert ENDOR.ambient[1] > ENDOR.ambient[0]  # un peu vert
    assert TATOOINE.ambient[0] > TATOOINE.ambient[2]  # chaud


# --- La directive -----------------------------------------------------------------------------------
def test_a_map_is_imperial_by_default():
    assert Tilemap.from_text(MAP).theme is IMPERIAL


@pytest.mark.parametrize("name", list(THEMES))
def test_the_theme_directive_selects_a_theme(name):
    assert Tilemap.from_text(MAP + f"@theme {name}\n").theme is THEMES[name]


def test_the_directive_may_come_before_the_map_rows_too():
    assert Tilemap.from_text("@theme tatooine\n" + MAP).theme is TATOOINE


def test_an_unknown_theme_is_explained_with_its_line_number():
    with pytest.raises(ValueError, match=r"Ligne 4 : Thème inconnu.*endor.*tatooine"):
        Tilemap.from_text(MAP + "@theme jakku\n")


# --- Le dessin ---------------------------------------------------------------------------------------------
def test_imperial_floor_keeps_its_checkerboard():
    a = tile_art.floor_tile(IMPERIAL, TILE_SIZE, 0, 0)
    b = tile_art.floor_tile(IMPERIAL, TILE_SIZE, 1, 0)
    assert a.get_at((3, 3))[:3] == IMPERIAL.floor_a and b.get_at((3, 3))[:3] == IMPERIAL.floor_b
    assert tile_art.floor_tile(IMPERIAL, TILE_SIZE, 2, 0) is a


@pytest.mark.parametrize("theme", [ENDOR, TATOOINE])
def test_natural_floors_vary_from_tile_to_tile_without_a_checkerboard(theme):
    tiles = {id(tile_art.floor_tile(theme, TILE_SIZE, x, y)) for x in range(8) for y in range(8)}
    assert 3 <= len(tiles) <= tile_art.VARIANTS
    images = {pygame.image.tobytes(tile_art.floor_tile(theme, TILE_SIZE, x, y), "RGB") for x in range(8) for y in range(8)}
    assert len(images) > 1


def test_the_same_position_is_always_drawn_the_same():
    assert tile_art.variant_of(7, 3) == tile_art.variant_of(7, 3)
    assert {tile_art.variant_of(x, y) for x in range(20) for y in range(20)} == set(range(tile_art.VARIANTS))


def test_each_theme_draws_distinct_walls_and_floors():
    walls = {pygame.image.tobytes(tile_art.wall_tile(t, TILE_SIZE, 1, 1), "RGB") for t in THEMES.values()}
    floors = {pygame.image.tobytes(tile_art.floor_tile(t, TILE_SIZE, 1, 1), "RGB") for t in THEMES.values()}
    assert len(walls) == len(floors) == 3


@pytest.mark.parametrize("theme", list(THEMES.values()), ids=lambda t: t.id)
def test_every_wall_has_a_lit_top_and_a_shaded_foot(theme):
    tile = tile_art.wall_tile(theme, TILE_SIZE, 2, 5)
    assert tile.get_at((5, 1))[:3] == theme.wall_top and tile.get_at((5, TILE_SIZE - 2))[:3] == theme.wall_shade
    assert tile.get_size() == (TILE_SIZE, TILE_SIZE)


def test_the_map_is_drawn_with_the_theme_of_the_map():
    def render(theme_line):
        tm = Tilemap.from_text(MAP + theme_line)
        camera = Camera(160, 96, tm.pixel_width, tm.pixel_height)
        surface = pygame.Surface((160, 96))
        tm.draw(surface, camera)
        return surface

    imperial, endor, tatooine = render(""), render("@theme endor\n"), render("@theme tatooine\n")
    assert imperial.get_at((50, 50))[:3] == IMPERIAL.floor_b or imperial.get_at((50, 50))[:3] == IMPERIAL.floor_a
    assert luminance(tatooine.get_at((50, 50))) > luminance(endor.get_at((50, 50)))
    assert pygame.image.tobytes(endor, "RGB") != pygame.image.tobytes(tatooine, "RGB")


# --- Lumière, lampes et poussière ----------------------------------------------------------------------------------
@pytest.mark.parametrize("theme", list(THEMES.values()), ids=lambda t: t.id)
def test_lighting_uses_the_ambient_light_and_lamp_tints_of_the_theme(theme):
    rows = ["#" * 20] + ["#" + "." * 18 + "#"] * 18 + ["#" * 20]
    tm = Tilemap.from_text("\n".join(rows) + f"\n@theme {theme.id}\n")
    assert Lighting(tm).ambient() == theme.ambient
    lamps = place_ceiling_lamps(tm)
    assert lamps and all(lamp.color in theme.lamp_tints for lamp in lamps)


def test_dust_takes_the_color_of_the_ground():
    for theme in THEMES.values():
        tm = Tilemap.from_text(MAP + f"@theme {theme.id}\n")
        fx = Effects(tm, seed=1)
        fx.footstep((10, 10), "run")
        assert {p.color for p in fx.particles.particles} == {theme.dust}


# --- Les missions livrées ------------------------------------------------------------------------------------------
def test_each_theme_is_used_by_a_shipped_mission():
    used = {m.id: Tilemap.from_file(m.map_path).theme.id for m in CAMPAIGN.missions}
    assert used == {
        "training": "imperial",
        "outpost": "tatooine",
        "blackout": "tatooine",
        "endor": "endor",
        "radar": "endor",
        "prison": "tatooine",
        "hangar": "imperial",
        "theft": "imperial",
        "uniform": "imperial",
        "hq": "imperial",
        "cruiser": "imperial",
        "destroyer": "imperial",
    }
    assert set(used.values()) == set(THEMES)


def test_the_endor_mission_is_a_valid_plan_theft():
    mission = CAMPAIGN.get("endor")
    tm = Tilemap.from_file(mission.map_path)
    assert mission.objective == "steal_plans" and check_level(tm) == [] and tm.warnings == []
    assert len(tm.spawns_of("guard")) >= 5 and {s.level for s in tm.spawns_of("keycard")} == {1, 2}


def test_the_endor_mission_can_be_completed_by_a_virtual_player(game, monkeypatch):
    from game.items import ItemKind
    from game.scenes import play_scene
    from tests.runner import Runner

    mission = CAMPAIGN.get("endor")
    scene = play_scene.PlayScene(game, mission.map_path, mission)
    game.scenes.push(scene)
    scene.guards.clear()
    runner = Runner(game, scene, monkeypatch)
    tm = scene.tilemap
    card = next(s for s in tm.spawns_of("keycard") if s.level == 1)
    runner.go((card.tx, card.ty))
    runner.press("1")  # le bouton de la caserne ouvre le champ du sud-est
    assert not tm.fields["a"].active
    card = next(s for s in tm.spawns_of("keycard") if s.level == 2)
    runner.go((card.tx, card.ty))
    runner.use_terminal()
    assert scene.inventory.count_kind(ItemKind.DATA) == 1
    exit_ = tm.spawns_of("exit")[0]
    runner.go((exit_.tx, exit_.ty))
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_e))
    runner.frames(2)
    assert scene.won and game.progress.is_completed("endor")


def test_the_new_intros_name_their_places():
    campaign = load_campaign()
    assert any("Tatooine" in p for p in campaign.get("blackout").intro)
    assert any("Endor" in p for p in campaign.get("endor").intro)
    assert "Tatooine" in campaign.get("blackout").summary and "Endor" in campaign.get("endor").summary
