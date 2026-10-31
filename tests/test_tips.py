"""Astuces contextuelles de l'entraînement, et disparition de l'aide permanente de l'écran de jeu."""
import pygame
import pytest

from game.core import bindings
from game.core.input import InputState
from game.scenes import play_scene
from game.tips import DEFAULT_RADIUS, MOVE_DONE, TIPS, TipTracker, TipZone, format_tip
from game.ui.hud import Hud
from game.world.tilemap import Tilemap
from tests.paths import BLACKOUT, CAMPAIGN, CRUISER, SANDBOX, TRAINING

V = pygame.Vector2
TS = 32


def at(tx, ty):
    return V((tx + 0.5) * TS, (ty + 0.5) * TS)


def tracker(*zones):
    return TipTracker([TipZone(*z) for z in zones], TS)


def run(t, pos, seconds=1.0, **kw):
    for _ in range(int(seconds * 60)):
        t.update(1 / 60, pos, **kw)


# --- Le catalogue -----------------------------------------------------------------------------------------
def test_every_tip_has_a_text_that_can_be_formatted():
    for tip in TIPS.values():
        assert tip.text and format_tip(tip.text)
        assert tip.done_on or tip.duration or tip.done_distance or tip.done_crouch or tip.id == "exit"  # une fin est prévue


def test_tips_name_the_keys_actually_in_use():
    assert "Z Q S D" in format_tip(TIPS["move"].text) and "Maj gauche" in format_tip(TIPS["move"].text)
    bindings.current.rebind("interact", 0, pygame.K_g)
    assert "appuyez sur G" in format_tip(TIPS["door"].text)
    assert "la souris" in format_tip(TIPS["decoy"].text) and "F" in format_tip(TIPS["decoy"].text)


def test_tips_speak_of_pad_buttons_when_playing_with_a_pad():
    bindings.device = bindings.PAD
    assert "appuyez sur A" in format_tip(TIPS["door"].text)
    assert "joystick" in format_tip(TIPS["move"].text) and "RT" in format_tip(TIPS["move"].text)
    assert "joystick droit" in format_tip(TIPS["decoy"].text) and "X" in format_tip(TIPS["decoy"].text)


# --- La zone ---------------------------------------------------------------------------------------------------
def test_a_tip_shows_only_near_its_zone():
    t = tracker(("door", (10, 5), 3))
    run(t, at(0, 5), 0.5)
    assert t.current is None
    run(t, at(8, 5), 0.5)
    tip, alpha = t.current
    assert tip.id == "door" and alpha == 1.0
    run(t, at(0, 5), 1.0)
    assert t.current is None  # il s'efface en quittant la zone


def test_tips_fade_in_and_out():
    t = tracker(("door", (10, 5), 3))
    t.update(1 / 60, at(10, 5))
    assert 0 < t.alpha < 0.2
    run(t, at(10, 5), 1.0)
    assert t.alpha == 1.0
    t.update(1 / 60, at(0, 0))
    assert 0.8 < t.alpha < 1.0 and t.current is not None  # le fondu de sortie dure un instant


def test_the_nearest_tip_wins_where_zones_overlap():
    t = tracker(("door", (10, 5), 6), ("pickup", (12, 5), 6))
    run(t, at(11.9, 5), 0.3)
    assert t.current[0].id == "pickup"
    run(t, at(9, 5), 0.3)
    assert t.current[0].id == "door"


def test_the_default_radius_is_used_when_none_is_given():
    assert TipZone("door", (1, 1)).radius == DEFAULT_RADIUS


def test_hidden_tips_stay_hidden():
    t = tracker(("door", (10, 5), 3))
    run(t, at(10, 5), 0.5, hidden=True)
    assert t.current is None


# --- Comprendre une astuce --------------------------------------------------------------------------------------------
def test_the_awaited_event_completes_the_displayed_tip():
    t = tracker(("door", (10, 5), 3))
    run(t, at(10, 5), 0.5)
    t.notify("item_picked")  # pas l'événement attendu
    assert t.current is not None and t.active is not None
    t.notify("door_opened")
    assert t.active is None
    run(t, at(10, 5), 1.0)
    assert t.current is None  # elle ne revient pas


def test_an_event_far_from_the_zone_does_not_use_up_the_tip():
    t = tracker(("door", (10, 5), 3))
    run(t, at(0, 0), 0.5)
    t.notify("door_opened")  # une autre porte, ailleurs
    run(t, at(10, 5), 0.5)
    assert t.current[0].id == "door"


def test_each_zone_is_understood_on_its_own():
    t = tracker(("pickup", (3, 3), 2), ("pickup", (20, 3), 2))
    run(t, at(3, 3), 0.3)
    t.notify("item_picked")
    run(t, at(20, 3), 0.3)
    assert t.current[0].id == "pickup" and t.active == 1  # la deuxième sert encore


