"""Acoustique : occlusion filtrée (K3), réverbération par salle (K4), voix et radios des gardes (K5)."""
import math
import random
from array import array

import pygame
import pytest

from game.ai.guard import Guard, GuardState
from game.core import dsp
from game.core.audio import Audio
from game.core.events import EventBus
from game.core.preferences import Preferences
from game.settings import (
    MUFFLE_CUTOFFS,
    OCCLUSION_VOLUME,
    REVERB_AREAS,
    REVERB_TAPS,
    SOUNDS_DIR,
    VOICE_CATEGORY_COOLDOWN,
    VOICE_GAP,
    VOICE_LINES,
)
from game.systems.acoustics import Acoustics, muffle_level, reverb_level
from game.systems.sound_director import SoundDirector
from game.systems.voices import VoiceBank
from game.world.tilemap import Tilemap

V = pygame.Vector2
RATE = 44100


def tile_center(x, y):
    return V((x + 0.5) * 32, (y + 0.5) * 32)


def sine(freq, seconds=0.2, channels=1, amp=12000):
    frames = int(seconds * RATE)
    samples = array("h")
    for i in range(frames):
        v = int(amp * math.sin(2 * math.pi * freq * i / RATE))
        samples.extend([v] * channels)
    return samples.tobytes()


def peak(raw):
    samples = array("h")
    samples.frombytes(raw)
    return max(abs(v) for v in samples)


# --- Traitement du signal -----------------------------------------------------------------------------------------------------------
def test_lowpass_keeps_the_bass_and_removes_the_treble():
    low, high = sine(100), sine(6000)
    assert peak(dsp.lowpass(low, 1, RATE, 800)) > 0.8 * peak(low)
    assert peak(dsp.lowpass(high, 1, RATE, 800)) < 0.1 * peak(high)


def test_lowpass_keeps_the_length_and_filters_each_channel_alone():
    raw = sine(300, channels=2)
    out = dsp.lowpass(raw, 2, RATE, 900)
    assert len(out) == len(raw)
    left = array("h")
    left.frombytes(out)
    assert left[2::2] != array("h", [0] * len(left[2::2])) and list(left[0::2]) == list(left[1::2])


def test_a_lower_cutoff_is_duller():
    raw = sine(1500)
    assert peak(dsp.lowpass(raw, 1, RATE, 400)) < peak(dsp.lowpass(raw, 1, RATE, 1500)) < peak(raw)


def test_echo_adds_a_tail_and_never_clips():
    raw = sine(440, 0.1, amp=30000)
    out = dsp.echo(raw, 1, RATE, REVERB_TAPS[2])
    longest = max(delay for delay, _ in REVERB_TAPS[2])
    assert len(out) == len(raw) + round(longest * RATE) * 2  # 16 bits : deux octets par échantillon (voie unique)
    assert peak(out) <= 32767
    assert dsp.echo(raw, 1, RATE, ()) == raw


def test_echo_gives_the_same_tail_without_the_c_module(monkeypatch):
    raw = sine(440, 0.1, amp=8000)
    fast = dsp.echo(raw, 1, RATE, REVERB_TAPS[1])
    monkeypatch.setattr(dsp, "audioop", None)
    slow = dsp.echo(raw, 1, RATE, REVERB_TAPS[1])
    assert len(fast) == len(slow)
    a, b = array("h"), array("h")
    a.frombytes(fast)
    b.frombytes(slow)
    assert max(abs(x - y) for x, y in zip(a, b)) <= 8  # même résultat, à l'arrondi près


def test_a_bigger_room_has_a_longer_and_stronger_echo():
    assert len(REVERB_TAPS[0]) == 0 and len(REVERB_TAPS[1]) < len(REVERB_TAPS[2])
    assert max(d for d, _ in REVERB_TAPS[1]) < max(d for d, _ in REVERB_TAPS[2])


