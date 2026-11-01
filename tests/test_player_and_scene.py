import math

import pygame
import pytest

from game.ai.guard import GuardState
from game.core.game import Game
from game.core.input import InputState
from game.entities.player import Player, Stance
from game.items import Item, ItemKind
from game.scenes import play_scene
from game.scenes.pause_scene import PauseScene
from game.settings import DECOY_SIZE, FIELD_LIGHT_SPACING, THROW_KEY, THROW_RANGE
from game.settings import MAPS_DIR as _MAPS
from game.systems.interaction import InteractionContext
from game.world.tilemap import Tilemap
from tests.paths import SANDBOX

ROOM = Tilemap.from_text("######\n#....#\n#....#\n######")


def run(player, inp, frames=60, dt=1 / 60):
    for _ in range(frames):
        player.update(dt, ROOM, inp)


def test_speed_depends_on_stance():
    distances = {}
    for name, inp in {
        "crouch": InputState(move=pygame.Vector2(1, 0), crouch=True),
        "walk": InputState(move=pygame.Vector2(1, 0)),
        "run": InputState(move=pygame.Vector2(1, 0), run=True),
    }.items():
        p = Player(64, 64)
        run(p, inp, frames=20)
        distances[name] = p.pos.x - 64
    assert 0 < distances["crouch"] < distances["walk"] < distances["run"]


def test_crouch_beats_run():
    p = Player(40, 64)
    p.update(1 / 60, ROOM, InputState(move=pygame.Vector2(1, 0), run=True, crouch=True))
    assert p.stance is Stance.CROUCH


def test_diagonal_not_faster():
    straight, diagonal = Player(60, 60), Player(60, 60)
    straight.update(0.1, ROOM, InputState(move=pygame.Vector2(1, 0)))
    diagonal.update(0.1, ROOM, InputState(move=pygame.Vector2(1, 1)))  # non normalisé exprès
    assert straight.pos.distance_to((60, 60)) == pytest.approx(diagonal.pos.distance_to((60, 60)))


def test_noise_radius():
    p = Player(60, 60)
    p.update(1 / 60, ROOM, InputState())
    assert p.noise_radius == 0  # à l'arrêt
    p.update(1 / 60, ROOM, InputState(move=pygame.Vector2(1, 0), crouch=True))
    assert p.noise_radius == 0  # accroupi
    p.update(1 / 60, ROOM, InputState(move=pygame.Vector2(1, 0)))
    walk = p.noise_radius
    p.update(1 / 60, ROOM, InputState(move=pygame.Vector2(1, 0), run=True))
    assert 0 < walk < p.noise_radius


def test_player_cannot_leave_room():
    p = Player(60, 60)
    run(p, InputState(move=pygame.Vector2(1, 1), run=True), frames=300)
    assert 32 <= p.rect.left and p.rect.right <= 160
    assert 32 <= p.rect.top and p.rect.bottom <= 96


def test_facing_follows_aim():
    p = Player(60, 60)
    p.update(1 / 60, ROOM, InputState(), aim_world=pygame.Vector2(60, 0))
    assert p.facing.y == pytest.approx(-1)


@pytest.fixture
def game():
    g = Game()
    pygame.event.clear()  # le pilote vidéo factice envoie des « perte de focus » au démarrage, qui mettraient en pause
    yield g
    pygame.quit()


def test_play_scene_smoke(game, monkeypatch):
    """Lance la vraie scène sur la vraie carte : le joueur avance, reste hors des murs, la caméra suit."""
    scene = play_scene.PlayScene(game, SANDBOX)
    game.scenes.push(scene)
    scene.guards.clear()  # ici on teste le déplacement, pas l'IA (voir test_guard et les tests de scène ci-dessous)
    # On se place au début du long couloir principal (tuile 3, 10), dégagé vers l'est.
    scene.player.pos.update(3.5 * 32, 10.5 * 32)
    scene.camera.snap_to(scene.player.pos)
    start = scene.player.pos.copy()
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState(move=pygame.Vector2(1, 0), run=True))
    for _ in range(240):
        game.step(1 / 60)
    assert scene.player.pos.x > start.x
    tx, ty = scene.tilemap.world_to_tile(*scene.player.pos)
    assert not scene.tilemap.is_solid(tx, ty)
    assert scene.camera.pos.x > 0

    scene.debug = True  # le mode debug doit aussi se dessiner sans erreur
    game.step(1 / 60)


def test_escape_opens_the_pause_menu_instead_of_quitting(game):
    scene = play_scene.PlayScene(game, SANDBOX)
    game.scenes.push(scene)
    game.running = True
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    assert game.running is True
    assert isinstance(game.scenes.current, PauseScene)


