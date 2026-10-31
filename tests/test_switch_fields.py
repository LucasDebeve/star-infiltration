import logging

import pygame
import pytest

from game.ai.pathfinding import find_path
from game.core.camera import Camera
from game.core.events import EventBus
from game.entities.field_button import FieldButton
from game.items import Inventory
from game.settings import BUTTON_COOLDOWN, BUTTON_REACH, COLORS, LINK_COLOR_COUNT, MAPS_DIR, TILE_SIZE
from game.systems.interaction import InteractionContext, InteractionSystem
from game.world import prop_art
from game.world.collision import move_and_collide
from game.world.level_check import check_level, explore
from game.world.raycast import line_of_sight
from game.world.switch_fields import box_overlaps_tiles, link_colors, parse_config, straight_runs
from game.world.tilemap import GATE, Tilemap
from tests.paths import SANDBOX

TS = TILE_SIZE

# L'exemple du cahier des charges : trois salles alignées A, B, C. Le champ a (AB) est fermé au départ,
# le champ b (BC) est ouvert, et le bouton 1 (salle A) est lié aux deux.
ABC = """\
##############
#.1.a...b....#
##############
---
field a closed
field b open
button 1 toggles a b
"""


def abc() -> Tilemap:
    return Tilemap.from_text(ABC)


def center(tx, ty):
    return pygame.Vector2((tx + 0.5) * TS, (ty + 0.5) * TS)


def box_at(tx, ty, size=22):
    """Boîte d'une entité de 22 px centrée sur la tuile (tx, ty), au format (x, y, largeur, hauteur)."""
    c = center(tx, ty)
    return (c.x - size / 2, c.y - size / 2, size, size)


# --- Lecture de la carte -----------------------------------------------------------
def test_the_spec_example_loads_with_its_initial_states():
    tm = abc()
    a, b = tm.fields["a"], tm.fields["b"]
    assert (a.active, b.active) == (True, False)  # a fermé (actif), b ouvert (inactif)
    assert a.tiles == [(4, 1)] and b.tiles == [(8, 1)]
    assert tm.buttons["1"].tile == (2, 1) and tm.buttons["1"].fields == ("a", "b")
    assert a.buttons == ["1"] and b.buttons == ["1"]
    assert tm.tile_at(4, 1) == GATE and tm.tile_at(2, 1) != GATE  # le sol est sous le bouton


def test_all_the_tiles_of_a_letter_form_a_single_field():
    tm = Tilemap.from_text("#######\n#.a.a.#\n#.a.a.#\n#######\n---\nfield a open\n")
    assert sorted(tm.fields) == ["a"] and len(tm.fields["a"].tiles) == 4
    assert sorted(tm.fields["a"].runs) == [(2, 1, 1, 2), (4, 1, 1, 2)]  # deux lignes, un seul champ


def test_comments_blank_lines_and_trailing_comments_are_ignored_in_the_config():
    tm = Tilemap.from_text("#####\n#a1.#\n#####\n---\n; un commentaire\n\nfield a open   ; inline\nbutton 1 toggles a\n\n")
    assert tm.fields["a"].active is False and tm.buttons["1"].fields == ("a",)


def test_existing_maps_without_a_config_section_are_unchanged():
    tm = Tilemap.from_file(SANDBOX)
    assert tm.tile_at(0, 0) != GATE
    plain = Tilemap.from_text("#####\n#...#\n#####")
    assert plain.fields == {} and plain.buttons == {} and plain.warnings == []


def test_directives_still_work_around_the_config_section():
    tm = Tilemap.from_text("#######\n#PG.a.#\n#######\n@patrol 2,1 -> 3,1\n---\nfield a open\n")
    assert tm.route_for(tm.spawns_of("guard")[0]) == [(2, 1), (3, 1)]
    assert "a" in tm.fields


def test_directive_errors_report_their_file_line():
    with pytest.raises(ValueError, match="Ligne 5 :.*pas de vaisseau"):
        Tilemap.from_text("; commentaire\n#####\n#...#\n#####\n@ship 1,1 -> N\n")


# --- Erreurs, en français, avec le numéro de ligne -----------------------------------
GRID = "; un commentaire\n; un autre\n#####\n#a1.#\n#####\n"  # la grille commence à la ligne 3, la rangée utile est la ligne 4


