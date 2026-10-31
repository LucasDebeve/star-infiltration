"""Ambiances sonores localisées : mixage par genre, lissage, murs, courant, et sons ponctuels des boutons et champs."""
import wave

import pygame
import pytest

from game.core.audio import Audio
from game.core.events import EventBus
from game.core.input import InputState
from game.core.preferences import Preferences
from game.scenes import play_scene
from game.settings import (
    AMBIENT_FADE_RATE,
    AMBIENT_FLOOR,
    AMBIENT_REFRESH,
    AMBIENT_SOURCES,
    AMBIENT_WALL_DAMPING,
    SOUNDS_DIR,
)
from game.systems.ambience import Ambience, AmbientSource, mix
from game.systems.sound_director import SoundDirector
from game.world.tilemap import Tilemap
from tests.paths import BLACKOUT, CAMPAIGN, CRUISER, SANDBOX, TRAINING

OPEN = Tilemap.from_text("#" * 30 + "\n#" + "." * 28 + "#\n" + "#" * 30)
WALLED = Tilemap.from_text("#" * 30 + "\n#" + "." * 13 + "#" + "." * 14 + "#\n" + "#" * 30)


def at(x, y=48):
    return pygame.Vector2(x, y)


class FakeAmbientAudio:
    def __init__(self):
        self.levels, self.stopped = {}, 0

    def set_ambient(self, name, level, pan=0.0):
        self.levels[name] = (level, pan)

    def stop_ambient(self, name=None):
        self.levels.clear()
        self.stopped += 1


# --- Mixage pur -------------------------------------------------------------------------------
def test_every_ambient_kind_names_an_existing_looping_sound():
    for kind, (sound, reach, volume) in AMBIENT_SOURCES.items():
        assert (SOUNDS_DIR / f"{sound}.wav").exists(), kind
        assert reach > 0 and 0 < volume <= 1


def test_a_source_is_loudest_up_close_and_silent_out_of_range():
    reach = AMBIENT_SOURCES["engine"][1]
    levels = [mix([AmbientSource("engine", at(100))], at(100 + d)).get("engine", (0, 0))[0] for d in (0, reach / 3, reach / 1.5, reach)]
    assert levels == sorted(levels, reverse=True) and levels[0] == pytest.approx(AMBIENT_SOURCES["engine"][2]) and levels[-1] == 0


def test_the_pan_leans_toward_the_source():
    right = mix([AmbientSource("lamp", at(200))], at(100))["lamp"][1]
    left = mix([AmbientSource("lamp", at(0))], at(100))["lamp"][1]
    assert right > 0 > left


def test_nearby_sources_of_a_kind_add_up_but_never_exceed_one():
    one = mix([AmbientSource("lamp", at(100))], at(250))["lamp"][0]
    two = mix([AmbientSource("lamp", at(100)), AmbientSource("lamp", at(100))], at(250))["lamp"][0]
    many = mix([AmbientSource("lamp", at(100)) for _ in range(40)], at(250))["lamp"][0]
    assert 0 < one < 0.2 and two == pytest.approx(2 * one) and many == 1.0


def test_two_sources_on_both_sides_balance_out():
    sources = [AmbientSource("lamp", at(100 - 80)), AmbientSource("lamp", at(100 + 80))]
    assert mix(sources, at(100))["lamp"][1] == pytest.approx(0.0)


def test_each_kind_is_mixed_apart():
    result = mix([AmbientSource("engine", at(100)), AmbientSource("terminal", at(100))], at(110))
    assert set(result) == {"engine", "terminal"}


def test_an_inactive_source_is_silent():
    state = {"on": True}
    source = AmbientSource("terminal", at(100), lambda: state["on"])
    assert "terminal" in mix([source], at(110))
    state["on"] = False
    assert mix([source], at(110)) == {}


def test_walls_muffle_a_source_by_a_fixed_factor():
    source = [AmbientSource("lamp", at(32 * 3 + 16, 48))]
    listener = at(32 * 8 + 16, 48)
    open_level = mix(source, listener, OPEN)["lamp"][0]
    walled_level = mix([AmbientSource("lamp", at(32 * 3 + 16, 48))], at(32 * 20 + 16, 48), WALLED)
    open_far = mix(source, at(32 * 20 + 16, 48), OPEN).get("lamp", (0, 0))[0]
    assert walled_level.get("lamp", (0, 0))[0] <= open_far * AMBIENT_WALL_DAMPING + 1e-9
    assert open_level > 0


def test_a_wall_makes_an_audible_difference():
    reach = AMBIENT_SOURCES["engine"][1]
    source = [AmbientSource("engine", at(32 * 12 + 16, 48))]
    listener = at(32 * 16 + 16, 48)  # de l'autre côté du mur de la colonne 14, à moins d'une portée
    assert listener.distance_to(source[0].pos) < reach
    assert mix(source, listener, WALLED)["engine"][0] == pytest.approx(mix(source, listener, OPEN)["engine"][0] * AMBIENT_WALL_DAMPING)