def test_footsteps_follow_stance_and_cadence():
    p = Player(60, 60)
    steps = {}
    for name, inp in {
        "idle": InputState(),
        "crouch": InputState(move=pygame.Vector2(1, 0), crouch=True),
        "walk": InputState(move=pygame.Vector2(1, 0)),
        "run": InputState(move=pygame.Vector2(1, 0), run=True),
    }.items():
        p = Player(40, 60)
        count = 0
        for _ in range(60):  # 1 seconde
            p.update(1 / 60, ROOM, inp)
            count += p.made_step
            if p.pos.x > 150:
                p.pos.x = 40
        steps[name] = count
    assert steps["idle"] == steps["crouch"] == 0
    assert 0 < steps["walk"] < steps["run"]


def test_first_step_is_immediate_and_resets_after_stopping():
    p = Player(60, 60)
    p.update(1 / 60, ROOM, InputState(move=pygame.Vector2(1, 0)))
    assert p.made_step
    p.update(1 / 60, ROOM, InputState(move=pygame.Vector2(1, 0)))
    assert not p.made_step  # il faut attendre l'intervalle
    p.update(1 / 60, ROOM, InputState())
    p.update(1 / 60, ROOM, InputState(move=pygame.Vector2(1, 0)))
    assert p.made_step  # on repart : nouveau pas aussitôt


def test_detectability_by_stance():
    p = Player(60, 60)
    values = {}
    for name, inp in {
        "crouch": InputState(crouch=True),
        "walk": InputState(),
        "run": InputState(run=True),
    }.items():
        p.update(1 / 60, ROOM, inp)
        values[name] = p.detectability
    assert values["crouch"] < values["walk"] < values["run"]


# --- Scène : gardes, bruit, capture ------------------------------------------
@pytest.fixture
def scene(game, monkeypatch):
    s = play_scene.PlayScene(game, SANDBOX)
    game.scenes.push(s)
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState())
    return s


def place(scene, guard, tile):
    guard.pos.update((tile[0] + 0.5) * 32, (tile[1] + 0.5) * 32)


def test_scene_spawns_one_guard_per_g(scene):
    assert len(scene.guards) == len(scene.tilemap.spawns_of("guard"))
    assert all(g.state is GuardState.PATROL for g in scene.guards)
    assert scene.threat is GuardState.PATROL


def test_footstep_noise_makes_a_nearby_guard_investigate(scene, monkeypatch):
    guard = scene.guards[0]
    scene.guards[:] = [guard]
    place(scene, guard, (6, 27))
    scene.player.pos.update(4.5 * 32, 27.5 * 32)
    guard.angle = 0.0  # regarde vers l'est, le joueur est derrière lui (à l'ouest) : il ne peut que l'entendre
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState(move=pygame.Vector2(0, 1), run=True))
    scene.update(1 / 60)
    assert guard.state is GuardState.INVESTIGATE
    assert scene.threat is GuardState.INVESTIGATE


def test_crouching_player_is_inaudible(scene, monkeypatch):
    guard = scene.guards[0]
    scene.guards[:] = [guard]
    place(scene, guard, (6, 27))
    scene.player.pos.update(4.5 * 32, 27.5 * 32)
    guard.angle = 0.0
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState(move=pygame.Vector2(0, 1), crouch=True))
    for _ in range(30):
        scene.update(1 / 60)
    assert guard.state is GuardState.PATROL


def test_noise_event_alerts_guards(scene):
    guard = scene.guards[0]
    scene.guards[:] = [guard]
    place(scene, guard, (6, 27))
    scene.game.events.emit("noise", pos=pygame.Vector2(5.5 * 32, 27.5 * 32), radius=200)
    assert guard.state is GuardState.INVESTIGATE


def test_scene_unsubscribes_on_exit(game):
    s = play_scene.PlayScene(game, SANDBOX)
    game.scenes.push(s)
    game.scenes.pop()
    game.events.emit("noise", pos=pygame.Vector2(0, 0), radius=10)  # ne doit rien casser


def test_getting_caught_freezes_the_game_and_r_restarts(scene, monkeypatch):
    guard = scene.guards[0]
    scene.guards[:] = [guard]
    start = pygame.Vector2(scene.player.pos)
    place(scene, guard, (4, 27))
    guard._start_chase(scene.player)
    scene.player.pos.update(4.5 * 32 + 20, 27.5 * 32)
    scene.update(1 / 60)
    assert scene.caught
    frozen = pygame.Vector2(scene.player.pos)
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState(move=pygame.Vector2(0, 1)))
    scene.update(1 / 60)
    assert scene.player.pos == frozen  # plus de déplacement une fois capturé

    scene.game.step(1 / 60)  # l'écran de capture doit se dessiner sans erreur
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r))
    assert not scene.caught
    assert scene.player.pos == start
    assert all(g.state is GuardState.PATROL for g in scene.guards)
    assert len(scene.guards) == len(scene.tilemap.spawns_of("guard"))


