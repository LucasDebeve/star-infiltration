"""Effets visuels : particules (poussière, étincelles, fumée), et ce qui les déclenche dans la scène."""
import pygame
import pytest

from game.ai.guard import GuardState
from game.core.camera import Camera
from game.core.input import InputState
from game.scenes import play_scene
from game.settings import DUST_CHASE_INTERVAL, NOZZLE_SPACING, PARTICLE_LIMIT, SMOKE_RANGE, SPARK_BURST, SPARK_RATE
from game.systems.effects import Effects, ship_nozzles
from game.ui.particles import Particle, ParticleSystem, Pulse
from game.world.props import Prop
from game.world.tilemap import Tilemap
from tests.paths import BLACKOUT, CAMPAIGN, CRUISER, SANDBOX, TRAINING


# --- Particule et cadence ---------------------------------------------------------------
def test_a_particle_ages_grows_and_fades():
    p = Particle(0, 0, 0, 0, 2.0, 2.0, 10.0, (1, 2, 3), 255, 0.0, False)
    assert p.size == 2.0 and p.opacity == 0.0  # à la naissance : invisible, il apparaît en un instant
    p.age = 1.0
    assert p.size == pytest.approx(6.0) and 0 < p.opacity < 1
    p.age = 2.0
    assert p.t == 1.0 and p.opacity == 0.0


def test_a_pulse_emits_the_right_count_over_time_without_losing_the_remainder():
    pulse = Pulse(10)
    assert sum(pulse.count(1 / 60) for _ in range(600)) in (99, 100, 101)  # 10 s à 10 par seconde
    assert Pulse(1000).count(0.01) in (10, 11)


def test_two_pulses_do_not_tick_in_lockstep():
    import random

    rng = random.Random(3)
    assert Pulse(2, rng)._carry != Pulse(2, rng)._carry


# --- Système ---------------------------------------------------------------------------------
def test_particles_move_slow_down_and_die():
    ps = ParticleSystem(seed=1)
    ps.emit((0, 0), (100, 0), 0.5, 2, 2, (255, 255, 255), drag=4.0)
    ps.update(0.1)
    p = ps.particles[0]
    assert p.x == pytest.approx(10.0) and 0 < p.vx < 100
    for _ in range(10):
        ps.update(0.1)
    assert len(ps) == 0 and p.x < 40  # morte, et le frottement l'a arrêtée avant


def test_the_particle_count_is_capped():
    ps = ParticleSystem(seed=1, limit=5)
    assert all(ps.emit((0, 0), (0, 0), 5, 1, 1, (0, 0, 0)) for _ in range(5))
    assert not ps.emit((0, 0), (0, 0), 5, 1, 1, (0, 0, 0)) and len(ps) == 5
    ps.sparks((0, 0), 50, (255, 255, 255))
    assert len(ps) == 5


def test_the_default_cap_is_generous_but_finite():
    assert 100 < PARTICLE_LIMIT < 5000


def test_the_same_seed_gives_the_same_effects():
    a, b = ParticleSystem(seed=9), ParticleSystem(seed=9)
    for ps in (a, b):
        ps.dust((10, 10), True)
        ps.sparks((5, 5), 4, (255, 0, 0))
        ps.smoke((0, 0), (0, 1))
        ps.update(0.1)
    assert [(p.x, p.y) for p in a.particles] == [(p.x, p.y) for p in b.particles]


def test_running_raises_more_and_bigger_dust_than_walking():
    walk, run = ParticleSystem(seed=1), ParticleSystem(seed=1)
    walk.dust((0, 0), False)
    run.dust((0, 0), True)
    assert len(run) > len(walk)
    assert max(p.size1 for p in run.particles) > max(p.size1 for p in walk.particles)
    assert not any(p.glow for p in walk.particles + run.particles)


def test_sparks_glow_and_are_short_lived():
    ps = ParticleSystem(seed=1)
    ps.sparks((0, 0), 20, (255, 200, 0))
    assert len(ps) == 20 and all(p.glow and p.life < 0.5 for p in ps.particles)


def test_smoke_drifts_away_along_the_exhaust_and_swells():
    ps = ParticleSystem(seed=1)
    for _ in range(30):
        ps.smoke((0, 0), (0, 1))
    assert all(p.vy > 0 and abs(p.vx) < p.vy for p in ps.particles)  # reste dans la direction de l'échappement
    assert all(p.size1 > 3 * p.size0 for p in ps.particles) and all(not p.glow for p in ps.particles)