@pytest.mark.parametrize(
    "config, message",
    [
        ("", r"Ligne 4 : le champ 'a' est utilisé dans la carte mais n'est pas déclaré"),
        ("field a open\n", r"Ligne 4 : le bouton '1' est utilisé dans la carte mais n'est pas déclaré"),
        ("field a open\nfield b open\nbutton 1 toggles a\n", r"Ligne 8 : le champ 'b' est déclaré mais n'apparaît pas dans la carte"),
        ("field a open\nbutton 1 toggles a\nbutton 2 toggles a\n", r"Ligne 9 : le bouton '2' est déclaré mais n'apparaît pas dans la carte"),
        ("field a open\nbutton 1 toggles a z\n", r"Ligne 8 : le bouton '1' référence le champ 'z', qui n'existe pas"),
        ("field a ouvert\nbutton 1 toggles a\n", r"Ligne 7 : état inconnu 'ouvert' pour le champ 'a'"),
        ("field a open\nfonctionne 1\nbutton 1 toggles a\n", r"Ligne 8 : instruction inconnue 'fonctionne'"),
        ("field A open\nbutton 1 toggles a\n", r"Ligne 7 : 'A' n'est pas un nom de champ valide"),
        ("field ab open\nbutton 1 toggles a\n", r"Ligne 7 : 'ab' n'est pas un nom de champ valide"),
        ("field a open\nbutton x toggles a\n", r"Ligne 8 : 'x' n'est pas un nom de bouton valide"),
        ("field a open\nbutton 0 toggles a\n", r"Ligne 8 : '0' n'est pas un nom de bouton valide"),
        ("field a open\nfield a closed\nbutton 1 toggles a\n", r"Ligne 8 : le champ 'a' est déjà déclaré \(ligne 7\)"),
        ("field a open\nbutton 1 toggles a\nbutton 1 toggles a\n", r"Ligne 9 : le bouton '1' est déjà déclaré \(ligne 8\)"),
        ("field a open\nbutton 1 a\n", r"Ligne 8 : syntaxe attendue : 'button <chiffre> toggles"),
        ("field a open\nbutton 1 toggles\n", r"Ligne 8 : syntaxe attendue : 'button <chiffre> toggles"),
        ("field a\nbutton 1 toggles a\n", r"Ligne 7 : syntaxe attendue : 'field <lettre> closed\|open'"),
        ("field a open\nbutton 1 toggles a a\n", r"Ligne 8 : le bouton '1' liste plusieurs fois le même champ"),
    ],
)
def test_config_errors_are_explicit_and_give_the_file_line(config, message):
    with pytest.raises(ValueError, match=message):
        Tilemap.from_text(GRID + "---\n" + config)


def test_a_map_with_letters_but_no_config_section_explains_what_to_add():
    with pytest.raises(ValueError, match=r"Ligne 2 : le champ 'a' est utilisé.*après '---'"):
        Tilemap.from_text("#####\n#a..#\n#####\n")


def test_a_button_digit_placed_twice_is_rejected_at_the_second_one():
    with pytest.raises(ValueError, match=r"Ligne 3 : le bouton '1' est placé deux fois \(déjà ligne 2\)"):
        Tilemap.from_text("######\n#1a..#\n#1...#\n######\n---\nfield a open\nbutton 1 toggles a\n")


@pytest.mark.parametrize("rows", [["#####", "#aa.#", "#a..#", "#####"], ["#####", "#aa##", "#aa##", "#####"]])
def test_a_field_must_be_made_of_straight_one_tile_lines(rows):
    with pytest.raises(ValueError, match="Ligne 2 : le champ 'a' doit être formé de lignes droites"):
        Tilemap.from_text("\n".join(rows) + "\n---\nfield a open\n")


def test_file_line_numbers_are_used_for_the_older_errors_too():
    with pytest.raises(ValueError, match="Ligne 3 de la carte : 2 caractères"):
        Tilemap.from_text("; commentaire\n###\n##\n###")
    with pytest.raises(ValueError, match=r"Ligne 3 : caractère inconnu '\?' \(colonne 2\)"):
        Tilemap.from_text("; commentaire\n###\n#?#\n###")


def test_a_field_without_a_button_is_only_a_warning(caplog):
    with caplog.at_level(logging.WARNING):
        tm = Tilemap.from_text("#####\n#.a.#\n#####\n---\nfield a closed\n")
    assert tm.fields["a"].active  # il garde son état de départ
    assert tm.warnings == ["Ligne 5 : le champ 'a' n'est lié à aucun bouton, il gardera son état de départ"]
    assert "n'est lié à aucun bouton" in caplog.text


def test_parse_config_alone():
    config = parse_config([(1, "field a closed"), (2, "; rien"), (3, ""), (4, "button 2 toggles a")])
    assert config.fields == {"a": (True, 1)} and config.buttons == {"2": (("a",), 4)}


def test_straight_runs():
    assert straight_runs([(1, 1), (2, 1), (3, 1)]) == [(1, 1, 3, 1)]
    assert sorted(straight_runs([(1, 1), (1, 2), (5, 5)])) == [(1, 1, 1, 2), (5, 5, 1, 1)]
    assert straight_runs([(1, 1), (2, 1), (1, 2)]) is None
    assert straight_runs([]) == []