def test_r_does_nothing_while_playing(scene):
    scene.player.pos.update(100, 100)
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r))
    assert scene.player.pos == pygame.Vector2(100, 100)


def test_full_frame_with_guards_chasing_and_debug(scene):
    """Dessin complet avec cônes, bulles et debug : ne doit pas lever d'exception."""
    guard = scene.guards[0]
    scene.player.pos.update(guard.pos)
    scene.camera.snap_to(scene.player.pos)
    guard._start_chase(scene.player)
    scene.debug = True
    for _ in range(5):
        scene.game.step(1 / 60)
    scene.guards[1].awareness = 0.5
    scene.game.step(1 / 60)


def test_a_full_minute_of_idle_play_on_the_real_level(scene):
    """Les 8 gardes patrouillent une minute sans rien casser et sans quitter les couloirs."""
    for _ in range(60 * 60):
        scene.update(1 / 60)
    for guard in scene.guards:
        tx, ty = scene.tilemap.world_to_tile(*guard.pos)
        assert not scene.tilemap.is_solid(tx, ty)


# --- Scène : objets, portes, terminal, leurre, fin de mission -----------------
KEY_E = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_e)
KEY_F = pygame.event.Event(pygame.KEYDOWN, key=THROW_KEY)
DECOY_ITEM = Item(ItemKind.DECOY)


def teleport(scene, tile):
    scene.player.pos.update((tile[0] + 0.5) * 32, (tile[1] + 0.5) * 32)
    scene.camera.snap_to(scene.player.pos)


def toasts(scene):
    return [t[0] for t in scene.hud._toasts]


def press_e(scene):
    scene.handle_event(KEY_E)
    scene.update(1 / 60)


def test_scene_builds_items_doors_and_terminal(scene):
    assert scene.tilemap.spawns_of("terminal") and len(scene.terminals) == 1
    assert scene.exit_pad is not None
    assert len(scene.doors) == len(scene.tilemap.door_groups()) == 7
    kinds = sorted(p.item.kind.value + str(p.item.level) for p in scene.pickups)
    assert kinds == ["decoy0"] * 4 + ["keycard1", "keycard2"]
    assert scene.objective.startswith("Objectif : pirater")


def test_walking_over_an_item_picks_it_up(scene):
    scene.guards.clear()
    pickup = next(p for p in scene.pickups if p.item.kind is ItemKind.DECOY)
    scene.player.pos.update(pickup.pos)
    scene.update(1 / 60)
    assert scene.inventory.count(DECOY_ITEM) == 1 and pickup not in scene.pickups
    assert toasts(scene) == ["Ramassé : Leurre"]


def test_free_door_opens_on_e_and_guards_hear_it(scene):
    door = next(d for d in scene.doors if d.level == 0 and d.tiles[0] == (22, 27))
    guard = scene.guards[0]
    scene.guards[:] = [guard]
    teleport(scene, (21, 27))
    place(scene, guard, (20, 27))  # à ~2 tuiles de la porte : dans le rayon de son bruit
    guard.angle = math.pi  # il regarde à l'ouest, le joueur est derrière lui : il ne peut que l'entendre
    press_e(scene)
    assert door.is_open and not scene.tilemap.is_solid(22, 27)
    assert guard.state is GuardState.INVESTIGATE  # le bruit de la porte l'a alerté


def test_locked_door_refuses_and_says_why(scene):
    scene.guards.clear()
    door = next(d for d in scene.doors if d.tiles[0] == (24, 9))
    teleport(scene, (24, 10))
    press_e(scene)
    assert not door.is_open and scene.tilemap.is_solid(24, 9)
    assert scene.hud._denied_timer > 0  # l'invite « Badge niv. 1 requis » se secoue
    assert scene.interaction.prompt.label == "Badge niv. 1 requis"


def test_keycard_unlocks_the_door(scene):
    scene.guards.clear()
    scene.inventory.add(Item(ItemKind.KEYCARD, 1))
    door = next(d for d in scene.doors if d.tiles[0] == (24, 9))
    teleport(scene, (24, 10))
    press_e(scene)
    assert door.is_open and scene.tilemap.same_region((24, 10), (24, 8))