# --- Lissage et arrêt -----------------------------------------------------------------------------------
def test_the_level_fades_in_instead_of_jumping():
    audio = FakeAmbientAudio()
    amb = Ambience(audio, OPEN, [AmbientSource("engine", at(100))])
    amb.update(1 / 60, at(100))
    first = audio.levels["amb_engine"][0]
    assert 0 < first <= AMBIENT_FADE_RATE / 60 + 1e-9 < AMBIENT_SOURCES["engine"][2]
    for _ in range(120):
        amb.update(1 / 60, at(100))
    assert audio.levels["amb_engine"][0] == pytest.approx(AMBIENT_SOURCES["engine"][2])


def test_the_level_fades_out_when_leaving():
    audio = FakeAmbientAudio()
    amb = Ambience(audio, OPEN, [AmbientSource("engine", at(100))])
    for _ in range(120):
        amb.update(1 / 60, at(100))
    amb.update(1 / 60, at(100 + 5000))
    for _ in range(int(AMBIENT_REFRESH * 60) + 1):
        amb.update(1 / 60, at(100 + 5000))
    now = audio.levels["amb_engine"][0]
    assert 0 < now < AMBIENT_SOURCES["engine"][2]  # en train de s'éteindre, pas coupé net
    for _ in range(120):
        amb.update(1 / 60, at(100 + 5000))
    assert audio.levels["amb_engine"][0] == 0


def test_the_targets_are_recomputed_at_a_fixed_rhythm_not_every_frame():
    calls = []
    audio = FakeAmbientAudio()
    amb = Ambience(audio, OPEN, [AmbientSource("lamp", at(100), lambda: calls.append(1) or True)])
    for _ in range(60):
        amb.update(1 / 60, at(100))
    assert 8 <= len(calls) <= 12  # environ 10 par seconde, pas 60


def test_stopping_silences_everything():
    audio = FakeAmbientAudio()
    amb = Ambience(audio, OPEN, [AmbientSource("engine", at(100))])
    amb.update(0.5, at(100))
    amb.stop()
    assert audio.levels == {} and all(v == 0 for v in amb.levels.values())


# --- La couche audio -------------------------------------------------------------------------------------------
@pytest.fixture
def audio():
    return Audio(Preferences())


def test_set_ambient_starts_a_loop_adjusts_it_and_stops_it(audio):
    audio.set_ambient("amb_lamp", 0.5, -0.5)
    assert audio.is_ambient("amb_lamp")
    channel = audio._ambient["amb_lamp"][0]
    audio.set_ambient("amb_lamp", 0.25, 0.5)
    assert audio._ambient["amb_lamp"][0] is channel  # la même voix, pas une boucle de plus
    audio.set_ambient("amb_lamp", AMBIENT_FLOOR / 2)
    assert not audio.is_ambient("amb_lamp")


def test_an_ambient_loop_follows_the_effects_volume_and_the_pause(audio):
    audio.set_ambient("amb_engine", 1.0)
    audio.prefs.sfx, audio.prefs.master = 0.5, 1.0
    audio.apply_volumes()
    assert audio.ambient_volumes("amb_engine") == pytest.approx((0.5, 0.5))
    audio.set_ambient("amb_engine", 1.0, 0.5)  # source à droite : la voie gauche baisse
    left, right = audio.ambient_volumes("amb_engine")
    assert left == pytest.approx(0.25) and right == pytest.approx(0.5)
    audio.ducked = True
    audio.apply_volumes()
    assert audio.ambient_volumes("amb_engine") == (0.0, 0.0)  # pause : les ambiances se taisent aussi


def test_a_missing_ambient_file_is_ignored(audio, tmp_path):
    silent = Audio(Preferences(), sounds_dir=tmp_path)
    silent.set_ambient("amb_engine", 1.0)
    assert not silent.is_ambient("amb_engine")


def test_stop_ambient_without_a_name_stops_them_all(audio):
    audio.set_ambient("amb_lamp", 0.5)
    audio.set_ambient("amb_field", 0.5)
    audio.stop_ambient()
    assert not audio.is_ambient("amb_lamp") and not audio.is_ambient("amb_field")


def test_disabled_audio_ignores_ambiences(audio):
    audio.enabled = False
    audio.set_ambient("amb_lamp", 0.5)
    assert not audio.is_ambient("amb_lamp")


# --- Sons ponctuels : boutons, champs, coupure ----------------------------------------------------------------------
class RecordingAudio:
    def __init__(self):
        self.calls = []

    def play(self, name, volume=1.0, pan=0.0):
        self.calls.append(("play", name))

    def play_at(self, name, source, listener, volume=1.0):
        self.calls.append(("at", name, tuple(source)))

    def stop_loop(self, name):
        pass

    def set_tension(self, v):
        pass


@pytest.fixture
def rig():
    audio, bus = RecordingAudio(), EventBus()
    director = SoundDirector(audio, bus)
    director.attach()
    director.set_anchors({"1": (100, 100)}, {"a": (300, 100)})
    return audio, bus


def test_a_button_click_and_its_field_are_heard_from_where_they_are(rig):
    audio, bus = rig
    bus.emit("button_pressed", button="1")
    bus.emit("field_toggled", field="a", active=False)
    bus.emit("field_toggled", field="a", active=True)
    assert audio.calls == [("at", "button_press", (100, 100)), ("at", "field_off", (300, 100)), ("at", "field_on", (300, 100))]