def test_moving_far_enough_completes_the_move_tip():
    t = tracker(("move", (0, 0), 20))
    pos = at(0, 0)
    for _ in range(int(MOVE_DONE / 100 * 60) + 30):
        pos = pos + V(100 / 60, 0)
        t.update(1 / 60, pos)
    assert t.states[0].done
    run(t, pos, 1.0)
    assert t.current is None


def test_standing_still_does_not_complete_the_move_tip():
    t = tracker(("move", (0, 0), 20))
    run(t, at(0, 0), 5.0)
    assert not t.states[0].done and t.current is not None


def test_crouching_long_enough_completes_the_crouch_tip():
    t = tracker(("crouch", (0, 0), 20))
    run(t, at(0, 0), 3.0, stance_is_crouch=False)
    assert not t.states[0].done
    run(t, at(0, 0), 2.0, stance_is_crouch=True)
    assert t.states[0].done


def test_a_timed_tip_goes_away_by_itself():
    t = tracker(("guard", (0, 0), 20))
    run(t, at(0, 0), TIPS["guard"].duration - 1)
    assert not t.states[0].done
    run(t, at(0, 0), 2)
    assert t.states[0].done


def test_the_decoy_tip_needs_a_decoy():
    t = tracker(("decoy", (0, 0), 20))
    run(t, at(0, 0), 1.0, has_decoy=False)
    assert t.current is None
    run(t, at(0, 0), 0.5, has_decoy=True)
    assert t.current[0].id == "decoy"
    t.notify("decoy_thrown")
    assert t.active is None


def test_reset_brings_back_every_tip():
    t = tracker(("door", (10, 5), 3))
    run(t, at(10, 5), 0.3)
    t.notify("door_opened")
    t.reset()
    run(t, at(10, 5), 0.3)
    assert t.current[0].id == "door"


# --- Directive de carte ------------------------------------------------------------------------------------------------------
MAP = "#####\n#P.E#\n#####\n"


def test_the_tip_directive_places_a_zone():
    tm = Tilemap.from_text(MAP + "@tip 2,1 -> door 4\n@tip 1,1 -> move\n")
    assert tm.tip_zones == [TipZone("door", (2, 1), 4.0), TipZone("move", (1, 1), DEFAULT_RADIUS)]


@pytest.mark.parametrize(
    "line,message",
    [
        ("@tip 2,1 -> inconnue", "Astuce inconnue"),
        ("@tip 2,1", "Astuce illisible"),
        ("@tip deux,un -> door", "Astuce illisible"),
        ("@tip 2,1 -> door beaucoup", "Astuce illisible"),
        ("@tip 99,1 -> door", "hors de la carte"),
        ("@tip 2,1 -> door 0", "rayon nul"),
    ],
)
def test_bad_tip_directives_are_explained_with_their_line(line, message):
    with pytest.raises(ValueError, match=rf"Ligne 4 : .*{message}"):
        Tilemap.from_text(MAP + line + "\n")


def test_only_the_training_level_has_tips():
    assert Tilemap.from_file(TRAINING).tip_zones
    for path in (CRUISER, BLACKOUT, SANDBOX, CAMPAIGN.get("endor").map_path):
        assert Tilemap.from_file(path).tip_zones == []


def test_the_training_tips_follow_its_five_rooms():
    zones = Tilemap.from_file(TRAINING).tip_zones
    first = {z.tip: z for z in reversed(zones)}
    rooms = {name: (z.tile[0] - 1) // 10 + 1 for name, z in first.items()}
    assert rooms["move"] == rooms["crouch"] == rooms["pickup"] == 1 and rooms["door"] == 1
    assert rooms["badge_door"] == 2 and rooms["button"] == 3
    assert rooms["guard"] == rooms["decoy"] == 4 and rooms["hack"] == rooms["exit"] == 5
    for z in zones:
        assert not Tilemap.from_file(TRAINING).is_solid(*z.tile)


def test_every_training_tip_can_be_understood():
    """Chaque astuce a une fin : une action, une distance, un temps, ou la fin de la mission."""
    for zone in Tilemap.from_file(TRAINING).tip_zones:
        tip = TIPS[zone.tip]
        assert tip.done_on or tip.duration or tip.done_distance or tip.done_crouch or tip.id == "exit"


# --- Dans la scène ---------------------------------------------------------------------------------------------------------------------
@pytest.fixture
def training(game, monkeypatch):
    holder = {"input": InputState()}
    monkeypatch.setattr(play_scene, "read_input", lambda: holder["input"])
    mission = CAMPAIGN.get("training")
    scene = play_scene.PlayScene(game, mission.map_path, mission)
    game.scenes.push(scene)
    scene.holder = holder
    return scene


def test_the_first_tip_appears_at_the_start_of_the_training(training):
    for _ in range(30):
        training.update(1 / 60)
    assert training.tips.current[0].id == "move"


def test_the_scene_draws_the_tip_with_the_real_keys(training, game):
    for _ in range(40):
        training.update(1 / 60)
    surface = pygame.Surface((1280, 720))
    drawn = []
    original = training.hud.draw_tip
    training.hud.draw_tip = lambda s, text, alpha=1.0: drawn.append(text) or original(s, text, alpha)
    training.draw(surface)
    assert drawn and "Z Q S D" in drawn[0]


def test_an_action_completes_the_tip_through_the_event_bus(training, game):
    training.player.pos.update(at(8, 5))
    for _ in range(20):
        training.update(1 / 60)
    assert training.tips.current[0].id == "door"
    game.events.emit("door_opened", door=training.doors[0])
    assert training.tips.active is None


def test_the_tip_goes_away_when_the_mission_ends(training):
    for _ in range(40):
        training.update(1 / 60)
    assert training.tips.current is not None
    training.caught = True
    for _ in range(60):
        training.update(1 / 60)
    assert training.tips.current is None


def test_a_restart_brings_the_tips_back(training):
    training.tips.states[0].done = True
    training.restart()
    assert not training.tips.states[0].done


def test_the_other_missions_show_no_tip(game, monkeypatch):
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState())
    scene = play_scene.PlayScene(game, CRUISER)
    game.scenes.push(scene)
    for _ in range(60):
        scene.update(1 / 60)
    assert scene.tips.current is None