def test_open_door_changes_what_guards_can_reach(scene):
    """Une fois la porte ouverte, les zones sont recalculées : l'A* des gardes passe par là."""
    from game.ai.pathfinding import find_path

    assert find_path(scene.tilemap, (24, 10), (24, 8)) == []
    scene.guards.clear()
    scene.inventory.add(Item(ItemKind.KEYCARD, 1))
    teleport(scene, (24, 10))
    press_e(scene)
    assert find_path(scene.tilemap, (24, 10), (24, 8))


def test_hacking_the_terminal_in_the_scene(scene, monkeypatch):
    from game.settings import HACK_TIME

    scene.guards.clear()
    teleport(scene, (57, 5))
    terminal = scene.terminals[0]
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_e))
    for _ in range(2):
        scene.update(1 / 60)
    menu = scene.game.scenes.current
    assert type(menu).__name__ == "TerminalScene" and not terminal.hacked  # le menu s'ouvre, rien n'est encore fait
    assert [a[0] for a in menu.actions] == ["data"] and menu.choose("data")
    for _ in range(int(HACK_TIME * 60 * 0.6)):
        scene.update(1 / 60)
    assert terminal.job is not None and scene.hack_progress > 0 and not terminal.hacked
    for _ in range(int(HACK_TIME * 60 * 0.6)):
        scene.update(1 / 60)
    assert terminal.hacked and terminal.job is None
    assert scene.inventory.count(Item(ItemKind.DATA)) == 1
    assert scene.objective.startswith("Objectif : rejoindre la sortie")
    assert any("Données" in t for t in toasts(scene))


def test_exit_without_data_is_refused(scene):
    scene.guards.clear()
    teleport(scene, (3, 31))
    press_e(scene)
    assert not scene.won and scene.hud._denied_timer > 0
    assert scene.interaction.prompt.label == "Données requises"


def test_mission_complete_then_restart_resets_everything(scene):
    scene.guards.clear()
    scene.inventory.add(Item(ItemKind.DATA))
    scene.inventory.add(Item(ItemKind.KEYCARD, 1))
    next(d for d in scene.doors if d.tiles[0] == (22, 27)).interact(InteractionContext(scene.tilemap, scene.inventory, scene.game.events))
    teleport(scene, (3, 31))
    press_e(scene)
    assert scene.won and not scene.caught and scene.objective == ""
    frozen = pygame.Vector2(scene.player.pos)
    scene.update(1 / 60)
    assert scene.player.pos == frozen  # le jeu est figé
    scene.game.step(1 / 60)  # l'écran de victoire se dessine

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r))
    assert not scene.won
    assert scene.tilemap.is_solid(22, 27)  # la carte est rechargée : la porte est refermée
    assert scene.inventory.stacks() == []
    assert len(scene.pickups) == 6 and len(scene.guards) == 8
    assert scene.doors and not any(d.is_open for d in scene.doors)


def test_r_restarts_nothing_while_playing_even_with_items(scene):
    scene.inventory.add(DECOY_ITEM)
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r))
    assert scene.inventory.count(DECOY_ITEM) == 1


# --- Leurre -----------------------------------------------------------------
def aim_at(monkeypatch, scene, world_point):
    screen = scene.camera.world_to_screen(world_point)
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState(aim_screen=screen))


def throw(scene):
    scene.handle_event(KEY_F)
    scene.update(1 / 60)


def test_throw_lands_at_the_aimed_point(scene, monkeypatch):
    scene.guards.clear()
    teleport(scene, (6, 28))
    scene.inventory.add(DECOY_ITEM)
    aim_at(monkeypatch, scene, scene.player.pos + pygame.Vector2(100, 0))
    throw(scene)
    assert scene.inventory.count(DECOY_ITEM) == 0
    assert len(scene.decoys) == 1
    assert scene.decoys[0].pos.x == pytest.approx(scene.player.pos.x + 100, abs=2)


def test_throw_range_is_limited(scene, monkeypatch):
    scene.guards.clear()
    teleport(scene, (4, 28))
    scene.inventory.add(DECOY_ITEM)
    aim_at(monkeypatch, scene, scene.player.pos + pygame.Vector2(2000, 0))
    throw(scene)
    assert scene.decoys[0].pos.distance_to(scene.player.pos) == pytest.approx(THROW_RANGE, abs=2)