# --- Niveaux ------------------------------------------------------------------------------------------------------------------------------
def test_muffling_grows_with_the_walls_up_to_the_last_filter():
    assert [muffle_level(n) for n in (0, 1, 2, 3, 4, 9)] == [0, 1, 2, 3, 3, 3]
    cutoffs = [c for c in MUFFLE_CUTOFFS if c]
    assert cutoffs == sorted(cutoffs, reverse=True) and MUFFLE_CUTOFFS[0] is None


def test_reverb_depends_on_the_area_of_the_room():
    small, big = REVERB_AREAS
    assert reverb_level(small - 1) == 0 and reverb_level(small) == 1 and reverb_level(big - 1) == 1 and reverb_level(big) == 2


# --- Carte --------------------------------------------------------------------------------------------------------------------------------
SMALL_ROOM = "#####\n#P.E#\n#####"
# Deux pièces séparées par un mur épais de deux tuiles, et une porte fermée entre la seconde et le couloir.
WALLS = "\n".join(["############", "#P.##.....E#", "#..##......#", "############"])


def test_region_size_counts_the_open_tiles_of_the_room():
    tm = Tilemap.from_text(WALLS)
    assert tm.region_size(1, 1) == 4  # la pièce de gauche : 2 x 2
    assert tm.region_size(5, 1) == 12  # la pièce de droite : 6 x 2
    assert tm.region_size(0, 0) == 0  # un mur n'a pas de surface


def test_region_size_follows_doors_that_open():
    tm = Tilemap.from_text("#######\n#P.D..#\n#.#D#E#\n#######")
    before = tm.region_size(1, 1)
    tm.open_door([(3, 1), (3, 2)] if tm.tile_at(3, 2) == 3 else [(3, 1)])
    assert tm.region_size(1, 1) > before


def test_acoustics_counts_the_walls_between_source_and_listener():
    tm = Tilemap.from_text(WALLS)
    acoustics = Acoustics(tm)
    assert acoustics.walls(tile_center(1, 1), tile_center(2, 2)) == 0
    assert acoustics.walls(tile_center(1, 1), tile_center(6, 1)) == 2  # le mur de deux tuiles


def test_acoustics_only_reports_what_is_not_neutral():
    tm = Tilemap.from_text(WALLS)
    acoustics = Acoustics(tm)
    assert acoustics.effects(tile_center(1, 1), tile_center(2, 2)) == {}  # même petite pièce
    assert acoustics.effects(tile_center(1, 1), tile_center(6, 1)) == {"walls": 2}
    assert acoustics.own(tile_center(1, 1)) == {}


def big_hall(width=34, height=20):
    row = "#" + "." * (width - 2) + "#"
    return "\n".join(["#" * width, *[row] * (height - 2), "#" * width])


def test_a_hall_resonates_and_a_closet_does_not():
    hall = Acoustics(Tilemap.from_text(big_hall()))
    assert hall.reverb_at(tile_center(5, 5)) == 2
    closet = Acoustics(Tilemap.from_text(SMALL_ROOM))
    assert closet.reverb_at(tile_center(1, 1)) == 0
    assert hall.own(tile_center(5, 5)) == {"reverb": 2}


def test_a_closed_door_muffles_and_an_open_door_does_not():
    tm = Tilemap.from_text("#######\n#P.D.E#\n#######")
    acoustics = Acoustics(tm)
    assert acoustics.walls(tile_center(1, 1), tile_center(5, 1)) == 1
    tm.open_door([(3, 1)])
    assert acoustics.walls(tile_center(1, 1), tile_center(5, 1)) == 0


# --- Audio réel (pilote factice) -------------------------------------------------------------------------------------------------------
@pytest.fixture
def audio():
    audio = Audio(Preferences())
    if not audio.enabled:
        pytest.skip("pas de mixeur")
    return audio


def raw_of(sound):
    return sound.get_raw()


def energy(raw):
    samples = array("h")
    samples.frombytes(raw)
    return sum(v * v for v in samples) / max(1, len(samples))


def test_a_muffled_variant_is_a_different_duller_sound(audio):
    clean, muffled = audio._variant("door_open", 0, 0), audio._variant("door_open", 3, 0)
    assert clean is not muffled and energy(raw_of(muffled)) < energy(raw_of(clean))
    assert audio._variant("door_open", 3, 0) is muffled  # fabriqué une fois, puis gardé