# --- Plus d'aide permanente à l'écran ---------------------------------------------------------------------------------------------
def test_the_game_screen_no_longer_shows_key_hints(game):
    from game.entities.player import Player

    hud = Hud()
    surface = pygame.Surface((1280, 720))
    surface.fill((0, 0, 0))
    hud.draw(surface, fps=60, player=Player(100, 100), tile=(3, 3), debug=False)
    bottom_left = surface.subsurface(pygame.Rect(0, 640, 900, 80))
    assert pygame.mask.from_threshold(bottom_left, (0, 0, 0), (1, 1, 1, 255)).count() == 900 * 80  # rien en bas à gauche


def test_the_decoy_slot_no_longer_carries_a_key_letter(game):
    from game.items import Inventory, Item, ItemKind

    hud = Hud()
    inventory = Inventory()
    inventory.add(Item(ItemKind.DECOY))
    surface = pygame.Surface((1280, 720))
    surface.fill((0, 0, 0))
    hud._draw_inventory(surface, inventory)
    bright = pygame.Surface((58, 16))
    bright.blit(surface, (0, 0), pygame.Rect(1280 - 12 - 58, 720 - 12 - 58 + 3, 58, 16))  # le coin haut-gauche de la case, où se tenait la lettre
    assert max(bright.get_at((x, y))[0] for x in range(58) for y in range(16)) < 200  # pas de pastille claire


def test_the_interaction_prompt_follows_the_binding_and_the_device(game):
    hud = Hud()
    surface = pygame.Surface((400, 300))
    from game.systems.interaction import Prompt

    keyboard = []
    for device in (bindings.KEYBOARD, bindings.PAD):
        bindings.device = device
        surface.fill((0, 0, 0))
        hud.draw_prompt(surface, (200, 200), Prompt("Ouvrir"))
        keyboard.append(pygame.image.tobytes(surface, "RGB"))
    assert keyboard[0] != keyboard[1]  # « E » puis « A »
    bindings.current.rebind("interact", 0, pygame.K_LCTRL)
    bindings.device = bindings.KEYBOARD
    surface.fill((0, 0, 0))
    hud.draw_prompt(surface, (200, 200), Prompt("Ouvrir"))  # une pastille plus large : « Ctrl gauche »


def test_end_screens_name_the_right_restart_key():
    import inspect

    from game.ui import hud as hud_module

    assert not hasattr(hud_module, "HELP_LINES")
    source = inspect.getsource(hud_module.Hud.draw_caught) + inspect.getsource(hud_module.Hud.draw_won)
    assert "bindings.label('restart')" in source


def test_a_tip_panel_is_drawn_with_its_fade(game):
    hud = Hud()
    surface = pygame.Surface((1280, 720))
    surface.fill((0, 0, 0))
    hud.draw_tip(surface, "Une ligne\nDeux lignes", 1.0)
    full = pygame.image.tobytes(surface, "RGB")
    surface.fill((0, 0, 0))
    hud.draw_tip(surface, "Une ligne\nDeux lignes", 0.3)
    faint = pygame.image.tobytes(surface, "RGB")
    surface.fill((0, 0, 0))
    hud.draw_tip(surface, "Une ligne", 0.0)
    assert full != faint and pygame.image.tobytes(surface, "RGB") == pygame.image.tobytes(pygame.Surface((1280, 720)), "RGB")