def test_throw_stops_at_walls(scene, monkeypatch):
    scene.guards.clear()
    teleport(scene, (3, 32))  # le mur du bas commence en y = 34 tuiles, à ~1,5 tuile du joueur
    scene.inventory.add(DECOY_ITEM)
    aim_at(monkeypatch, scene, scene.player.pos + pygame.Vector2(0, 150))
    throw(scene)
    decoy = scene.decoys[0]
    assert not scene.tilemap.is_solid(*scene.tilemap.world_to_tile(*decoy.pos))
    assert decoy.pos.y == pytest.approx(34 * 32 - DECOY_SIZE)  # il retombe juste devant le mur


def test_throw_without_a_decoy_does_nothing(scene):
    scene.guards.clear()
    throw(scene)
    assert scene.decoys == [] and toasts(scene) == ["Aucun leurre"]


def test_decoy_lures_guards_away(scene, monkeypatch):
    guard = scene.guards[0]
    scene.guards[:] = [guard]
    teleport(scene, (4, 28))
    place(scene, guard, (10, 28))
    guard.angle = 0.0  # il regarde vers l'est, le joueur est derrière lui
    scene.inventory.add(DECOY_ITEM)
    aim_at(monkeypatch, scene, scene.player.pos + pygame.Vector2(60, 0))  # le leurre tombe à ~4 tuiles du garde
    throw(scene)
    assert guard.state is GuardState.INVESTIGATE
    assert guard.destination.distance_to(scene.decoys[0].pos) < 5


def test_decoys_expire_and_are_removed(scene):
    scene.guards.clear()
    from game.entities.decoy import Decoy

    scene.decoys.append(Decoy(100, 100))
    for _ in range(60 * 6):
        scene.update(1 / 60)
    assert scene.decoys == []


def test_cannot_throw_once_caught(scene):
    scene.inventory.add(DECOY_ITEM)
    scene.caught = True
    throw(scene)
    assert scene.decoys == [] and scene.inventory.count(DECOY_ITEM) == 1


def test_full_frame_with_prompt_toasts_inventory_and_decoys(scene):
    from game.entities.decoy import Decoy

    scene.guards.clear()
    scene.inventory.add(Item(ItemKind.KEYCARD, 2))
    scene.inventory.add(Item(ItemKind.DATA))
    scene.inventory.add(DECOY_ITEM, 3)
    teleport(scene, (57, 5))
    scene.decoys.append(Decoy(*scene.player.pos + pygame.Vector2(40, 0)))
    scene.hud.notify("Test")
    scene.update(1 / 60)  # une cible (le terminal) est à portée : l'invite se dessine
    assert scene.interaction.prompt is not None
    scene.debug = True
    scene.game.step(1 / 60)
    teleport(scene, (24, 10))  # invite refusée (porte verrouillée) et sortie en vue
    scene.inventory.remove(Item(ItemKind.KEYCARD, 2))
    scene.update(1 / 60)
    scene.game.step(1 / 60)


# --- Scène : alerte globale, renforts, verrouillage --------------------------
from game.settings import LOCKDOWN_TIME, REINFORCE_FIRST_DELAY, REINFORCE_PER_WAVE  # noqa: E402


def start_alert(scene, player_tile=(30, 10)):
    """Déclenche l'alerte proprement : un garde enfermé dans une salle scellée est déjà en poursuite."""
    sealed = next(g for g in scene.guards if scene.tilemap.world_to_tile(*g.pos) == (24, 5))
    scene.guards[:] = [sealed]
    teleport(scene, player_tile)
    sealed._start_chase(scene.player)
    scene.update(1 / 60)
    return sealed


def test_scene_is_calm_at_the_start(scene):
    assert not scene.alert.active and not scene.failed
    assert len(scene.alert.reinforcement_tiles) == 3


def test_first_chase_raises_the_global_alert(scene):
    start_alert(scene)
    assert scene.alert.active and scene.alert.time_left == pytest.approx(LOCKDOWN_TIME, abs=0.1)
    assert any("ALERTE GÉNÉRALE" in t for t in toasts(scene))
    assert all(g.alerted for g in scene.guards)


def test_objective_becomes_an_escape_when_alerted_with_the_data(scene):
    scene.inventory.add(Item(ItemKind.DATA))
    assert scene.objective.startswith("Objectif : rejoindre")
    start_alert(scene)
    assert scene.objective.startswith("FUITE")


def test_reinforcements_join_the_game_and_the_hud_announces_them(scene):
    start_alert(scene)
    before = len(scene.guards)
    for _ in range(round((REINFORCE_FIRST_DELAY + 0.5) * 60)):
        scene.update(1 / 60)
        if scene.over:
            break
    arrivals = [g for g in scene.guards if g.is_reinforcement]
    assert len(arrivals) == REINFORCE_PER_WAVE and len(scene.guards) == before + REINFORCE_PER_WAVE
    assert any("renforts" in t for t in toasts(scene))
    assert scene.threat is GuardState.INVESTIGATE or scene.threat is GuardState.CHASE