# --- Couleurs des liaisons ------------------------------------------------------------
def test_a_button_and_its_fields_share_one_colour_and_groups_differ():
    buttons, fields = link_colors({"1": ("a", "b"), "2": ("c",)})
    assert buttons["1"] == fields["a"] == fields["b"]
    assert buttons["2"] == fields["c"] and buttons["1"] != buttons["2"]


def test_buttons_sharing_a_field_end_up_in_the_same_group():
    buttons, fields = link_colors({"1": ("a",), "2": ("a", "b"), "3": ("z",)})
    assert buttons["1"] == buttons["2"] == fields["a"] == fields["b"]
    assert buttons["3"] != buttons["1"]


def test_colours_wrap_around_the_palette():
    links = {str(i): (chr(ord("a") + i),) for i in range(1, LINK_COLOR_COUNT + 2)}
    buttons, _ = link_colors(links)
    assert max(buttons.values()) < LINK_COLOR_COUNT
    assert buttons["1"] == buttons[str(LINK_COLOR_COUNT + 1)]


def test_the_palette_exists_in_colors_and_the_first_tint_is_cyan():
    for i in range(LINK_COLOR_COUNT):
        assert f"link_{i}" in COLORS
    r, g, b = COLORS["link_0"]
    assert b > r and g > r  # cyan par défaut
    assert len({COLORS[f"link_{i}"] for i in range(LINK_COLOR_COUNT)}) == LINK_COLOR_COUNT


def test_the_fields_of_a_loaded_map_carry_their_group_colour():
    tm = Tilemap.from_text("#########\n#a.1.2.b#\n#########\n---\nfield a open\nfield b open\nbutton 1 toggles a\nbutton 2 toggles b\n")
    assert tm.buttons["1"].color == tm.fields["a"].color != tm.fields["b"].color == tm.buttons["2"].color


# --- Solidité dynamique -----------------------------------------------------------------
def test_an_active_field_is_solid_and_an_inactive_one_is_not():
    tm = abc()
    assert tm.is_solid(4, 1) and not tm.is_solid(8, 1)
    assert not tm.is_solid(2, 1)  # le sol sous un bouton reste praticable


def test_fields_never_block_sight_in_either_state():
    tm = abc()
    assert not tm.is_opaque(4, 1) and not tm.is_opaque(8, 1)
    assert line_of_sight(tm, center(1, 1), center(12, 1))


def test_collisions_follow_the_state_without_touching_the_collision_module():
    tm = abc()
    blocked = move_and_collide(tm, 3.2 * TS, 1.2 * TS, 22, 22, 3 * TS, 0)
    assert blocked.hit_x and blocked.x + 22 <= 4 * TS + 1e-6  # a est actif : on s'y arrête
    through_b = move_and_collide(tm, 5.1 * TS, 1.2 * TS, 22, 22, 3 * TS, 0)
    assert not through_b.hit_x and through_b.x > 8 * TS  # b est inactif : on le traverse
    tm.toggle_field("a")
    assert not move_and_collide(tm, 3.2 * TS, 1.2 * TS, 22, 22, 1.5 * TS, 0).hit_x  # a ouvert : on passe


def test_the_collision_module_knows_nothing_about_fields():
    import game.world.collision as collision

    source = open(collision.__file__, encoding="utf-8").read()
    assert "field" not in source.lower() and "gate" not in source.lower()


def test_toggling_updates_pathfinding_and_regions():
    tm = abc()
    assert not tm.same_region((1, 1), (6, 1)) and find_path(tm, (1, 1), (6, 1)) == []
    tm.toggle_field("a")
    assert tm.same_region((1, 1), (6, 1)) and find_path(tm, (1, 1), (6, 1))
    assert find_path(tm, (1, 1), (11, 1))  # b est ouvert aussi
    tm.toggle_field("b")
    tm.update_fields([])
    assert find_path(tm, (1, 1), (11, 1)) == []  # b fermé : le quai est coupé


def test_an_active_field_stops_thrown_objects_but_not_sight():
    from game.world.raycast import cast_ray

    tm = abc()
    assert cast_ray(tm, center(1, 1), (1, 0), 400, solid=True) == pytest.approx(4 * TS - center(1, 1).x)  # un leurre s'arrête
    assert cast_ray(tm, center(1, 1), (1, 0), 400) == pytest.approx(13 * TS - center(1, 1).x)  # le regard va jusqu'au mur du fond


def test_regions_are_recomputed_when_a_waiting_field_finally_closes():
    tm = abc()
    assert tm.same_region((5, 1), (10, 1))  # remplit le cache de zones (b ouvert)
    tm.toggle_field("b")
    assert tm.same_region((5, 1), (10, 1))  # en attente : le passage est encore libre
    tm.update_fields([])  # la zone est libre : b se ferme
    assert not tm.same_region((5, 1), (10, 1))  # le cache de zones ne doit pas rester périmé


