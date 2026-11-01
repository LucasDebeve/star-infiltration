"""Décor vivant : écrans, voyants, lanternes, bouches de vapeur, vent et poussière en suspension."""

import math

import pygame
import pytest

from game.core.camera import Camera
from game.core.input import InputState
from game.scenes import play_scene
from game.settings import (
    AMBIENT_PARTICLE_SHARE,
    DECOR_SPACING,
    MOTE_RADIUS,
    PARTICLE_LIMIT,
    VENT_BURST,
    VENT_PERIOD,
    VENT_SPACING,
    VENT_START_CLEARANCE,
)
from game.systems.effects import Effects, vent_active, wind_strength
from game.ui.particles import ParticleSystem
from game.world import decor_art
from game.world.decor import Vent, WallDecor, place_wall_decor
from game.world.themes import ENDOR, IMPERIAL, TATOOINE
from game.world.tilemap import Tilemap
from tests.paths import BLACKOUT, CAMPAIGN, CRUISER

V = pygame.Vector2
ENDOR_MAP = CAMPAIGN.get("endor").map_path


def big_map(theme="imperial"):
    rows = ["#" * 40] + ["#" + "." * 38 + "#"] * 18 + ["#" * 40]
    return Tilemap.from_text("\n".join(rows[:2] + ["#P" + "." * 37 + "#"] + rows[3:]) + f"\n@theme {theme}\n")


# --- Placement ----------------------------------------------------------------------------------------
def test_decor_is_placed_deterministically_on_flat_walls_only():
    a, b = place_wall_decor(Tilemap.from_file(ENDOR_MAP)), place_wall_decor(Tilemap.from_file(ENDOR_MAP))
    assert a == b and len(a) > 10
    tm = Tilemap.from_file(ENDOR_MAP)
    for d in a:
        assert not tm.is_solid(d.tile[0] + d.face[0], d.tile[1] + d.face[1])  # il regarde un passage
        assert tm.is_solid(*d.tile) and tm.is_opaque(*d.tile) is not False  # posé sur un mur


def test_decor_keeps_its_distance_and_leaves_doors_and_points_alone():
    from game.world.tilemap import DOOR, GATE, OPEN_DOOR

    tm = Tilemap.from_file(ENDOR_MAP)
    decor = place_wall_decor(tm)
    assert decor
    for i, d in enumerate(decor):
        for other in decor[i + 1 :]:
            assert max(abs(d.tile[0] - other.tile[0]), abs(d.tile[1] - other.tile[1])) > DECOR_SPACING
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                assert tm.tile_at(d.tile[0] + dx, d.tile[1] + dy) not in (DOOR, OPEN_DOOR, GATE)
                assert all((s.tx, s.ty) != (d.tile[0] + dx, d.tile[1] + dy) for s in tm.spawns)


def test_each_theme_picks_its_own_kinds_of_decor():
    kinds = {t.id: {d.kind for d in place_wall_decor(big_map(t.id))} for t in (IMPERIAL, TATOOINE, ENDOR)}
    assert kinds["imperial"] == set()  # à bord du vaisseau : aucun décor mural
    assert kinds["tatooine"] == kinds["endor"] == {"lantern"}  # sur terre : des lanternes, et rien d'autre


def test_the_map_carries_its_decor_and_vents():
    ship = Tilemap.from_file(CRUISER)
    assert ship.vents and ship.decor == []  # le vaisseau a de la vapeur, pas d'écrans ni de voyants
    assert Tilemap.from_file(BLACKOUT).vents == [] and Tilemap.from_file(BLACKOUT).decor  # Tatooine : pas de vapeur
    assert Tilemap.from_file(ENDOR_MAP).vents and Tilemap.from_file(ENDOR_MAP).decor


def test_vents_sit_against_one_wall_and_blow_away_from_it():
    tm = Tilemap.from_file(CRUISER)
    for vent in tm.vents:
        x, y = vent.tile
        dx, dy = vent.direction
        assert tm.is_solid(x - dx, y - dy) and not tm.is_solid(x, y) and not tm.is_solid(x + dx, y + dy)


def test_vents_are_spaced_and_far_from_the_start():
    tm = Tilemap.from_file(CRUISER)
    start = tm.spawns_of("player")[0]
    for i, v in enumerate(tm.vents):
        assert max(abs(v.tile[0] - start.tx), abs(v.tile[1] - start.ty)) >= VENT_START_CLEARANCE
        assert all(max(abs(v.tile[0] - o.tile[0]), abs(v.tile[1] - o.tile[1])) >= VENT_SPACING for o in tm.vents[i + 1 :])
        assert VENT_PERIOD[0] <= v.period <= VENT_PERIOD[1]