def test_reinforcements_are_updated_like_any_guard(scene):
    start_alert(scene)
    for _ in range(round((REINFORCE_FIRST_DELAY + 0.5) * 60)):
        scene.update(1 / 60)
    spawn_positions = [pygame.Vector2(g.pos) for g in scene.guards if g.is_reinforcement]
    for _ in range(60):
        scene.update(1 / 60)
        if scene.over:
            break
    moved = [g.pos.distance_to(p) for g, p in zip((g for g in scene.guards if g.is_reinforcement), spawn_positions)]
    assert all(d > 20 for d in moved)  # ils foncent vers le joueur


def test_lockdown_ends_the_game_and_freezes_it(scene):
    start_alert(scene)
    scene.alert.time_left = 0.05
    scene.update(0.1)
    assert scene.failed and scene.over and not scene.caught and not scene.won
    frozen = pygame.Vector2(scene.player.pos)
    scene.update(1 / 60)
    assert scene.player.pos == frozen
    scene.game.step(1 / 60)  # l'écran « VERROUILLAGE » se dessine


def test_exit_still_works_during_the_alert_and_beats_the_lockdown(scene):
    start_alert(scene)
    scene.guards.clear()
    scene.inventory.add(Item(ItemKind.DATA))
    teleport(scene, (3, 31))
    press_e(scene)
    assert scene.won and not scene.failed


def test_restart_clears_the_alert_and_reinforcements(scene):
    start_alert(scene)
    scene.alert.time_left = 0.05
    scene.update(0.1)
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r))
    assert not scene.failed and not scene.alert.active
    assert scene.alert.time_left == LOCKDOWN_TIME
    assert len(scene.guards) == 8 and not any(g.is_reinforcement for g in scene.guards)


def test_a_caught_player_does_not_also_fail(scene):
    sealed = start_alert(scene)
    place(scene, sealed, (30, 10))
    scene.player.pos.update(sealed.pos + pygame.Vector2(10, 0))
    scene.update(1 / 60)
    assert scene.caught and not scene.failed


def test_full_frame_during_alert_with_everything_on_screen(scene):
    start_alert(scene)
    for _ in range(round((REINFORCE_FIRST_DELAY + 0.5) * 60)):
        scene.update(1 / 60)
    scene.alert.time_left = 10  # chronomètre en clignotement
    scene.debug = True
    for _ in range(3):
        scene.game.step(1 / 60)


def test_reinforcements_withdraw_after_their_stay(scene):
    start_alert(scene)
    for _ in range(round((REINFORCE_FIRST_DELAY + 0.5) * 60)):
        scene.update(1 / 60)
    arrived = [g for g in scene.guards if g.is_reinforcement]
    assert len(arrived) == REINFORCE_PER_WAVE
    scene.hud.clear_notifications()
    for g in arrived:
        g.lifetime = 0.0
        g.state = GuardState.PATROL  # (hors poursuite)
    scene.update(1 / 60)
    assert not any(g.is_reinforcement for g in scene.guards)
    assert toasts(scene) == ["Les renforts se retirent"]
    scene.update(1 / 60)
    assert toasts(scene) == ["Les renforts se retirent"]  # annoncé une seule fois


# --- Scène : éclairage -------------------------------------------------------
from game.settings import ALARM_FADE_TIME, GUARD_FOV, LIGHTING_KEY  # noqa: E402


def specs_by_radius(scene):
    return {round(s.radius): s for s in scene._light_specs()}


def test_f4_toggles_the_lighting_and_the_choice_is_remembered(scene):
    assert scene.lighting.enabled and scene.game.prefs.lighting
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=LIGHTING_KEY))
    assert not scene.lighting.enabled and not scene.game.prefs.lighting
    scene.caught = True
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r))
    assert not scene.lighting.enabled  # la nouvelle partie garde le réglage
    scene.game.step(1 / 60)  # et le rendu sans éclairage fonctionne
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=LIGHTING_KEY))
    assert scene.lighting.enabled and scene.game.prefs.lighting