# --- Pas d'écrasement ---------------------------------------------------------------------
def test_turning_a_field_off_is_immediate():
    tm = abc()
    f = tm.toggle_field("a")
    assert f.active is False and f.target is False and not f.pending


def test_turning_a_free_field_on_is_effective_at_the_next_update():
    tm = abc()
    f = tm.toggle_field("b")  # ouvert -> fermé : voulu, pas encore effectif
    assert f.target and not f.active and f.pending
    assert tm.update_fields([box_at(2, 1)]) == [f]  # personne dans sa zone
    assert f.active and not f.pending and tm.is_solid(8, 1)


def test_an_occupied_field_waits_and_never_closes_on_someone():
    tm = abc()
    f = tm.toggle_field("b")
    for _ in range(5):
        assert tm.update_fields([box_at(8, 1)]) == []  # quelqu'un est dedans
        assert f.pending and not tm.is_solid(8, 1)  # il n'est jamais solide autour de lui
    assert tm.update_fields([box_at(9, 1)]) == [f]  # il sort : le champ se ferme enfin
    assert tm.is_solid(8, 1)


def test_toggling_while_pending_cancels_the_activation():
    tm = abc()
    f = tm.toggle_field("b")
    tm.update_fields([box_at(8, 1)])
    tm.toggle_field("b")  # nouvel appui : on ne veut plus fermer
    assert f.target is False and not f.pending
    assert tm.update_fields([]) == [] and not tm.is_solid(8, 1)


def test_toggle_with_known_occupants_applies_immediately_or_waits():
    tm = abc()
    assert tm.toggle_field("b", occupants=[box_at(2, 1)]).active
    tm2 = abc()
    assert tm2.toggle_field("b", occupants=[box_at(8, 1)]).pending


def test_pending_state_is_visible_in_the_model():
    tm = abc()
    assert not tm.fields["a"].pending and not tm.fields["b"].pending
    tm.toggle_field("b")
    assert tm.fields["b"].pending


def test_only_real_overlap_counts_not_touching():
    tile_left = 8 * TS
    assert box_overlaps_tiles((tile_left - 10, TS + 4, 22, 22), [(8, 1)], TS)  # empiète de 12 px
    assert not box_overlaps_tiles((tile_left - 22, TS + 4, 22, 22), [(8, 1)], TS)  # colle le bord sans entrer
    assert not box_overlaps_tiles((tile_left + TS, TS + 4, 22, 22), [(8, 1)], TS)  # de l'autre côté, bord à bord


def test_a_one_pixel_overlap_counts():
    assert box_overlaps_tiles((8 * TS - 21, TS + 4, 22, 22), [(8, 1)], TS)


def test_the_player_is_never_stuck_inside_a_field():
    """Scénario complet : le joueur reste planté dans la zone, le champ attend, il en sort, le champ se ferme."""
    tm = abc()
    f = tm.toggle_field("b")
    x = 8 * TS - 4  # à cheval sur la tuile du champ
    for _ in range(30):
        tm.update_fields([(x, TS + 5, 22, 22)])
        assert not tm.is_solid(8, 1)  # aucune image où il serait emmuré
    x = 9 * TS + 2
    tm.update_fields([(x, TS + 5, 22, 22)])
    assert f.active
    # Une fois fermé, il est du bon côté et ne peut plus entrer.
    assert move_and_collide(tm, 9.2 * TS, 1.2 * TS, 22, 22, -3 * TS, 0).hit_x


# --- Bouton ---------------------------------------------------------------------------------
class Spy:
    def __init__(self, bus, *names):
        self.log = []
        for name in names:
            bus.subscribe(name, lambda _n=name, **payload: self.log.append((_n, payload)))


def press_setup(text=ABC):
    tm = Tilemap.from_text(text)
    bus = EventBus()
    button = FieldButton(next(iter(tm.buttons.values())), TS)
    return tm, bus, button, InteractionContext(tm, Inventory(), bus)


def test_a_button_toggles_all_its_fields_and_pressing_again_inverts_back():
    tm, bus, button, ctx = press_setup()
    button.interact(ctx)
    tm.update_fields([])
    assert (tm.fields["a"].active, tm.fields["b"].active) == (False, True)  # AB s'ouvre, BC se ferme
    button.update(BUTTON_COOLDOWN + 0.01)
    button.interact(ctx)
    tm.update_fields([])
    assert (tm.fields["a"].active, tm.fields["b"].active) == (True, False)  # et inversement


def test_a_button_emits_one_press_and_one_toggle_per_field():
    tm, bus, button, ctx = press_setup()
    spy = Spy(bus, "button_pressed", "field_toggled")
    button.interact(ctx)
    assert spy.log == [
        ("button_pressed", {"button": "1"}),
        ("field_toggled", {"field": "a", "active": False}),  # a était fermé : nouvel état = ouvert
        ("field_toggled", {"field": "b", "active": True}),
    ]