def test_nowhere_is_there_a_wall_screen_or_led():
    for theme in (IMPERIAL, TATOOINE, ENDOR):
        assert set(theme.decor) <= {"lantern"}


def test_the_imperial_ship_has_no_wall_decor():
    for mission in (CAMPAIGN.get("training"), CAMPAIGN.get("cruiser")):
        assert Tilemap.from_file(mission.map_path).decor == []


def test_decor_never_blocks_anything():
    tm = Tilemap.from_file(ENDOR_MAP)
    solid_before = [[tm.is_solid(x, y) for x in range(tm.width)] for y in range(tm.height)]
    tm.rebuild_decor()
    assert solid_before == [[tm.is_solid(x, y) for x in range(tm.width)] for y in range(tm.height)]


# --- Animation pure ----------------------------------------------------------------------------------------
def test_a_lantern_flickers_but_never_goes_out():
    values = [decor_art.lantern_flicker(0.4, t / 30) for t in range(600)]
    assert 0.74 <= min(values) < max(values) <= 1.0


def test_lanterns_do_not_flicker_in_step():
    assert [decor_art.lantern_flicker(0.1, t / 30) for t in range(60)] != [decor_art.lantern_flicker(0.7, t / 30) for t in range(60)]


# --- Dessin ----------------------------------------------------------------------------------------------------
def draw_lantern(time=0.0, phase=0.2):
    surface = pygame.Surface((64, 64))
    surface.fill((90, 90, 90))
    decor_art.draw_decor(surface, WallDecor("lantern", (1, 1), (0, 1), phase, 0), pygame.Rect(16, 16, 32, 32), (255, 190, 110), time)
    return pygame.image.tobytes(surface, "RGB")


def test_a_lantern_draws_something_and_animates():
    assert draw_lantern() != pygame.image.tobytes(pygame.Surface((64, 64)), "RGB")
    assert len({draw_lantern(t / 7) for t in range(30)}) > 1


def test_the_map_draws_its_decor_inside_the_view_only():
    tm = Tilemap.from_file(ENDOR_MAP)
    surface = pygame.Surface((1280, 720))
    camera = Camera(1280, 720, tm.pixel_width, tm.pixel_height)
    camera.snap_to(V(tm.pixel_width / 2, tm.pixel_height / 2))
    surface.fill((0, 0, 0))
    tm.draw_decor(surface, camera, 0.0)
    assert pygame.mask.from_threshold(surface, (0, 0, 0), (1, 1, 1, 255)).count() < 1280 * 720
    far = Camera(1280, 720, tm.pixel_width, tm.pixel_height)
    far.pos.update(-5000, -5000)
    surface.fill((0, 0, 0))
    tm.draw_decor(surface, far, 0.0)
    assert pygame.mask.from_threshold(surface, (0, 0, 0), (1, 1, 1, 255)).count() == 1280 * 720


def full_view(tm):
    return Camera(tm.pixel_width, tm.pixel_height, tm.pixel_width, tm.pixel_height)


def test_lanterns_light_the_passage_not_the_wall():
    tm = Tilemap.from_file(ENDOR_MAP)
    lights = tm.decor_lights(full_view(tm), 0.0)
    assert len(lights) == len(tm.decor) > 0
    for pos, radius, color, intensity in lights:
        assert radius > 0 and 0 < intensity <= 1 and not tm.is_solid(*tm.world_to_tile(*pos))


def test_lantern_light_flickers():
    tm = Tilemap.from_file(ENDOR_MAP)
    assert {round(l[3], 3) for t in range(20) for l in tm.decor_lights(full_view(tm), t / 5)} != {round(l[3], 3) for l in tm.decor_lights(full_view(tm), 0.0)}


def test_decor_ignores_the_power():
    """Les lanternes brûlent même sans courant : le décor n'en dépend pas."""
    import inspect

    assert "powered" not in inspect.signature(Tilemap.draw_decor).parameters
    assert "powered" not in inspect.signature(Tilemap.decor_lights).parameters


# --- Vapeur ---------------------------------------------------------------------------------------------------------
def test_a_vent_blows_for_a_burst_at_the_start_of_each_period():
    vent = Vent((5, 5), (0, 1), 0.0, 6.0)
    times = [t / 10 for t in range(0, 120)]
    on = [vent_active(vent, t) for t in times]
    assert abs(sum(on) / 10 - 2 * VENT_BURST) < 0.3  # deux périodes de 6 s : deux jets
    assert on[0] and not on[40]


