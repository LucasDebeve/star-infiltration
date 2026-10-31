import pytest

from game.ui.menu import Button, Choice, Menu, Slider, Toggle, row_rects


class Box:
    """Une valeur modifiable, pour brancher les curseurs et bascules."""

    def __init__(self, value):
        self.value = value

    def set(self, value):
        self.value = value


def make_menu(sounds=None):
    clicked, box_v, box_t, box_c = [], Box(0.5), Box(False), Box("b")
    back = []
    items = [
        Button("Jouer", lambda: clicked.append("jouer")),
        Slider("Volume", lambda: box_v.value, box_v.set),
        Toggle("Éclairage", lambda: box_t.value, box_t.set),
        Choice("Difficulté", [("a", "A"), ("b", "B"), ("c", "C")], lambda: box_c.value, box_c.set),
        Button("Quitter", lambda: clicked.append("quitter")),
    ]
    menu = Menu(items, on_sound=(sounds.append if sounds is not None else None), on_back=lambda: back.append(1))
    return menu, clicked, box_v, box_t, box_c, back


def test_navigation_wraps_around():
    menu, *_ = make_menu()
    assert menu.index == 0
    menu.move(-1)
    assert menu.index == 4
    menu.move(1)
    assert menu.index == 0


def test_navigation_skips_disabled_items():
    menu, *_ = make_menu()
    menu.items[1].enabled = False
    menu.move(1)
    assert menu.index == 2
    menu.move(-1)
    assert menu.index == 0


def test_buttons_run_their_action_on_activate():
    menu, clicked, *_ = make_menu()
    menu.activate()
    menu.move(-1)
    menu.activate()
    assert clicked == ["jouer", "quitter"]


def test_slider_steps_and_clamps():
    menu, _, volume, *_ = make_menu()
    menu.select(1)
    menu.adjust(1)
    assert volume.value == pytest.approx(0.6)
    for _ in range(20):
        menu.adjust(1)
    assert volume.value == 1.0
    for _ in range(20):
        menu.adjust(-1)
    assert volume.value == 0.0


def test_slider_text_and_fraction():
    slider = Slider("v", lambda: 0.3, lambda v: None)
    assert slider.value_text() == "30 %" and slider.fraction() == pytest.approx(0.3)


def test_slider_has_no_accumulating_float_error():
    box = Box(0.0)
    slider = Slider("v", lambda: box.value, box.set)
    for _ in range(10):
        slider.adjust(1)
    assert box.value == 1.0


def test_toggle_flips_on_enter_and_follows_arrows():
    menu, _, _, toggle, *_ = make_menu()
    menu.select(2)
    menu.activate()
    assert toggle.value is True
    menu.adjust(-1)
    assert toggle.value is False
    assert menu.selected.value_text() == "Désactivé"
    menu.adjust(1)
    assert menu.selected.value_text() == "Activé"


def test_choice_cycles_both_ways_and_wraps():
    menu, *_, choice, _ = make_menu()
    menu.select(3)
    menu.adjust(1)
    assert choice.value == "c" and menu.selected.value_text() == "C"
    menu.adjust(1)
    assert choice.value == "a"
    menu.adjust(-1)
    assert choice.value == "c"
    menu.activate()
    assert choice.value == "a"


def test_choice_with_an_unknown_value_shows_the_first_option():
    choice = Choice("x", [("a", "A"), ("b", "B")], lambda: "zzz", lambda v: None)
    assert choice.value_text() == "A"


def test_back_calls_the_callback():
    menu, *_, back = make_menu()
    menu.back()
    assert back == [1]


def test_menu_without_back_ignores_it():
    Menu([Button("x", lambda: None)]).back()


def test_sounds_match_what_happens():
    sounds = []
    menu, *_ = make_menu(sounds)
    menu.move(1)
    menu.adjust(1)  # sur un curseur
    menu.activate()
    menu.back()
    assert sounds == ["ui_move", "ui_select", "ui_select", "ui_back"]


def test_no_sound_when_nothing_changes():
    sounds = []
    menu, *_ = make_menu(sounds)
    menu.adjust(1)  # un bouton ne se règle pas
    menu.select(0)  # déjà dessus
    menu.select(99)
    assert sounds == []


def test_selecting_nothing_is_ignored():
    sounds = []
    menu, *_ = make_menu(sounds)
    menu.select(None)  # le pointeur n'est sur aucune ligne
    assert menu.index == 0 and sounds == []


def test_mouse_selection_ignores_disabled_and_out_of_range():
    menu, *_ = make_menu()
    menu.items[2].enabled = False
    menu.select(2)
    menu.select(-1)
    assert menu.index == 0


def test_a_menu_needs_items():
    with pytest.raises(ValueError):
        Menu([])


def test_row_rects_are_centered_and_stacked():
    rects = row_rects((1280, 720), 3, 200)
    assert len(rects) == 3 and all(r.centerx == 640 for r in rects)
    assert rects[0].y == 200 and rects[1].y > rects[0].bottom