def test_a_reverberant_variant_is_longer(audio):
    dry, wet = audio._variant("pickup", 0, 0), audio._variant("pickup", 0, 2)
    assert wet.get_length() > dry.get_length()


def test_a_missing_sound_is_still_tolerated(audio):
    assert audio._variant("n_existe_pas", 2, 1) is None
    assert audio.play("n_existe_pas", 1.0, 0.0, walls=2, reverb=1) is False


def test_long_sounds_are_never_filtered(audio):
    music = audio._sound("music_ambient")
    assert audio._variant("music_ambient", 3, 2) is music


def test_each_wall_makes_the_sound_quieter(audio, monkeypatch):
    levels = []

    class Channel:
        def set_volume(self, left, right=None):
            levels.append(left)

    sound = audio._sound("pickup")
    audio._sounds["pickup"] = type("S", (), {"play": lambda self: Channel(), "get_length": lambda self: 0.1, "get_raw": lambda self: b""})()
    audio._variants.clear()
    for walls in (0, 1, 2):
        audio._variants[("pickup", walls, 0)] = audio._sounds["pickup"]
        audio.play("pickup", 1.0, 0.0, walls=walls)
    assert levels[1] == pytest.approx(levels[0] * OCCLUSION_VOLUME) and levels[2] == pytest.approx(levels[0] * OCCLUSION_VOLUME**2)
    audio._sounds["pickup"] = sound


# --- Banc de voix -----------------------------------------------------------------------------------------------------------------------
def bank(**kwargs):
    return VoiceBank(rng=random.Random(4), **kwargs)


def test_every_voice_line_has_a_sound_file():
    for category, count in VOICE_LINES.items():
        for number in range(1, count + 1):
            assert (SOUNDS_DIR / f"voice_{category}_{number}.wav").exists(), (category, number)


def test_no_line_repeats_until_all_have_been_heard():
    voices = bank(gap=0.0, cooldown=0.0)
    names = [voices.pick("chase") for _ in range(VOICE_LINES["chase"] * 3)]
    for start in range(0, len(names), VOICE_LINES["chase"]):
        assert len(set(names[start:start + VOICE_LINES["chase"]])) == VOICE_LINES["chase"]
    assert all(a != b for a, b in zip(names, names[1:]))  # jamais deux fois de suite, même d'un sac à l'autre


def test_two_voices_never_overlap_and_a_category_does_not_nag():
    voices = bank()
    assert voices.pick("suspect") is not None
    assert voices.pick("lost") is None  # un autre garde vient de parler
    voices.tick(VOICE_GAP + 0.01)
    assert voices.pick("lost") is not None
    voices.tick(VOICE_GAP + 0.01)
    assert voices.pick("suspect") is None  # le même soupçon ne se répète pas aussitôt
    voices.tick(VOICE_CATEGORY_COOLDOWN)
    assert voices.pick("suspect") is not None


def test_an_urgent_line_skips_the_category_delay_but_not_the_gap():
    voices = bank()
    assert voices.pick("chase", urgent=True) is not None
    voices.tick(VOICE_GAP + 0.01)
    assert voices.pick("chase") is None and voices.pick("chase", urgent=True) is not None
    assert voices.pick("chase", urgent=True) is None  # pas deux à la fois


def test_an_unknown_category_is_silent():
    assert bank().pick("chant") is None


# --- Directeur sonore ----------------------------------------------------------------------------------------------------------------------
class FakeAudio:
    def __init__(self):
        self.calls = []

    def play(self, name, volume=1.0, pan=0.0, **extra):
        self.calls.append(("play", name, volume, extra))

    def play_at(self, name, source, listener, volume=1.0, **extra):
        self.calls.append(("at", name, volume, extra))

    def set_tension(self, value):
        pass

    def start_loop(self, name, volume=1.0):
        return True

    def stop_loop(self, name):
        pass


