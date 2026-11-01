"""Réglages par carte (E1) : @lockdown, @waves, @detect, @stay, @ambient."""

import pytest

from game.core.input import InputState
from game.difficulty import all_difficulties, get_difficulty
from game.scenes import play_scene
from game.settings import AMBIENT_LIGHT
from game.ui.lighting import Lighting
from game.world.map_settings import LIMITS, MapSettings, apply_setting
from game.world.tilemap import Tilemap
from tests.paths import CAMPAIGN

MAP = "#####\n#PEC#\n#####\n"
NORMAL = get_difficulty("normal")


# --- Lecture ---------------------------------------------------------------------------------------
def test_a_map_without_directives_has_empty_settings():
    tm = Tilemap.from_text(MAP)
    assert tm.settings.is_empty() and tm.ambient == tm.theme.ambient


def test_every_directive_is_read():
    tm = Tilemap.from_text(MAP + "@lockdown 120\n@waves 2\n@detect 1.2\n@stay 20\n@ambient 90,100,130\n")
    assert tm.settings == MapSettings(120.0, 2, 1.2, 20.0, (90, 100, 130))
    assert tm.ambient == (90, 100, 130)


def test_directives_may_come_in_any_order_and_amid_the_others():
    tm = Tilemap.from_text(MAP + "@waves 1\n@theme tatooine\n@lockdown 100\n")
    assert tm.settings.waves == 1 and tm.settings.lockdown == 100 and tm.theme.id == "tatooine"


def test_the_map_ambient_replaces_the_theme_one():
    plain, dark = Tilemap.from_text(MAP), Tilemap.from_text(MAP + "@ambient 20,30,40\n")
    assert plain.ambient == AMBIENT_LIGHT and dark.ambient == (20, 30, 40)
    assert Lighting(dark).ambient() == (20, 30, 40) and Lighting(dark).base_light() < Lighting(plain).base_light()


@pytest.mark.parametrize(
    "line,message",
    [
        ("@lockdown 10", "hors de 30..600"),
        ("@lockdown beaucoup", "attend un nombre"),
        ("@waves 2.5", "attend un nombre entier"),
        ("@waves 20", "hors de 0..8"),
        ("@detect 0", "hors de 0.3..3"),
        ("@stay 1", "hors de 5..120"),
        ("@ambient 1,2", "trois valeurs entre 0 et 255"),
        ("@ambient 1,2,300", "trois valeurs entre 0 et 255"),
        ("@ambient a,b,c", "trois entiers"),
        ("@lockdown 100\n@lockdown 90", "indiqué deux fois"),
    ],
)
def test_bad_settings_are_explained_with_their_line(line, message):
    with pytest.raises(ValueError, match=rf"Ligne \d : .*{message}"):
        Tilemap.from_text(MAP + line + "\n")


def test_every_setting_has_limits_that_contain_the_defaults():
    for name, (low, high) in LIMITS.items():
        assert low < high
    for d in all_difficulties():
        assert LIMITS["lockdown"][0] <= d.lockdown_time <= LIMITS["lockdown"][1] and LIMITS["waves"][0] <= d.waves <= LIMITS["waves"][1]


def test_apply_setting_never_mutates_the_original():
    base = MapSettings()
    changed = apply_setting(base, "waves", "3")
    assert base.waves is None and changed.waves == 3


# --- Combinaison avec la difficulté --------------------------------------------------------------------------------
def test_without_settings_the_difficulty_is_untouched():
    for d in all_difficulties():
        assert d.for_map(MapSettings()) is d and d.for_map(None) is d


def test_the_values_are_for_normal_and_the_other_difficulties_follow():
    settings = MapSettings(lockdown=120.0, waves=2, detect=1.2, stay=20.0)
    easy, normal, hard = (get_difficulty(k).for_map(settings) for k in ("easy", "normal", "hard"))
    assert normal.lockdown_time == 120.0 and normal.waves == 2 and normal.detect == pytest.approx(1.2) and normal.reinforcement_stay == 20.0
    assert easy.lockdown_time > normal.lockdown_time > hard.lockdown_time  # la proportion est conservée
    assert easy.lockdown_time / normal.lockdown_time == pytest.approx(get_difficulty("easy").lockdown_time / NORMAL.lockdown_time, abs=0.01)
    assert easy.waves < normal.waves < hard.waves and easy.detect < normal.detect < hard.detect


def test_a_setting_only_changes_what_it_names():
    d = get_difficulty("hard").for_map(MapSettings(lockdown=100.0))
    base = get_difficulty("hard")
    assert d.lockdown_time != base.lockdown_time and (d.detect, d.waves, d.reinforcement_stay) == (base.detect, base.waves, base.reinforcement_stay)


def test_the_number_of_waves_never_goes_negative():
    assert get_difficulty("easy").for_map(MapSettings(waves=0)).waves == 0


# --- Dans le jeu --------------------------------------------------------------------------------------------------------------------
def scene_for(game, monkeypatch, text, tmp_path):
    path = tmp_path / "carte.txt"
    path.write_text(text, encoding="utf-8")
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState())
    scene = play_scene.PlayScene(game, path)
    game.scenes.push(scene)
    return scene


def test_the_scene_uses_the_map_settings_for_the_alert(game, monkeypatch, tmp_path):
    scene = scene_for(game, monkeypatch, MAP + "@lockdown 100\n@waves 1\n@detect 2\n", tmp_path)
    assert scene.difficulty.lockdown_time == 100.0 and scene.difficulty.waves == 1 and scene.alert.time_left == 100.0
    assert scene.alert.difficulty is scene.difficulty


def test_the_chosen_difficulty_still_scales_the_map_settings(game, monkeypatch, tmp_path):
    game.prefs.difficulty = "hard"
    scene = scene_for(game, monkeypatch, MAP + "@lockdown 100\n", tmp_path)
    assert scene.difficulty.lockdown_time < 100.0 and scene.difficulty.key == "hard"


def test_guards_use_the_map_detection(game, monkeypatch, tmp_path):
    scene = scene_for(game, monkeypatch, "######\n#PGE.#\n######\n@detect 2\n", tmp_path)
    assert scene.guards and all(g.sensitivity == scene.difficulty.detect > 1.9 for g in scene.guards)


def test_a_restart_rereads_the_settings(game, monkeypatch, tmp_path):
    scene = scene_for(game, monkeypatch, MAP + "@lockdown 100\n", tmp_path)
    game.prefs.difficulty = "easy"
    scene.restart()
    assert scene.difficulty.lockdown_time > 100.0


# --- Cartes livrées --------------------------------------------------------------------------------------------------------------------------
def test_the_shipped_maps_use_their_own_balance():
    settings = {m.id: Tilemap.from_file(m.map_path).settings for m in CAMPAIGN.missions}
    assert settings["training"].lockdown == 240 and settings["outpost"].waves == 1
    assert settings["destroyer"].lockdown == 120 and settings["destroyer"].waves == 4 and settings["destroyer"].detect == 1.1
    assert settings["destroyer"].ambient is not None and settings["prison"].lockdown == 170


def test_the_lockdown_gets_tighter_where_the_level_gets_harder():
    lockdowns = [Tilemap.from_file(CAMPAIGN.get(i).map_path).settings.lockdown for i in ("outpost", "radar", "hangar", "destroyer")]
    assert lockdowns == sorted(lockdowns, reverse=True)


def test_the_destroyer_is_darker_than_a_plain_ship():
    destroyer = Tilemap.from_file(CAMPAIGN.get("destroyer").map_path)
    assert sum(destroyer.ambient) < sum(destroyer.theme.ambient)