# --- Dessin ---------------------------------------------------------------------------------------
def painted(surface):
    return pygame.mask.from_threshold(surface, (0, 0, 0), (1, 1, 1, 255)).count() < surface.get_width() * surface.get_height()


@pytest.fixture
def view():
    return Camera(200, 200, 400, 400), pygame.Surface((200, 200))


def test_soft_and_glowing_particles_are_drawn_in_their_own_pass(view):
    camera, surface = view
    ps = ParticleSystem(seed=1)
    ps.emit((100, 100), (0, 0), 1, 6, 6, (200, 200, 200), alpha=255)  # douce
    ps.emit((100, 100), (0, 0), 1, 6, 6, (200, 200, 200), glow=True)
    ps.update(0.2)
    surface.fill((0, 0, 0))
    ps.draw_glow(surface, camera)
    glow_only = pygame.image.tobytes(surface, "RGB")
    surface.fill((0, 0, 0))
    ps.draw_soft(surface, camera)
    soft_only = pygame.image.tobytes(surface, "RGB")
    assert painted(pygame.image.frombytes(glow_only, (200, 200), "RGB")) and painted(pygame.image.frombytes(soft_only, (200, 200), "RGB"))
    assert glow_only != soft_only


def test_glowing_sparks_brighten_what_is_behind_them(view):
    camera, surface = view
    ps = ParticleSystem(seed=1)
    ps.emit((100, 100), (0, 0), 1, 5, 5, (100, 100, 100), glow=True)
    ps.update(0.2)
    surface.fill((50, 50, 50))
    ps.draw_glow(surface, camera)
    assert surface.get_at(camera.world_to_screen((100, 100)))[0] > 50  # additif : plus clair que le fond


def test_offscreen_particles_are_not_drawn(view):
    camera, surface = view
    ps = ParticleSystem(seed=1)
    ps.emit((390, 390), (0, 0), 1, 6, 6, (200, 200, 200))  # hors de la caméra (qui regarde en haut à gauche)
    ps.update(0.2)
    surface.fill((0, 0, 0))
    ps.draw_soft(surface, camera)
    assert not painted(surface)


# --- Tuyères des vaisseaux --------------------------------------------------------------------------
@pytest.mark.parametrize("facing,direction", [("N", (0, 1)), ("S", (0, -1)), ("E", (-1, 0)), ("O", (1, 0))])
def test_the_exhaust_leaves_by_the_stern(facing, direction):
    prop = Prop("ship", 4, 4, 3, 3, facing)
    nozzles = ship_nozzles(prop, 32)
    assert all(tuple(d) == direction for _, d in nozzles)
    hull = pygame.Rect(4 * 32, 4 * 32, 96, 96)
    for pos, d in nozzles:
        assert not hull.collidepoint(pos)  # juste derrière la coque, pas dedans
        assert hull.inflate(16, 16).collidepoint(pos)
        assert (pos - pygame.Vector2(hull.center)).dot(d) > 0  # côté poupe


def test_a_wider_ship_has_more_nozzles():
    narrow = ship_nozzles(Prop("ship", 0, 0, 2, 3, "N"), 32)
    wide = ship_nozzles(Prop("ship", 0, 0, 6, 3, "N"), 32)
    assert len(narrow) == 1 and len(wide) == 6 // NOZZLE_SPACING
    xs = [p.x for p, _ in wide]
    assert xs == sorted(xs) and 0 < xs[0] and xs[-1] < 6 * 32


# --- Le contrôleur d'effets -----------------------------------------------------------------------------
def test_ships_smoke_only_when_the_player_is_near():
    tm = Tilemap.from_file(CRUISER)
    ship = next(p for p in tm.props if p.kind == "ship")
    near = pygame.Vector2((ship.x + ship.w / 2) * 32, (ship.y + ship.h / 2) * 32)
    fx = Effects(tm, seed=1)
    assert fx.nozzles
    for _ in range(120):
        fx.update(1 / 60, near + pygame.Vector2(SMOKE_RANGE * 5, 0))
    assert len(fx.particles) == 0  # trop loin
    for _ in range(120):
        fx.update(1 / 60, near)
    assert len(fx.particles) > 0


def test_a_map_without_ships_makes_no_smoke():
    fx = Effects(Tilemap.from_file(TRAINING), seed=1)
    assert fx.nozzles == []