def test_toggle_events_report_the_requested_state_even_when_the_field_must_wait():
    tm, bus, button, ctx = press_setup()
    spy = Spy(bus, "field_toggled")
    button.interact(ctx)
    assert tm.fields["b"].pending  # il faudra attendre la zone libre, mais l'événement donne l'état voulu
    assert ("field_toggled", {"field": "b", "active": True}) in spy.log


def test_the_cooldown_stops_a_burst_of_presses_from_flickering_the_fields():
    tm, bus, button, ctx = press_setup()
    spy = Spy(bus, "button_pressed", "field_toggled")
    for _ in range(10):  # dix appuis dans la même fraction de seconde
        button.interact(ctx)
        button.update(0.02)
    assert len(spy.log) == 3  # un seul appui pris en compte (1 pression + 2 champs)
    assert tm.fields["a"].target is False
    button.update(BUTTON_COOLDOWN)
    button.interact(ctx)
    assert tm.fields["a"].target is True  # le délai écoulé, un nouvel appui compte


def test_the_cooldown_is_about_four_tenths_of_a_second():
    assert BUTTON_COOLDOWN == pytest.approx(0.4)


def test_a_field_can_answer_to_several_buttons():
    text = "#########\n#1..a..2#\n#########\n---\nfield a closed\nbutton 1 toggles a\nbutton 2 toggles a\n"
    tm = Tilemap.from_text(text)
    b1, b2 = (FieldButton(spec, TS) for spec in (tm.buttons["1"], tm.buttons["2"]))
    ctx = InteractionContext(tm, Inventory(), EventBus())
    b1.interact(ctx)
    assert tm.fields["a"].target is False
    b2.interact(ctx)  # un autre bouton rétablit l'état précédent
    assert tm.fields["a"].target is True and tm.fields["a"].buttons == ["1", "2"]


def test_a_button_can_drive_several_fields_and_one_field_several_buttons_together():
    text = "############\n#1.a.b.c.2.#\n############\n---\nfield a closed\nfield b open\nfield c closed\nbutton 1 toggles a b\nbutton 2 toggles b c\n"
    tm = Tilemap.from_text(text)
    ctx = InteractionContext(tm, Inventory(), EventBus())
    FieldButton(tm.buttons["1"], TS).interact(ctx)
    assert [tm.fields[k].target for k in "abc"] == [False, True, True]
    FieldButton(tm.buttons["2"], TS).interact(ctx)
    assert [tm.fields[k].target for k in "abc"] == [False, False, False]  # b a été inversé deux fois


def test_reach_is_less_than_one_tile_and_the_prompt_says_actionner():
    tm, bus, button, ctx = press_setup()
    assert button.reach == BUTTON_REACH == TS
    system = InteractionSystem(bus)
    near, far = center(2, 1) + pygame.Vector2(TS - 2, 0), center(2, 1) + pygame.Vector2(TS + 6, 0)
    system.update(0.016, near, tm, ctx.inventory, [button], pressed=False, held=False)
    assert system.target is button and system.prompt.label == "Actionner" and system.prompt.enabled
    system.update(0.016, far, tm, ctx.inventory, [button], pressed=False, held=False)
    assert system.target is None


def test_the_interaction_system_presses_the_button_on_e():
    tm, bus, button, ctx = press_setup()
    system = InteractionSystem(bus)
    system.update(0.016, center(2, 1), tm, ctx.inventory, [button], pressed=True, held=False)
    assert tm.fields["a"].target is False


def test_holding_e_does_not_repeat():
    """L'interaction n'agit qu'à l'appui : maintenir la touche ne bascule rien de plus."""
    tm, bus, button, ctx = press_setup()
    system = InteractionSystem(bus)
    system.update(0.016, center(2, 1), tm, ctx.inventory, [button], pressed=True, held=True)
    for _ in range(100):
        button.update(0.016)
        system.update(0.016, center(2, 1), tm, ctx.inventory, [button], pressed=False, held=True)
    assert tm.fields["a"].target is False


def test_the_e_key_is_the_interact_key():
    from game.settings import KEYS

    assert pygame.K_e in KEYS["interact"]


def test_a_button_draws_released_and_pressed():
    tm, bus, button, ctx = press_setup()
    surface = pygame.Surface((300, 100))
    camera = Camera(300, 100, tm.pixel_width, tm.pixel_height)
    surface.fill((0, 0, 0))
    button.draw(surface, camera)
    released = pygame.image.tostring(surface, "RGB")
    button.interact(ctx)
    surface.fill((0, 0, 0))
    button.draw(surface, camera)
    assert pygame.image.tostring(surface, "RGB") != released  # enfoncé : visiblement différent


