import json

import pytest

from game.core.preferences import Preferences, default_path
from game.difficulty import all_difficulties, get_difficulty
from game.settings import DEFAULT_DIFFICULTY, DEFAULT_VOLUMES, DIFFICULTIES


def test_defaults_when_no_file(tmp_path):
    prefs = Preferences.load(tmp_path / "absent.json")
    assert (prefs.master, prefs.music, prefs.sfx) == (DEFAULT_VOLUMES["master"], DEFAULT_VOLUMES["music"], DEFAULT_VOLUMES["sfx"])
    assert prefs.lighting and not prefs.fullscreen and prefs.difficulty == DEFAULT_DIFFICULTY


def test_round_trip(tmp_path):
    path = tmp_path / "prefs.json"
    prefs = Preferences.load(path)
    prefs.master, prefs.music, prefs.lighting, prefs.fullscreen, prefs.difficulty = 0.3, 0.0, False, True, "hard"
    assert prefs.save()
    again = Preferences.load(path)
    assert (again.master, again.music, again.lighting, again.fullscreen, again.difficulty) == (0.3, 0.0, False, True, "hard")


def test_the_file_only_holds_settings_not_the_path(tmp_path):
    path = tmp_path / "prefs.json"
    Preferences.load(path).save()
    assert set(json.loads(path.read_text())) == {"master", "music", "sfx", "lighting", "screen_shake", "fullscreen", "gamepad", "keys", "difficulty"}


@pytest.mark.parametrize("content", ["", "pas du json", "[1, 2]", "null", '{"master": '])
def test_corrupt_files_fall_back_to_defaults(tmp_path, content):
    path = tmp_path / "prefs.json"
    path.write_text(content)
    assert Preferences.load(path) == Preferences()


def test_bad_values_are_replaced_field_by_field(tmp_path):
    path = tmp_path / "prefs.json"
    path.write_text(json.dumps({"master": "fort", "music": 7, "sfx": -3, "lighting": "oui", "fullscreen": 1, "difficulty": "impossible"}))
    prefs = Preferences.load(path)
    assert prefs.master == DEFAULT_VOLUMES["master"]  # texte : valeur par défaut
    assert prefs.music == 1.0 and prefs.sfx == 0.0  # hors bornes : ramenées dans [0, 1]
    assert prefs.lighting is True and prefs.fullscreen is False  # pas des booléens : ignorés
    assert prefs.difficulty == DEFAULT_DIFFICULTY


def test_a_boolean_is_not_a_volume(tmp_path):
    path = tmp_path / "prefs.json"
    path.write_text(json.dumps({"master": True}))
    assert Preferences.load(path).master == DEFAULT_VOLUMES["master"]


def test_partial_files_keep_other_defaults(tmp_path):
    path = tmp_path / "prefs.json"
    path.write_text(json.dumps({"difficulty": "easy", "inconnu": 42}))
    prefs = Preferences.load(path)
    assert prefs.difficulty == "easy" and prefs.music == DEFAULT_VOLUMES["music"]


def test_save_creates_missing_folders(tmp_path):
    path = tmp_path / "a" / "b" / "prefs.json"
    assert Preferences.load(path).save() and path.exists()


def test_save_never_raises_when_the_disk_refuses(tmp_path):
    blocker = tmp_path / "fichier"
    blocker.write_text("je ne suis pas un dossier")
    assert Preferences.load(blocker / "prefs.json").save() is False


def test_save_is_atomic(tmp_path):
    path = tmp_path / "prefs.json"
    prefs = Preferences.load(path)
    prefs.save()
    assert not list(tmp_path.glob("*.tmp"))


def test_default_path_follows_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("STAR_INFILTRATION_HOME", str(tmp_path))
    assert default_path() == tmp_path / "preferences.json"
    monkeypatch.delenv("STAR_INFILTRATION_HOME")
    assert default_path().parent.name == ".star-infiltration"


# --- Difficulté --------------------------------------------------------------
def test_difficulties_get_harder():
    easy, normal, hard = (get_difficulty(k) for k in ("easy", "normal", "hard"))
    assert easy.detect < normal.detect < hard.detect
    assert easy.lockdown_time > normal.lockdown_time > hard.lockdown_time
    assert easy.waves < normal.waves < hard.waves
    assert easy.reinforcement_stay < normal.reinforcement_stay < hard.reinforcement_stay


def test_normal_matches_the_tuned_constants():
    from game.settings import LOCKDOWN_TIME, REINFORCE_STAY_TIME, REINFORCE_WAVES

    normal = get_difficulty("normal")
    assert (normal.detect, normal.lockdown_time, normal.waves, normal.reinforcement_stay) == (
        1.0, LOCKDOWN_TIME, REINFORCE_WAVES, REINFORCE_STAY_TIME,
    )


def test_unknown_difficulty_falls_back_to_the_default():
    assert get_difficulty("cauchemar").key == DEFAULT_DIFFICULTY


def test_all_difficulties_lists_every_preset_in_order():
    assert [d.key for d in all_difficulties()] == list(DIFFICULTIES)


def test_screen_shake_defaults_on_and_ignores_garbage(tmp_path):
    path = tmp_path / "prefs.json"
    assert Preferences.load(path).screen_shake is True
    path.write_text('{"screen_shake": false}')
    assert Preferences.load(path).screen_shake is False
    path.write_text('{"screen_shake": "non"}')
    assert Preferences.load(path).screen_shake is True