def test_scene_lights_the_player_guards_and_objects(scene):
    specs = scene._light_specs()
    player_light = specs[0]
    assert player_light.shadowed and player_light.pos == scene.player.pos
    torches = [s for s in specs if s.facing is not None]
    assert len(torches) == len(scene.guards) and all(s.fov == GUARD_FOV for s in torches)
    # Un halo par garde, plus terminal, sortie, portes fermées, objets au sol, boutons et lignes de champs actifs.
    active_runs = sum(len(f.runs) for f in scene.tilemap.fields.values() if f.active)
    expected = 1 + 2 * len(scene.guards) + len(scene.terminals) + 1 + len(scene.doors) + len(scene.pickups)
    expected += len(scene.field_buttons) + active_runs
    expected += len(scene.tilemap.decor_lights(scene.camera, scene.time))  # lanternes visibles
    assert len(specs) == expected


def test_guard_torch_follows_the_guard_and_turns_red_when_chasing(scene):
    guard = scene.guards[0]
    scene.guards[:] = [guard]
    calm = [s for s in scene._light_specs() if s.facing is not None][0]
    assert calm.facing == guard.angle and calm.pos == guard.pos
    guard._start_chase(scene.player)
    chase = [s for s in scene._light_specs() if s.facing is not None][0]
    assert chase.color[0] > chase.color[2] + 100 and calm.color[2] > chase.color[2]


def test_opened_doors_and_picked_up_items_stop_glowing(scene):
    scene.guards.clear()
    before = len(scene._light_specs())
    scene.pickups.pop()
    scene.doors[0].is_open, scene.doors[0].progress = True, 1.0  # ouverte, animation terminée
    assert len(scene._light_specs()) == before - 2


def test_exit_glows_brighter_once_the_data_is_in_the_bag(scene):
    scene.guards.clear()
    exit_pos = scene.exit_pad.pos
    idle = next(s for s in scene._light_specs() if s.pos == exit_pos)
    scene.inventory.add(Item(ItemKind.DATA))
    ready = next(s for s in scene._light_specs() if s.pos == exit_pos)
    assert ready.intensity > 2 * idle.intensity and ready.color[1] > idle.color[1]


def test_thrown_decoy_flashes_with_each_beep(scene):
    from game.entities.decoy import Decoy

    scene.guards.clear()
    decoy = Decoy(300, 300)
    scene.decoys.append(decoy)
    decoy.made_beep = True
    flash = next(s for s in scene._light_specs() if s.pos == decoy.pos).intensity
    decoy.made_beep = False
    rest = next(s for s in scene._light_specs() if s.pos == decoy.pos).intensity
    assert flash > rest


def test_alert_shifts_the_lighting_to_alarm_mode(scene):
    calm = scene.lighting.ambient()
    start_alert(scene)
    for _ in range(round((ALARM_FADE_TIME + 0.5) * 60)):
        scene.update(1 / 60)
        if scene.over:
            break
    r, g, b = scene.lighting.ambient()
    assert r > g and r > b  # dominante rouge (l'ambiance calme est bleutée)
    assert calm[2] > calm[0]


def test_opening_a_door_refreshes_the_shadows(scene):
    scene.guards.clear()
    scene.inventory.add(Item(ItemKind.KEYCARD, 1))
    teleport(scene, (24, 10))
    scene.game.step(1 / 60)  # remplit les caches d'ombres
    revision = scene.tilemap.revision
    press_e(scene)
    assert scene.tilemap.revision == revision + 1
    scene.game.step(1 / 60)  # redessine avec la nouvelle géométrie
    assert scene.lighting._revision == scene.tilemap.revision