# --- Rendu ----------------------------------------------------------------------------------
def draw_tile_region(tm, time=0.0):
    surface = pygame.Surface((14 * TS, 3 * TS))
    surface.fill((0, 0, 0))
    tm.draw(surface, Camera(14 * TS, 3 * TS, tm.pixel_width, tm.pixel_height), time)
    return surface


def changed_pixels(surface, tile):
    """Nombre de pixels de la tuile qui diffèrent du sol nu."""
    floor = COLORS["floor_a" if (tile[0] + tile[1]) % 2 == 0 else "floor_b"]
    r = pygame.Rect(tile[0] * TS, tile[1] * TS, TS, TS)
    return sum(1 for x in range(r.x, r.right) for y in range(r.y, r.bottom) if surface.get_at((x, y))[:3] != floor)


def test_an_active_field_draws_a_band_and_an_inactive_one_only_its_emitters():
    tm = abc()
    surface = draw_tile_region(tm)
    active, inactive = changed_pixels(surface, (4, 1)), changed_pixels(surface, (8, 1))
    assert active > 400  # a est actif : une bande d'énergie sur toute la tuile
    assert inactive < active / 2  # b est inactif : il ne reste que le bout de ses émetteurs et un pointillé
    # Les émetteurs de b restent visibles, aux deux bouts (sur les murs qui encadrent le couloir).
    top = surface.get_at((8 * TS + TS // 2, TS))[:3]
    assert top != surface.get_at((8 * TS + TS // 2 + 20, TS))[:3]


def test_inactive_emitters_are_dim_and_active_ones_are_lit():
    tm = abc()
    lit = draw_tile_region(tm).get_at((4 * TS + TS // 2, TS))[:3]  # émetteur du haut du champ actif a
    tm.toggle_field("a")
    dim = draw_tile_region(tm).get_at((4 * TS + TS // 2, TS))[:3]
    assert sum(lit) > sum(dim)


def test_a_pending_field_blinks():
    tm = abc()
    tm.toggle_field("b")  # b doit se fermer : en attente
    assert tm.fields["b"].pending
    drawn = [changed_pixels(draw_tile_region(tm, t / 20), (8, 1)) for t in range(10)]
    assert max(drawn) > 2 * min(drawn)  # tantôt la bande entière, tantôt seulement les émetteurs
    assert len({pygame.image.tostring(draw_tile_region(tm, t / 20), "RGB") for t in range(10)}) >= 2


def test_the_active_band_is_animated_but_deterministic():
    tm = abc()
    assert pygame.image.tostring(draw_tile_region(tm, 0.0), "RGB") != pygame.image.tostring(draw_tile_region(tm, 0.3), "RGB")
    assert pygame.image.tostring(draw_tile_region(tm, 0.3), "RGB") == pygame.image.tostring(draw_tile_region(tm, 0.3), "RGB")


def test_vertical_and_single_tile_fields_orient_themselves_between_walls():
    tm = Tilemap.from_text("#####\n#.a.#\n#####\n---\nfield a open\n")  # couloir horizontal : murs en haut et en bas
    assert tm._run_is_vertical(2, 1, 1, 1) is True  # la ligne barre le couloir de haut en bas
    corridor = Tilemap.from_text("###\n#.#\n#a#\n#.#\n###\n---\nfield a open\n")
    assert corridor._run_is_vertical(1, 2, 1, 1) is False  # couloir vertical : la ligne barre de gauche à droite
    pit = Tilemap.from_text("#####\n#...#\n#.a.#\n#...#\n#####\n---\nfield a open\n")
    assert pit._run_is_vertical(2, 2, 1, 1) is False  # en terrain libre : horizontale par défaut
    assert Tilemap.from_text("####\n#aa#\n####\n---\nfield a open\n")._run_is_vertical(1, 1, 2, 1) is False  # deux tuiles : le sens de la ligne
    assert Tilemap.from_text("###\n#a#\n#a#\n###\n---\nfield a open\n")._run_is_vertical(1, 1, 1, 2) is True


@pytest.mark.parametrize("state", ["active", "inactive", "pending"])
@pytest.mark.parametrize("vertical", [False, True])
def test_every_gate_state_draws_in_both_orientations(state, vertical):
    surface = pygame.Surface((200, 200))
    rect = pygame.Rect(60, 60, TS, 3 * TS) if vertical else pygame.Rect(60, 60, 3 * TS, TS)
    for t in (0.0, 0.05, 0.123, 1.0):
        prop_art.draw_gate(surface, rect, vertical, COLORS["link_2"], state, t)


# --- Dans la scène ----------------------------------------------------------------------------
from game.core.game import Game  # noqa: E402
from game.core.input import InputState  # noqa: E402
from game.scenes import play_scene  # noqa: E402


@pytest.fixture
def game():
    g = Game()
    pygame.event.clear()
    yield g
    pygame.quit()


@pytest.fixture
def training(game, monkeypatch):
    s = play_scene.PlayScene(game, SANDBOX)
    game.scenes.push(s)
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState())
    s.guards.clear()
    return s


def teleport(scene, tile, dx=0.0):
    scene.player.pos.update((tile[0] + 0.5) * TS + dx, (tile[1] + 0.5) * TS)
    scene.camera.snap_to(scene.player.pos)


def press_e(scene):
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_e))
    scene.update(1 / 60)


def test_the_training_level_has_its_buttons_and_fields(training):
    assert [b.id for b in training.field_buttons] == ["1"]
    a, b = training.tilemap.fields["a"], training.tilemap.fields["b"]
    assert (a.active, b.active) == (True, False)
    assert training.tilemap.is_solid(46, 13) and not training.tilemap.is_solid(26, 27)


def test_pressing_e_next_to_the_button_inverts_both_fields(training):
    teleport(training, (44, 11))
    press_e(training)
    a, b = training.tilemap.fields["a"], training.tilemap.fields["b"]
    assert (a.active, b.active) == (False, True)  # le raccourci s'ouvre, le passage se ferme (zone libre)
    assert not training.tilemap.is_solid(46, 13) and training.tilemap.is_solid(26, 27)


def test_events_reach_the_event_bus_from_the_scene(training):
    spy = Spy(training.game.events, "button_pressed", "field_toggled")
    teleport(training, (44, 11))
    press_e(training)
    assert spy.log[0] == ("button_pressed", {"button": "1"})
    assert {(p["field"], p["active"]) for n, p in spy.log if n == "field_toggled"} == {("a", False), ("b", True)}


def test_the_hud_prompt_appears_only_near_the_button(training):
    teleport(training, (44, 11))
    training.update(1 / 60)
    assert training.interaction.prompt is not None and training.interaction.prompt.label == "Actionner"
    teleport(training, (44, 11), dx=TS + 8)
    training.update(1 / 60)
    assert training.interaction.target is not training.field_buttons[0]


def test_the_player_standing_in_a_field_zone_is_never_walled_in(training, monkeypatch):
    b_tiles = training.tilemap.fields["b"].tiles  # le passage b est ouvert : on se tient dedans
    teleport(training, b_tiles[0])
    inside = pygame.Vector2(training.player.pos)
    training.tilemap.toggle_field("b")  # b doit se fermer pendant qu'on est dedans
    for _ in range(30):
        training.update(1 / 60)
        assert training.tilemap.fields["b"].pending
        assert not training.tilemap.is_solid(*b_tiles[0])
    assert training.player.pos == inside
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState(move=pygame.Vector2(1, 0), run=True))
    for _ in range(60):  # il avance et sort de la zone
        training.update(1 / 60)
    assert training.tilemap.fields["b"].active  # le champ s'est refermé derrière lui
    assert not any(box_overlaps_tiles((*training.player.top_left, 22, 22), [t], TS) and training.tilemap.is_solid(*t) for t in b_tiles)


def test_a_guard_in_the_zone_is_not_crushed_either(training):
    from game.ai.guard import Guard

    guard = Guard([center(*training.tilemap.fields["b"].tiles[0])], 0.0)
    training.guards.append(guard)
    training.tilemap.toggle_field("b")
    for _ in range(10):
        training.update(1 / 60)
        assert training.tilemap.fields["b"].pending or not box_overlaps_tiles((*guard.top_left, guard.width, guard.height), training.tilemap.fields["b"].tiles, TS)


def test_active_and_pending_fields_light_their_surroundings_and_inactive_ones_do_not(training):
    def gate_specs():
        return [s for s in training._light_specs() if s.color == COLORS["link_0"] and s.radius == 92]

    assert len(gate_specs()) == 1  # seul a est actif
    training.tilemap.toggle_field("a")
    training.tilemap.toggle_field("b")
    assert len(gate_specs()) == 1  # a éteint, b en attente (clignote) : toujours une seule lueur
    training.update(1 / 60)
    assert len(gate_specs()) == 1  # b actif
    training.tilemap.toggle_field("b")
    assert len(gate_specs()) == 0


def test_button_lamp_dims_while_cooling_down(training):
    button = training.field_buttons[0]
    full = next(s for s in training._light_specs() if s.pos == button.pos).intensity
    button.cooldown = 0.3
    dim = next(s for s in training._light_specs() if s.pos == button.pos).intensity
    assert dim < full


def test_debug_mode_draws_the_links_and_states(training):
    training.debug = True
    teleport(training, (44, 11))
    for _ in range(3):
        training.game.step(1 / 60)
    training.tilemap.toggle_field("b")  # pending -> libellé « attente »
    training.game.step(1 / 60)


def test_debug_draws_an_orphan_field_label_too(game, monkeypatch):
    text = "#######\n#P..a.#\n#######\n---\nfield a closed\n"
    path = MAPS_DIR.parent.parent / "tests" / "_orphan.txt"
    try:
        path.write_text(text, encoding="utf-8")
        scene = play_scene.PlayScene(game, path)
        game.scenes.push(scene)
        scene.debug = True
        game.step(1 / 60)
    finally:
        path.unlink(missing_ok=True)


def test_restart_resets_fields_to_their_initial_state(training):
    teleport(training, (44, 11))
    press_e(training)
    assert not training.tilemap.fields["a"].active
    training.restart()
    assert training.tilemap.fields["a"].active and not training.tilemap.fields["b"].active
    assert training.tilemap.fields["a"].target is True


# --- L'exemple du cahier des charges, de bout en bout ----------------------------------------------
def test_the_a_b_c_scenario_from_the_spec():
    tm = abc()
    ctx = InteractionContext(tm, Inventory(), EventBus())
    button = FieldButton(tm.buttons["1"], TS)
    # Départ : on ne passe pas de A à B (AB fermé), mais B -> C est ouvert.
    assert find_path(tm, (3, 1), (5, 1)) == [] and find_path(tm, (5, 1), (9, 1))
    # On actionne le bouton de A : AB s'ouvre, BC se ferme.
    button.interact(ctx)
    tm.update_fields([])
    assert find_path(tm, (3, 1), (5, 1)) and find_path(tm, (5, 1), (9, 1)) == []
    # On le réactionne : l'inverse.
    button.update(BUTTON_COOLDOWN + 0.01)
    button.interact(ctx)
    tm.update_fields([])
    assert find_path(tm, (3, 1), (5, 1)) == [] and find_path(tm, (5, 1), (9, 1))


# --- Vérification de niveau -------------------------------------------------------------------------
def test_a_button_can_be_required_to_finish_a_level():
    text = "###########\n#P1.a.T.E.#\n###########\n---\nfield a closed\nbutton 1 toggles a\n"
    assert check_level(Tilemap.from_text(text)) == []


def test_a_level_whose_button_is_out_of_reach_is_reported():
    text = "###########\n#P.a.T.E.1#\n###########\n---\nfield a closed\nbutton 1 toggles a\n"
    problems = check_level(Tilemap.from_text(text))
    assert any("terminal inaccessible" in p for p in problems)


def test_a_button_can_be_needed_twice_in_the_right_order():
    """Le bouton 1 ouvre a (vers B) mais ferme b : il faut le bouton 2, dans B, pour rouvrir b vers le quai."""
    text = "################\n#P1.a.2.b.T.E..#\n################\n---\nfield a closed\nfield b open\nbutton 1 toggles a b\nbutton 2 toggles b\n"
    tm = Tilemap.from_text(text)
    assert check_level(tm) == []
    assert explore(tm).can_finish and explore(tm).states >= 4


def test_route_distances_ignore_closed_fields_as_a_lower_bound():
    from game.world.level_check import route_distances

    tm = Tilemap.from_file(MAPS_DIR / "cruiser.txt")
    assert tm.fields["c"].active  # la copie est modifiée, pas la carte reçue
    route_distances(tm)
    assert tm.fields["c"].active and tm.is_solid(*tm.fields["c"].tiles[0])


def test_every_shipped_map_uses_the_new_system_and_stays_solvable():
    from tests.paths import CAMPAIGN

    for mission in CAMPAIGN.missions:
        tm = Tilemap.from_file(mission.map_path)
        assert bool(tm.fields) == bool(tm.buttons) and tm.warnings == []  # pas de champ sans bouton, ni de bouton sans champ
        assert check_level(tm) == []
        assert explore(tm).can_finish
    cruiser = Tilemap.from_file(MAPS_DIR / "cruiser.txt")
    assert {f.id: f.start_active for f in cruiser.fields.values()} == {"a": True, "b": False, "c": True}
    assert cruiser.buttons["1"].fields == ("a", "b")  # l'exemple A-B-C du cahier des charges
    assert cruiser.fields["b"].buttons == ["1", "2"]  # un champ répond à deux boutons


def test_the_cruiser_terminal_is_locked_in_an_alcove_until_button_3():
    tm = Tilemap.from_file(MAPS_DIR / "cruiser.txt")
    terminal = tm.spawns_of("terminal")[0]
    button = tm.buttons["3"]
    start = tm.spawns_of("player")[0]
    assert tm.fields["c"].active and not tm.same_region(button.tile, (terminal.tx, terminal.ty))
    tm.toggle_field("c")
    assert tm.same_region(button.tile, (terminal.tx, terminal.ty))
    assert start is not None
