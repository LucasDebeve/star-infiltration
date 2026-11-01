import pygame
import pytest

from game.ai.guard import Guard, GuardState
from game.core.audio import Audio, attenuation, channel_volumes, music_levels, stereo_pan
from game.core.events import EventBus
from game.core.preferences import Preferences
from game.settings import ALERT_LOOP_VOLUME, DUCK_VOLUME, HACK_TICK_INTERVAL, SOUND_RANGE, SOUNDS_DIR, TENSION_FADE_TIME
from game.systems.sound_director import SoundDirector

SOUND_NAMES = [
    "step_walk",
    "door_open",
    "door_denied",
    "pickup",
    "hack_tick",
    "hack_done",
    "decoy_throw",
    "decoy_beep",
    "suspect",
    "spotted",
    "alert",
    "reinforcements",
    "lockdown",
    "caught",
    "win",
    "ui_move",
    "ui_select",
    "ui_back",
    "music_ambient",
    "music_tension",
    "amb_engine",
    "amb_lamp",
    "amb_field",
    "amb_terminal",
    "amb_console",
    "button_press",
    "field_on",
    "field_off",
    "power_down",
    "steam_vent",
    "terminal_open",
    "camera_off",
    "lights_out",
    "tractor_off",
    "cell_open",
    "locker_open",
    "disguise",
    "voice_suspect_1",
    "voice_suspect_2",
    "voice_suspect_3",
    "voice_chase_1",
    "voice_chase_2",
    "voice_chase_3",
    "voice_lost_1",
    "voice_lost_2",
    "voice_radio_1",
    "voice_radio_2",
]


# --- Calculs de volume (purs) -------------------------------------------------
def test_attenuation_fades_with_distance_and_is_silent_beyond_range():
    assert attenuation(0) == 1.0
    assert attenuation(SOUND_RANGE / 2) == pytest.approx(0.25)
    assert attenuation(SOUND_RANGE) == 0.0 and attenuation(SOUND_RANGE * 3) == 0.0
    levels = [attenuation(d) for d in range(0, SOUND_RANGE, 40)]
    assert levels == sorted(levels, reverse=True)


def test_pan_follows_the_horizontal_offset_and_is_clamped():
    assert stereo_pan(0) == 0
    assert stereo_pan(SOUND_RANGE / 2) == pytest.approx(0.5) and stereo_pan(-SOUND_RANGE / 2) == pytest.approx(-0.5)
    assert stereo_pan(10 * SOUND_RANGE) == 1.0 and stereo_pan(-10 * SOUND_RANGE) == -1.0


def test_channel_volumes_attenuate_the_far_side_only():
    assert channel_volumes(0.8, 0.0) == (0.8, 0.8)
    left, right = channel_volumes(0.8, 0.5)  # source à droite : la gauche baisse
    assert left == pytest.approx(0.4) and right == 0.8
    left, right = channel_volumes(0.8, -1.0)
    assert left == 0.8 and right == 0.0


def test_music_crossfade_keeps_constant_power():
    assert music_levels(0.0) == (1.0, 0.0) and music_levels(1.0) == (0.0, 1.0)
    for t in (0.1, 0.5, 0.9):
        calm, tense = music_levels(t)
        assert calm**2 + tense**2 == pytest.approx(1.0)
    assert music_levels(-5) == music_levels(0) and music_levels(5) == music_levels(1)


# --- Fichiers de sons ---------------------------------------------------------
# On ne vérifie que ce dont le jeu a besoin (le fichier existe et le mixeur sait le charger) : les sons
# sont remplaçables, format et durée sont libres.
@pytest.mark.parametrize("name", SOUND_NAMES)
def test_every_sound_file_exists_and_loads(name):
    pygame.init()
    path = SOUNDS_DIR / f"{name}.wav"
    assert path.exists(), f"fichier manquant : {path.name}"
    assert pygame.mixer.Sound(str(path)).get_length() > 0


@pytest.mark.parametrize("name", ["music_ambient", "music_tension", "alert"])
def test_looped_sounds_are_long_enough_to_loop_without_stuttering(name):
    pygame.init()
    assert pygame.mixer.Sound(str(SOUNDS_DIR / f"{name}.wav")).get_length() >= 0.5


# --- Moteur audio -------------------------------------------------------------
@pytest.fixture
def audio():
    pygame.init()
    return Audio(Preferences())


def test_audio_starts_with_the_dummy_device(audio):
    assert audio.enabled


def test_play_known_and_unknown_sounds(audio):
    assert audio.play("pickup")
    assert not audio.play("ce_son_n_existe_pas")  # tolérance : pas d'exception
    assert not audio.play("ce_son_n_existe_pas")  # et l'échec est mémorisé