def test_unknown_positions_still_make_a_sound(rig):
    audio, bus = rig
    bus.emit("button_pressed", button="9")
    assert audio.calls == [("play", "button_press")]


def test_cutting_the_power_has_its_own_sound(rig):
    audio, bus = rig
    bus.emit("power_cut", console=None)
    assert audio.calls == [("play", "power_down")]


# --- Dans la scène ---------------------------------------------------------------------------------------------------------
@pytest.fixture
def blackout(game, monkeypatch):
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState())
    scene = play_scene.PlayScene(game, BLACKOUT, CAMPAIGN.get("blackout"))
    game.scenes.push(scene)
    scene.guards.clear()
    return scene


def kinds(scene):
    return {s.kind for s in scene.ambience.sources}


def test_each_room_gets_its_hum_of_lamps_and_the_hangars_their_engines(game, monkeypatch):
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState())
    cruiser = play_scene.PlayScene(game, CRUISER)
    assert {"lamp", "engine", "field", "terminal"} <= kinds(cruiser)
    assert sum(s.kind == "engine" for s in cruiser.ambience.sources) == sum(p.kind == "ship" for p in cruiser.tilemap.props)
    assert "console" not in kinds(cruiser)


def test_the_training_level_has_no_engine_but_still_hums(game, monkeypatch):
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState())
    training = play_scene.PlayScene(game, TRAINING)
    assert "engine" not in kinds(training) and "lamp" in kinds(training)


def test_the_blackout_level_has_a_console_that_hums_until_the_power_is_cut(blackout):
    console = blackout.consoles[0]
    source = next(s for s in blackout.ambience.sources if s.kind == "console")
    assert source.active()
    console.cut = True
    assert not source.active()


def test_the_lamps_go_quiet_when_the_power_is_cut(blackout):
    lamp = next(s for s in blackout.ambience.sources if s.kind == "lamp")
    assert lamp.active()
    blackout.consoles[0].cut = True
    assert not lamp.active()


def test_a_hacked_terminal_stops_beeping(game, monkeypatch):
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState())
    scene = play_scene.PlayScene(game, SANDBOX)
    source = next(s for s in scene.ambience.sources if s.kind == "terminal")
    assert source.active()
    scene.terminals[0].hacked = True
    assert not source.active()


def test_a_switchable_field_only_hums_while_active(game, monkeypatch):
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState())
    scene = play_scene.PlayScene(game, BLACKOUT, CAMPAIGN.get("blackout"))
    field = scene.tilemap.fields["a"]
    center = scene._field_center(field)
    source = next(s for s in scene.ambience.sources if s.kind == "field" and s.pos == center)
    assert field.active and source.active()
    scene.tilemap.toggle_field("a")
    scene.tilemap.update_fields()
    assert not source.active()


def test_the_scene_plays_the_ambience_near_a_console_and_stops_it_on_exit(game, blackout):
    console = blackout.consoles[0]
    blackout.player.pos.update(console.pos.x - 40, console.pos.y)
    for _ in range(90):
        game.step(1 / 60)
    assert game.audio.is_ambient("amb_console") and game.audio.is_ambient("amb_lamp")
    game.scenes.clear()
    assert not game.audio.is_ambient("amb_console") and not game.audio.is_ambient("amb_lamp")


def test_a_restart_starts_the_ambience_over(game, blackout):
    for _ in range(60):
        game.step(1 / 60)
    old = blackout.ambience
    blackout.restart()
    assert blackout.ambience is not old and all(v == 0 for v in blackout.ambience.levels.values())


def test_pausing_silences_the_ambience(game, blackout):
    blackout.player.pos.update(blackout.consoles[0].pos.x - 40, blackout.consoles[0].pos.y)
    for _ in range(60):
        game.step(1 / 60)
    assert max(game.audio.ambient_volumes("amb_console")) > 0
    blackout.pause()
    game.step(1 / 60)
    assert game.audio.ambient_volumes("amb_console") == (0.0, 0.0)


# --- Les fichiers livrés -------------------------------------------------------------------------------------------------------
def samples(name):
    with wave.open(str(SOUNDS_DIR / f"{name}.wav")) as w:
        raw = w.readframes(w.getnframes())
        return [int.from_bytes(raw[i : i + 2], "little", signed=True) for i in range(0, len(raw), 2 * w.getnchannels())], w.getframerate()


@pytest.mark.parametrize("name", [sound for sound, _, _ in AMBIENT_SOURCES.values()])
def test_ambient_loops_are_long_and_seamless(name):
    data, rate = samples(name)
    assert len(data) / rate >= 1.5  # assez long pour qu'on n'entende pas la répétition trop vite
    typical = sorted(abs(b - a) for a, b in zip(data, data[1:]))[int(len(data) * 0.99)]
    seam = abs(data[0] - data[-1])
    assert seam <= max(typical * 3, 1500), "clic audible à la jonction de la boucle"
    assert max(abs(v) for v in data) > 2000  # pas un fichier muet