def rig(text=None):
    audio, bus = FakeAudio(), EventBus()
    director = SoundDirector(audio, bus, VoiceBank(rng=random.Random(1)))
    director.attach()
    if text is not None:
        director.set_acoustics(Acoustics(Tilemap.from_text(text)))
    return audio, bus, director


def watch(director, guard, dt=0.1):
    director.update(dt, [guard], V(0, 0), hacking=False, alert_active=False)


def make_guard(tx=1, ty=1):
    return Guard([tile_center(tx, ty), tile_center(tx + 1, ty)], 0.0)


def test_a_sound_behind_walls_reaches_the_audio_with_its_wall_count():
    audio, _, director = rig(WALLS)
    director.listener.update(tile_center(6, 1))
    director._at("door_open", tile_center(1, 1))
    assert audio.calls[0][3] == {"walls": 2}


def test_without_acoustics_everything_stays_sharp():
    audio, _, director = rig()
    director._at("door_open", tile_center(1, 1))
    director._own("pickup", 1.0)
    assert audio.calls[0][3] == {} and audio.calls[1][3] == {}


def test_the_players_footsteps_echo_in_a_hall():
    audio, bus, director = rig(big_hall())
    director.listener.update(tile_center(5, 5))
    bus.emit("footstep", stance="walk")
    assert audio.calls[0][3] == {"reverb": 2}


def test_a_guard_who_turns_suspicious_speaks_and_one_who_spots_you_shouts():
    audio, _, director = rig()
    guard = make_guard()
    watch(director, guard)
    guard.state = GuardState.INVESTIGATE
    watch(director, guard)
    assert any(n.startswith("voice_suspect_") for _, n, *_ in audio.calls) and "suspect" in [c[1] for c in audio.calls]
    director.voices.tick(VOICE_GAP + 0.1)
    guard.state = GuardState.CHASE
    watch(director, guard)
    assert any(c[1].startswith("voice_chase_") for c in audio.calls) and "spotted" in [c[1] for c in audio.calls]


def test_a_guard_who_loses_the_trail_mutters():
    audio, _, director = rig()
    guard = make_guard()
    guard.state = GuardState.CHASE
    watch(director, guard)
    director.voices.tick(10)
    audio.calls.clear()
    guard.state = GuardState.SEARCH
    watch(director, guard)
    assert [c[1] for c in audio.calls] == ["voice_lost_1"] or audio.calls[0][1].startswith("voice_lost_")


def test_a_voice_is_muffled_like_any_localized_sound():
    audio, _, director = rig(WALLS)
    guard = make_guard(1, 1)
    director.listener.update(tile_center(6, 1))
    guard.state = GuardState.CHASE
    director._guard_states = {id(guard): GuardState.PATROL}
    director._announce_guards([guard])
    voice = next(c for c in audio.calls if c[1].startswith("voice_chase_"))
    assert voice[3].get("walls") == 2


def test_the_radio_crackles_when_the_alert_is_raised_wherever_the_player_is():
    audio, bus, _ = rig(WALLS)
    bus.emit("alert_raised", pos=V(0, 0))
    radio = [c for c in audio.calls if c[1].startswith("voice_radio_")]
    assert len(radio) == 1 and radio[0][0] == "play" and radio[0][3] == {}


def test_reinforcements_and_cameras_also_use_the_radio():
    audio, bus, director = rig()
    bus.emit("camera_spotted", pos=V(0, 0))
    director.voices.tick(10)
    bus.emit("reinforcements_arrived", count=2)
    assert sum(c[1].startswith("voice_radio_") for c in audio.calls) == 2


def test_the_real_game_wires_the_acoustics(game, monkeypatch, tmp_path):
    from game.core.input import InputState
    from game.scenes import play_scene

    path = tmp_path / "m.txt"
    rows = big_hall().split("\n")
    rows[1] = "#P" + rows[1][2:-2] + "E#"
    path.write_text("\n".join(rows) + "\n")
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState())
    scene = play_scene.PlayScene(game, path)
    game.scenes.push(scene)
    assert isinstance(scene.director.acoustics, Acoustics)
    assert scene.director.acoustics.reverb_at(scene.player.pos) == 2