def test_zero_volume_plays_nothing(audio):
    audio.prefs.sfx = 0.0
    assert not audio.play("pickup")
    audio.prefs.sfx, audio.prefs.master = 1.0, 0.0
    assert not audio.play("pickup")


def test_positional_sound_needs_to_be_in_range(audio):
    assert audio.play_at("door_open", (100, 0), (0, 0))
    assert not audio.play_at("door_open", (SOUND_RANGE + 1, 0), (0, 0))


def test_disabled_audio_is_a_silent_noop(audio):
    audio.enabled = False
    assert not audio.play("pickup") and not audio.play_at("door_open", (0, 0), (0, 0))
    audio.start_music()
    assert audio.layer_volumes()[0] > 0  # le calcul reste valable, sans voie à régler
    audio.update(1.0)


def test_music_follows_the_tension_with_a_fade(audio):
    audio.start_music()
    calm, tense = audio.layer_volumes()
    assert calm > 0 and tense == 0
    audio.set_tension(1.0)
    audio.update(TENSION_FADE_TIME / 2)
    assert 0.3 < audio.tension < 0.7  # fondu progressif, pas de saut
    audio.update(TENSION_FADE_TIME)
    calm, tense = audio.layer_volumes()
    assert calm == 0 and tense > 0
    audio.set_tension(0.0)
    audio.update(TENSION_FADE_TIME * 2)
    assert audio.tension == 0


def test_music_volume_follows_preferences_and_pause_ducking(audio):
    audio.start_music()
    normal = audio.layer_volumes()[0]
    audio.set_ducked(True)
    assert audio.layer_volumes()[0] == pytest.approx(normal * DUCK_VOLUME)
    audio.set_ducked(False)
    audio.prefs.music = 0.0
    assert audio.layer_volumes() == (0.0, 0.0)
    audio.prefs.music, audio.prefs.master = 1.0, 0.5
    assert audio.layer_volumes()[0] == pytest.approx(0.5)


def test_start_music_is_idempotent_and_stoppable(audio):
    audio.start_music()
    channels = list(audio._music_channels)
    audio.start_music()
    assert audio._music_channels == channels
    audio.stop_music()
    assert audio._music_channels == []


# --- Directeur sonore ---------------------------------------------------------
class FakeAudio:
    def __init__(self):
        self.calls = []
        self.tension = None
        self.loops = {}  # nom -> volume relatif, pour les effets en boucle en cours

    def start_loop(self, name, volume=1.0):
        self.loops[name] = volume
        return True

    def stop_loop(self, name):
        self.loops.pop(name, None)

    def play(self, name, volume=1.0, pan=0.0):
        self.calls.append(("play", name, volume))

    def play_at(self, name, source, listener, volume=1.0):
        self.calls.append(("at", name, tuple(source)))

    def set_tension(self, value):
        self.tension = value

    def names(self):
        return [c[1] for c in self.calls]


@pytest.fixture
def rig():
    audio, bus = FakeAudio(), EventBus()
    director = SoundDirector(audio, bus)
    director.attach()
    return audio, bus, director


def test_events_become_sounds(rig):
    audio, bus, _ = rig
    for event, kwargs in (
        ("item_picked", {"item": None}),
        ("interaction_denied", {"message": "x"}),
        ("terminal_hacked", {"terminal": None}),
        ("mission_complete", {}),
        ("player_caught", {}),
        ("reinforcements_arrived", {"count": 1}),
        ("lockdown", {}),
        ("decoy_thrown", {"pos": (5, 5)}),
    ):
        bus.emit(event, **kwargs)
    assert [n for n in audio.names() if not n.startswith("voice_")] == ["pickup", "door_denied", "hack_done", "win", "caught", "reinforcements", "lockdown", "decoy_throw"]
    assert sum(n.startswith("voice_radio") for n in audio.names()) == 1  # l'arrivée des renforts passe aussi par la radio


def test_footsteps_are_louder_when_running(rig):
    audio, bus, _ = rig
    bus.emit("footstep", stance="walk")
    bus.emit("footstep", stance="run")
    walk, run = audio.calls
    assert walk[0] == run[0] == "play" and run[2] > walk[2]  # course plus bruyante que marche (fichier choisi librement)


def test_an_unknown_stance_falls_back_to_walking(rig):
    audio, bus, _ = rig
    bus.emit("footstep", stance="crawl")
    bus.emit("footstep", stance="walk")
    assert audio.calls[0] == audio.calls[1]