def test_rendering_along_the_whole_hub_with_lighting(scene):
    scene.guards.clear()
    for i in range(60 * 4):
        teleport(scene, (4 + (i // 4) % 56, 10))
        scene.update(1 / 60)
        scene.game.step(1 / 60)


# --- Scène : son pendant l'alerte ---------------------------------------------
def test_the_klaxon_loops_during_the_lockdown_with_the_normal_music(scene):
    start_alert(scene)
    for _ in range(60 * 3):
        scene.update(1 / 60)
        if scene.over:
            break
    assert scene.game.audio.is_looping("alert")
    scene.game.audio.update(5.0)
    calm, tense = scene.game.audio.layer_volumes()
    assert calm > 0 and tense == 0  # musique normale seulement, pas de couche tendue


def test_the_klaxon_stops_when_the_game_ends_or_restarts(scene):
    start_alert(scene)
    scene.update(1 / 60)
    assert scene.game.audio.is_looping("alert")
    scene.won = True  # fin de partie
    scene.update(1 / 60)
    assert not scene.game.audio.is_looping("alert")
    scene.won = False
    scene.update(1 / 60)
    assert scene.game.audio.is_looping("alert")  # l'alerte est toujours là : il repart
    scene.restart()
    scene.update(1 / 60)
    assert not scene.game.audio.is_looping("alert")


def test_the_klaxon_stops_when_the_scene_is_left(scene):
    start_alert(scene)
    scene.update(1 / 60)
    assert scene.game.audio.is_looping("alert")
    scene.game.scenes.pop()  # on_exit : le directeur se détache
    assert not scene.game.audio.is_looping("alert")


# --- Scène : décor, champ de force, portes animées ------------------------------
@pytest.fixture
def cruiser_scene(game, monkeypatch):
    s = play_scene.PlayScene(game, _MAPS / "cruiser.txt")
    game.scenes.push(s)
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState())
    s.guards.clear()
    return s


def test_force_fields_get_evenly_spaced_lights(cruiser_scene):
    fields = [p for p in cruiser_scene.tilemap.props if p.kind == "field"]
    positions = cruiser_scene._field_light_positions
    assert len(positions) == sum(round(p.w * 32 / FIELD_LIGHT_SPACING) for p in fields)
    for pos in positions:  # chaque lueur est bien au centre d'une tuile de champ
        assert cruiser_scene.tilemap.tile_at(*cruiser_scene.tilemap.world_to_tile(*pos)) == 7  # FIELD
    specs = [s for s in cruiser_scene._light_specs() if s.color == (60, 170, 230)]
    assert len(specs) == len(positions)


def test_a_map_without_force_fields_has_no_such_lights(game, monkeypatch):
    s = play_scene.PlayScene(game, SANDBOX)
    assert s._field_light_positions == []


def test_the_space_layer_is_only_drawn_on_maps_that_have_void(game, monkeypatch):
    drawn = []
    for path, expected in ((_MAPS / "cruiser.txt", True), (SANDBOX, False)):  # le banc d'essai n'a pas de vide
        name = path.name
        s = play_scene.PlayScene(game, path)
        monkeypatch.setattr(s.space, "draw", lambda *a, name=name, **k: drawn.append(name))
        s.draw(game.screen)
        assert (name in drawn) is expected


def test_the_player_is_stopped_by_the_force_field_in_the_scene(cruiser_scene, monkeypatch):
    field = next(p for p in cruiser_scene.tilemap.props if p.kind == "field" and p.x < 30)
    teleport(cruiser_scene, (field.x + 8, field.y - 1))
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState(move=pygame.Vector2(0, 1), run=True))
    for _ in range(90):
        cruiser_scene.update(1 / 60)
    assert cruiser_scene.player.pos.y < field.y * 32  # il reste sur le pont
    assert cruiser_scene.player.rect.bottom <= field.y * 32 + 1


def test_a_decoy_cannot_be_thrown_into_space(cruiser_scene, monkeypatch):
    field = next(p for p in cruiser_scene.tilemap.props if p.kind == "field" and p.x < 30)
    teleport(cruiser_scene, (field.x + 8, field.y - 3))
    cruiser_scene.inventory.add(DECOY_ITEM)
    aim_at(monkeypatch, cruiser_scene, cruiser_scene.player.pos + pygame.Vector2(0, 200))
    throw(cruiser_scene)
    assert cruiser_scene.decoys[0].pos.y < field.y * 32  # retombé sur le pont, pas dans le vide


def test_doors_animate_in_the_scene_after_being_opened(cruiser_scene):
    door = next(d for d in cruiser_scene.doors if d.level == 0)
    cruiser_scene.inventory.add(Item(ItemKind.KEYCARD, 3))
    teleport(cruiser_scene, (int(door.anchor.x // 32), int(door.anchor.y // 32) + (1 if door.horizontal else 0)))
    press_e(cruiser_scene)
    assert door.is_open and door.progress < 1.0
    for _ in range(40):
        cruiser_scene.update(1 / 60)
    assert door.progress == 1.0
    cruiser_scene.game.step(1 / 60)


def test_door_light_fades_while_it_opens(cruiser_scene):
    door = cruiser_scene.doors[0]
    full = next(s for s in cruiser_scene._light_specs() if s.pos == door.anchor).intensity
    door.is_open, door.progress = True, 0.5
    half = next(s for s in cruiser_scene._light_specs() if s.pos == door.anchor).intensity
    assert half == pytest.approx(full / 2)
    door.progress = 1.0
    assert not [s for s in cruiser_scene._light_specs() if s.pos == door.anchor]


def test_a_full_frame_in_both_bays_with_every_prop_on_screen(cruiser_scene):
    for tile in ((10, 39), (60, 39), (11, 28), (45, 34)):
        teleport(cruiser_scene, tile)
        for _ in range(3):
            cruiser_scene.game.step(1 / 60)