def test_hacking_sparks_come_faster_as_the_download_advances():
    def count(progress):
        fx = Effects(Tilemap.from_text("###\n#P#\n###"), seed=1)
        for _ in range(60):
            fx.hacking("terminal", (50, 50), progress, 1 / 60)
        return len(fx.particles)

    assert count(0.0) < count(1.0)
    low, high = SPARK_RATE
    assert abs(count(1.0) - high) < 6 and abs(count(0.0) - low) < 4


def test_a_burst_scales_with_the_source():
    fx = Effects(Tilemap.from_text("###\n#P#\n###"), seed=1)
    fx.burst("console", (1, 1))
    assert len(fx.particles) == SPARK_BURST["console"] > SPARK_BURST["terminal"] > SPARK_BURST["field"]


def test_a_footstep_raises_a_puff_of_dust():
    fx = Effects(Tilemap.from_text("###\n#P#\n###"), seed=1)
    fx.footstep((50, 50), "walk")
    assert len(fx.particles) == 1


def chasing_guard_dust(state):
    from game.ai.guard import Guard

    tm = Tilemap.from_file(SANDBOX)
    guard = Guard.from_spawn(tm, tm.spawns_of("guard")[0])
    guard.state = state
    fx = Effects(Tilemap.from_text("###\n#P#\n###"), seed=1)
    puffs = 0
    for _ in range(60):
        before = len(fx.particles)
        fx.update(1 / 60, guard.pos, [guard])
        puffs += len(fx.particles) > before
    return puffs


def test_only_chasing_guards_raise_dust_at_a_steady_rhythm():
    assert chasing_guard_dust(GuardState.PATROL) == 0
    assert chasing_guard_dust(GuardState.INVESTIGATE) == 0
    puffs = chasing_guard_dust(GuardState.CHASE)
    assert abs(puffs - 1.0 / DUST_CHASE_INTERVAL) <= 2  # un nuage tous les DUST_CHASE_INTERVAL secondes


# --- Dans la scène ----------------------------------------------------------------------------------------------
@pytest.fixture
def scene(game, monkeypatch):
    holder = {"input": InputState()}
    monkeypatch.setattr(play_scene, "read_input", lambda: holder["input"])
    s = play_scene.PlayScene(game, SANDBOX)
    game.scenes.push(s)
    s.guards.clear()
    s.holder = holder
    return s


def dust_count(scene):
    return sum(p.color == scene.effects.dust_color for p in scene.effects.particles.particles)


def test_walking_raises_dust_but_standing_still_does_not(scene):
    for _ in range(60):
        scene.update(1 / 60)
    assert dust_count(scene) == 0  # (le décor, lui, anime déjà l'air : poussière en suspension, vapeur...)
    scene.holder["input"] = InputState(move=pygame.Vector2(1, 0), run=True)
    for _ in range(60):
        scene.update(1 / 60)
    assert dust_count(scene) > 0


def test_a_hack_throws_sparks_then_a_burst_when_done(scene):
    terminal = scene.terminals[0]
    scene.player.pos.update(terminal.pos.x - 20, terminal.pos.y)
    terminal.start("data")
    sparks = 0
    for _ in range(int(2.6 * 60)):
        scene.update(1 / 60)
        sparks = max(sparks, sum(p.glow for p in scene.effects.particles.particles))
    assert terminal.hacked and sparks > 5


def test_toggling_a_field_sparks_along_its_lines(scene):
    field = next(iter(scene.tilemap.fields.values()))
    before = len(scene.effects.particles)
    scene._on_field_toggled(field.id, True)
    assert len(scene.effects.particles) - before == SPARK_BURST["field"] * len(field.runs)


def test_cutting_the_power_throws_a_big_burst(game, monkeypatch):
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState())
    scene = play_scene.PlayScene(game, BLACKOUT, CAMPAIGN.get("blackout"))
    scene._on_power_cut(scene.consoles[0])
    assert len(scene.effects.particles) == SPARK_BURST["console"]


def test_a_restart_clears_the_effects(scene):
    scene.effects.particles.dust((0, 0), True)
    scene.restart()
    assert len(scene.effects.particles) == 0 and scene.effects.time == 0


def test_a_full_frame_with_effects_is_drawn(scene):
    scene.effects.particles.sparks(scene.player.pos, 10, (255, 255, 255))
    scene.effects.particles.dust(scene.player.pos, True)
    scene.game.step(1 / 60)