def test_door_and_decoy_sounds_are_positional(rig):
    audio, bus, _ = rig

    class Door:
        anchor = pygame.Vector2(10, 20)

    bus.emit("door_opened", door=Door())
    bus.emit("decoy_beep", pos=pygame.Vector2(30, 40))
    assert audio.calls == [("at", "door_open", (10, 20)), ("at", "decoy_beep", (30, 40))]


def test_detach_stops_the_sounds(rig):
    audio, bus, director = rig
    director.detach()
    bus.emit("player_caught")
    assert audio.calls == []


def guard():
    return Guard([pygame.Vector2(100, 100)], 0.0)


def test_guards_announce_suspicion_and_detection_once(rig):
    audio, _, director = rig
    g = guard()
    director.update(0.1, [g], (0, 0), hacking=False, alert_active=False)
    g.state = GuardState.INVESTIGATE
    director.update(0.1, [g], (0, 0), hacking=False, alert_active=False)
    director.update(0.1, [g], (0, 0), hacking=False, alert_active=False)  # pas de répétition
    director.voices.tick(2.0)  # le garde précédent a fini sa réplique
    g.state = GuardState.CHASE
    director.update(0.1, [g], (0, 0), hacking=False, alert_active=False)
    assert [n for n in audio.names() if not n.startswith("voice_")] == ["suspect", "spotted"]  # et chaque fois une réplique
    assert [n.split("_")[1] for n in audio.names() if n.startswith("voice_")] == ["suspect", "chase"]


def test_a_new_arrival_does_not_announce_itself(rig):
    audio, _, director = rig
    director.update(0.1, [], (0, 0), hacking=False, alert_active=False)
    arrival = guard()
    arrival.state = GuardState.INVESTIGATE
    director.update(0.1, [arrival], (0, 0), hacking=False, alert_active=False)
    assert audio.calls == []


def test_search_to_investigate_is_not_a_new_suspicion(rig):
    audio, _, director = rig
    g = guard()
    g.state = GuardState.SEARCH
    director.update(0.1, [g], (0, 0), hacking=False, alert_active=False)
    g.state = GuardState.INVESTIGATE
    director.update(0.1, [g], (0, 0), hacking=False, alert_active=False)
    assert audio.calls == []


def test_hacking_ticks_at_a_steady_rhythm(rig):
    audio, _, director = rig
    for _ in range(round(2 / 0.02)):
        director.update(0.02, [], (0, 0), hacking=True, alert_active=False)
    ticks = audio.names().count("hack_tick")
    assert ticks == pytest.approx(2 / HACK_TICK_INTERVAL, abs=1.5)
    audio.calls.clear()
    director.update(0.02, [], (0, 0), hacking=False, alert_active=False)
    assert audio.calls == []


def test_music_gets_tenser_when_a_guard_investigates_but_not_during_the_alert(rig):
    audio, _, director = rig
    director.update(0.1, [guard()], (0, 0), hacking=False, alert_active=False)
    assert audio.tension == 0.0
    g = guard()
    g.state = GuardState.INVESTIGATE
    director.update(0.1, [g], (0, 0), hacking=False, alert_active=False)
    assert 0 < audio.tension < 1
    g.state = GuardState.CHASE
    director.update(0.1, [g], (0, 0), hacking=False, alert_active=True)
    assert audio.tension == 0.0  # pendant l'alerte : la musique normale, sans couche tendue


def test_the_klaxon_loops_for_the_whole_alert_and_only_then(rig):
    audio, bus, director = rig
    director.update(0.1, [], (0, 0), hacking=False, alert_active=False)
    assert audio.loops == {}
    director.update(0.1, [], (0, 0), hacking=False, alert_active=True)
    assert audio.loops == {"alert": ALERT_LOOP_VOLUME}
    for _ in range(50):  # des centaines d'images plus tard : toujours une seule boucle, rien de rejoué
        director.update(0.1, [], (0, 0), hacking=False, alert_active=True)
    assert audio.loops == {"alert": ALERT_LOOP_VOLUME}
    bus.emit("alert_raised", pos=(0, 0))  # le déclenchement n'ajoute pas de second klaxon ponctuel
    assert audio.names().count("alert") == 0
    director.update(0.1, [], (0, 0), hacking=False, alert_active=False)  # fin de partie, redémarrage...
    assert audio.loops == {}


def test_detaching_silences_the_klaxon(rig):
    audio, _, director = rig
    director.update(0.1, [], (0, 0), hacking=False, alert_active=True)
    director.detach()
    assert audio.loops == {}