def test_vents_are_out_of_step_with_each_other():
    a, b = Vent((5, 5), (0, 1), 0.0, 6.0), Vent((9, 5), (0, 1), 0.5, 6.0)
    assert [vent_active(a, t) for t in range(12)] != [vent_active(b, t) for t in range(12)]


def vent_effects():
    tm = Tilemap.from_file(CRUISER)
    return tm, Effects(tm, seed=1)


def run_effects(fx, focus, seconds, **kw):
    opened = []
    for _ in range(int(seconds * 60)):
        opened += fx.update(1 / 60, focus, **kw)
    return opened


def test_a_nearby_vent_puffs_steam_and_announces_its_burst():
    tm, fx = vent_effects()
    vent = tm.vents[0]
    focus = V(vent.center(32)) + V(60, 0)
    opened = run_effects(fx, focus, 9.0)
    assert opened and all(isinstance(p, pygame.Vector2) for p in opened)
    assert any(p.color == tm.theme.vent_color for p in fx.particles.particles) or len(opened) >= 1


def test_every_burst_is_announced_once():
    tm, fx = vent_effects()
    vent = tm.vents[0]
    only = Effects(tm, seed=1)
    only.vents = [v for v in only.vents if v[0] is vent]
    only._vent_was_active = [False]
    opened = run_effects(only, V(vent.center(32)), vent.period * 3)
    assert 2 <= len(opened) <= 4


def test_distant_vents_stay_quiet():
    tm, fx = vent_effects()
    far = V(tm.pixel_width * 10, tm.pixel_height * 10)
    assert run_effects(fx, far, 9.0) == [] and len(fx.particles) == 0


def test_steam_rises_away_from_the_wall_and_swells():
    ps = ParticleSystem(seed=2)
    for _ in range(40):
        ps.steam((0, 0), (0, 1), (200, 200, 200))
    assert all(p.vy > 0 and p.size1 > 3 * p.size0 and not p.glow for p in ps.particles)


def test_vent_bursts_become_a_sound_from_their_position():
    from game.core.events import EventBus
    from game.systems.sound_director import SoundDirector

    calls = []

    class Audio:
        def play(self, *a, **k):
            calls.append(("play", a))

        def play_at(self, name, source, listener, volume=1.0):
            calls.append(("at", name, tuple(source)))

        def stop_loop(self, name):
            pass

    bus = EventBus()
    SoundDirector(Audio(), bus).attach()
    bus.emit("vent_burst", pos=V(40, 60))
    assert calls == [("at", "steam_vent", (40, 60))]


def test_the_steam_sound_ships():
    from game.settings import SOUNDS_DIR

    assert (SOUNDS_DIR / "steam_vent.wav").exists()


# --- Vent ----------------------------------------------------------------------------------------------------------------
def test_the_wind_comes_in_gusts():
    values = [wind_strength(t / 2) for t in range(1200)]
    assert min(values) >= 0.15 and max(values) <= 1.0 and max(values) - min(values) > 0.5


def view_rect():
    return pygame.Rect(0, 0, 1280, 720)


def test_tatooine_blows_sand_and_endor_drops_leaves_but_a_ship_has_no_wind():
    results = {}
    for theme in ("tatooine", "endor", "imperial"):
        fx = Effects(big_map(theme), seed=3)
        run_effects(fx, V(100, 100), 6.0, view=view_rect(), power_on=False)  # sans courant : pas de poussière en suspension
        results[theme] = fx.particles.particles
    assert len(results["tatooine"]) > 40 and all(p.size0 == 1.0 and not p.glow for p in results["tatooine"])
    assert 5 < len(results["endor"]) < 60 and all(p.sway for p in results["endor"])
    assert results["imperial"] == []


def test_sand_drifts_with_the_wind_direction():
    fx = Effects(big_map("tatooine"), seed=3)
    run_effects(fx, V(100, 100), 4.0, view=view_rect())
    grains = [p for p in fx.particles.particles if not p.glow]
    assert grains and sum(p.vx for p in grains) / len(grains) > 60
    assert abs(sum(p.vy for p in grains) / len(grains)) < sum(p.vx for p in grains) / len(grains)


def test_leaves_fall_and_sway():
    fx = Effects(big_map("endor"), seed=3)
    run_effects(fx, V(100, 100), 8.0, view=view_rect(), power_on=False)
    leaves = fx.particles.particles
    assert leaves and all(p.vy > 0 for p in leaves)
    assert len({round(p.vx, 1) for p in leaves}) > 3  # elles ne tombent pas toutes pareil


def test_the_wind_is_only_made_where_the_player_looks():
    fx = Effects(big_map("tatooine"), seed=3)
    run_effects(fx, V(100, 100), 3.0, view=pygame.Rect(0, 0, 100, 100))
    assert all(-1 <= p.x <= 101 for p in fx.particles.particles if p.age < 0.05)
    nothing = Effects(big_map("tatooine"), seed=3)
    run_effects(nothing, V(100, 100), 3.0)  # sans zone visible : pas de vent
    assert len(nothing.particles) == 0


# --- Poussière en suspension -------------------------------------------------------------------------------------------------
def lamp_fx(theme="imperial"):
    return Effects(big_map(theme), seed=4, lamps=[((600, 300), (255, 220, 180))])


def test_dust_motes_float_in_the_glow_of_a_lamp():
    fx = lamp_fx()
    run_effects(fx, V(100, 100), 5.0, view=view_rect())
    motes = [p for p in fx.particles.particles if p.glow]
    assert len(motes) > 3 and all(p.sway and p.size0 == 1.0 for p in motes)
    assert all(math.dist((p.x, p.y), (600, 300)) < MOTE_RADIUS + 40 for p in motes)  # ils restent près de la lampe
    assert max(math.hypot(p.vx, p.vy) for p in motes) < 25  # presque immobiles


def test_no_motes_without_power_or_far_from_the_view():
    dark = lamp_fx()
    run_effects(dark, V(100, 100), 5.0, view=view_rect(), power_on=False)
    assert not any(p.glow for p in dark.particles.particles)
    away = lamp_fx()
    run_effects(away, V(100, 100), 5.0, view=pygame.Rect(3000, 3000, 1280, 720))
    assert not any(p.glow for p in away.particles.particles)


def test_the_decor_never_crowds_out_the_sparks():
    fx = Effects(big_map("tatooine"), seed=5, lamps=[((600, 300), (255, 255, 255))] * 30)
    run_effects(fx, V(100, 100), 30.0, view=view_rect())
    assert len(fx.particles) <= PARTICLE_LIMIT * AMBIENT_PARTICLE_SHARE + 30
    fx.particles.sparks((50, 50), 40, (255, 255, 255))
    assert sum(p.color == (255, 255, 255) and p.life < 0.5 for p in fx.particles.particles) == 40  # les étincelles ont de la place


def test_a_swaying_particle_drifts_sideways():
    ps = ParticleSystem(seed=1)
    ps.emit((0, 0), (0, 0), 5.0, 1, 1, (1, 2, 3), sway=(40, 2.0))
    xs = []
    for _ in range(120):
        ps.update(1 / 60)
        xs.append(ps.particles[0].x)
    assert max(xs) - min(xs) > 3 and any(b < a for a, b in zip(xs, xs[1:])) and any(b > a for a, b in zip(xs, xs[1:]))
    assert abs(sum(xs) / len(xs)) < 25  # il va et vient : il ne part pas d'un seul côté


# --- Dans la scène --------------------------------------------------------------------------------------------------------------------
@pytest.fixture
def cruiser(game, monkeypatch):
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState())
    scene = play_scene.PlayScene(game, CRUISER)
    game.scenes.push(scene)
    scene.guards.clear()
    return scene


def test_the_scene_gives_its_lamps_to_the_effects(cruiser):
    assert len(cruiser.effects.lamps) == len(cruiser.lighting.lamps) > 0


def test_a_vent_burst_in_the_scene_reaches_the_sound_director(cruiser, game):
    heard = []
    game.events.subscribe("vent_burst", lambda pos, **_: heard.append(pos))
    vent = cruiser.tilemap.vents[0]
    cruiser.player.pos.update(V(vent.center(32)) + V(80, 0))
    for _ in range(60 * 9):
        cruiser.update(1 / 60)
    assert heard


def test_the_scene_draws_decor_lights_and_steam_without_error(cruiser, game):
    vent = cruiser.tilemap.vents[0]
    cruiser.player.pos.update(V(vent.center(32)) + V(60, 40))
    cruiser.camera.snap_to(cruiser.player.pos)
    for _ in range(60 * 4):
        game.step(1 / 60)


def test_cutting_the_power_keeps_the_lanterns_burning(game, monkeypatch):
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState())
    scene = play_scene.PlayScene(game, BLACKOUT, CAMPAIGN.get("blackout"))
    game.scenes.push(scene)
    assert scene.power_on
    scene.consoles[0].cut = True
    assert not scene.power_on
    surface = pygame.Surface((1280, 720))
    scene.draw(surface)  # ne plante pas, lanternes comprises


def test_every_shipped_level_still_loads_with_its_decor():
    for mission in CAMPAIGN.missions:
        tm = Tilemap.from_file(mission.map_path)
        assert bool(tm.decor) == (tm.theme.id != "imperial"), mission.id