# --- Effets en boucle (moteur audio) --------------------------------------------
def test_a_loop_plays_once_and_stops(audio):
    assert audio.start_loop("alert", 0.5)
    channel = audio._loops["alert"][0]
    assert audio.is_looping("alert") and channel.get_busy()
    assert audio.start_loop("alert", 0.5)  # déjà en cours : la même voie, pas de doublon
    assert audio._loops["alert"][0] is channel and len(audio._loops) == 1
    audio.stop_loop("alert")
    assert not audio.is_looping("alert") and not channel.get_busy()
    audio.stop_loop("alert")  # sans danger si rien ne tourne


def test_a_loop_keeps_playing_beyond_the_length_of_the_sound(audio):
    audio.start_loop("alert")
    channel = audio._loops["alert"][0]
    import time

    time.sleep(0.05)
    assert channel.get_busy()
    assert channel.get_sound().get_length() < 3  # un son court, rejoué sans fin


def test_loop_volume_follows_preferences_and_is_muted_in_the_pause(audio):
    audio.prefs.master, audio.prefs.sfx = 1.0, 1.0
    audio.start_loop("alert", 0.5)
    channel = audio._loops["alert"][0]
    assert channel.get_volume() == pytest.approx(0.5, abs=0.02)
    audio.prefs.sfx = 0.4
    audio.apply_volumes()
    assert channel.get_volume() == pytest.approx(0.2, abs=0.02)
    audio.set_ducked(True)
    assert channel.get_volume() == 0.0
    audio.set_ducked(False)
    assert channel.get_volume() == pytest.approx(0.2, abs=0.02)


def test_unknown_or_disabled_loops_do_nothing(audio):
    assert not audio.start_loop("ce_son_n_existe_pas")
    assert not audio.is_looping("ce_son_n_existe_pas")
    audio.enabled = False
    assert not audio.start_loop("alert")


def test_stop_loops_stops_everything(audio):
    audio.start_loop("alert")
    audio.start_loop("hack_tick")
    audio.stop_loops()
    assert audio._loops == {}


# --- Thème (le générique) --------------------------------------------------------------------------------
THEME = "generique"


def test_the_theme_returns_its_length_and_plays_once(audio):
    if audio.sound_length(THEME) is None:
        pytest.skip("generique.wav absent")
    length = audio.play_theme(THEME)
    assert length == pytest.approx(audio.sound_length(THEME)) and length > 10
    assert audio.theme_playing
    audio.stop_theme()
    assert not audio.theme_playing


def test_playing_a_theme_replaces_the_previous_one(audio):
    audio.play_theme("music_ambient")
    first = audio._theme
    audio.play_theme("music_tension")
    assert not first.get_busy() or audio._theme is not first
    audio.stop_theme()


def test_the_theme_follows_the_music_volume_and_master(audio):
    audio.prefs.master, audio.prefs.music = 1.0, 0.5
    audio.play_theme("music_ambient")
    assert audio._theme.get_volume() == pytest.approx(0.5, abs=0.02)
    audio.prefs.music = 0.2
    audio.apply_volumes()
    assert audio._theme.get_volume() == pytest.approx(0.2, abs=0.02)
    audio.stop_theme()


def test_the_theme_ignores_the_sfx_volume_and_the_pause_ducking(audio):
    audio.prefs.master, audio.prefs.music, audio.prefs.sfx = 1.0, 0.8, 0.0
    audio.play_theme("music_ambient")
    audio.set_ducked(True)
    assert audio._theme.get_volume() == pytest.approx(0.8, abs=0.02)
    audio.stop_theme()


def test_a_missing_theme_is_tolerated(audio):
    assert audio.sound_length("ce_theme_n_existe_pas") is None
    assert audio.play_theme("ce_theme_n_existe_pas") is None and not audio.theme_playing


def test_stopping_with_a_fade_and_stopping_nothing(audio):
    audio.stop_theme()  # rien ne joue : sans danger
    audio.play_theme("music_ambient")
    audio.stop_theme(fade_ms=200)
    assert audio._theme is None


def test_a_disabled_audio_has_no_theme(audio):
    audio.enabled = False
    assert audio.sound_length("music_ambient") is None and audio.play_theme("music_ambient") is None


def test_muting_the_music_silences_both_layers_and_unmuting_restores_them(audio):
    audio.start_music()
    before = audio.layer_volumes()
    assert before[0] > 0
    audio.set_music_muted(True)
    assert audio.layer_volumes() == (0.0, 0.0)
    assert all(c.get_volume() == 0 for c in audio._music_channels)
    audio.set_music_muted(False)
    assert audio.layer_volumes() == before and audio._music_channels[0].get_volume() > 0


def test_muting_does_not_touch_sound_effects(audio):
    audio.set_music_muted(True)
    assert audio.play("pickup")
