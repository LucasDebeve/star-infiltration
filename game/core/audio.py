"""Son : effets (localisés ou non) et musique à deux couches (calme / tendue) fondues l'une dans l'autre.

Si le périphérique audio est absent ou refuse de s'ouvrir, le jeu continue en silence. Un fichier de son
manquant n'est pas une erreur non plus : on l'ignore (et on le signale une seule fois dans les journaux).
Les calculs de volume sont des fonctions pures, testées sans carte son.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pygame

from game.core import dsp
from game.core.preferences import Preferences
from game.settings import (
    AMBIENT_FLOOR,
    DUCK_VOLUME,
    MIXER_CHANNELS,
    MUFFLE_CUTOFFS,
    MUSIC_CHANNELS,
    OCCLUSION_VOLUME,
    REVERB_MAX_SOUND,
    REVERB_TAPS,
    SOUND_RANGE,
    SOUNDS_DIR,
    TENSION_FADE_TIME,
)

log = logging.getLogger(__name__)
MUSIC_LAYERS = ("music_ambient",)


def attenuation(distance: float, max_distance: float = SOUND_RANGE) -> float:
    """Volume (0..1) d'un son à `distance` : décroissance douce, nulle au-delà de `max_distance`."""
    if distance >= max_distance:
        return 0.0
    return (1.0 - distance / max_distance) ** 2


def stereo_pan(dx: float, max_distance: float = SOUND_RANGE) -> float:
    """Balance (-1 gauche .. 1 droite) selon le décalage horizontal de la source."""
    return max(-1.0, min(1.0, dx / max_distance))


def channel_volumes(volume: float, pan: float = 0.0) -> tuple[float, float]:
    """Volumes (gauche, droite) : la voie du côté opposé à la source s'atténue, l'autre reste intacte."""
    return volume * (1.0 - max(0.0, pan)), volume * (1.0 + min(0.0, pan))


def music_levels(tension: float) -> tuple[float, float]:
    """Poids (calme, tendue) de chaque couche pour une tension de 0 à 1 (fondu enchaîné à puissance constante)."""
    tension = max(0.0, min(1.0, tension))
    return (1.0 - tension) ** 0.5, tension ** 0.5


class Audio:
    def __init__(self, prefs: Preferences, sounds_dir: Path = SOUNDS_DIR) -> None:
        self.prefs = prefs
        self.sounds_dir = Path(sounds_dir)
        self.enabled = self._init_mixer()
        self.tension = 0.0  # tension réelle (fondue)
        self.tension_target = 0.0
        self.ducked = False
        self.music_muted = False  # la musique d'ambiance se tait (pendant le générique, qui a sa propre musique)
        self._theme: pygame.mixer.Channel | None = None
        self._sounds: dict[str, pygame.mixer.Sound | None] = {}
        self._variants: dict[tuple[str, int, int], pygame.mixer.Sound | None] = {}  # (nom, étouffement, écho) -> son filtré
        self._music_channels: list[pygame.mixer.Channel] = []
        self._loops: dict[str, tuple[pygame.mixer.Channel, float]] = {}  # effets en boucle : nom -> (voie, volume relatif)
        self._ambient: dict[str, list] = {}  # ambiances : nom -> [voie, volume, balance]

    @staticmethod
    def _init_mixer() -> bool:
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.set_num_channels(MIXER_CHANNELS + MUSIC_CHANNELS)
            pygame.mixer.set_reserved(MUSIC_CHANNELS)
        except pygame.error as exc:
            log.warning("Audio indisponible, le jeu sera silencieux : %s", exc)
            return False
        return True

    # --- Effets --------------------------------------------------------------
    def _sound(self, name: str) -> pygame.mixer.Sound | None:
        if name not in self._sounds:
            path = self.sounds_dir / f"{name}.wav"
            if not path.exists() and (self.sounds_dir / f"{name}.ogg").exists():
                path = self.sounds_dir / f"{name}.ogg"  # la version web livre des .ogg (les navigateurs lisent mal les .wav)
            try:
                self._sounds[name] = pygame.mixer.Sound(str(path))
            except (pygame.error, FileNotFoundError):
                log.warning("Son introuvable ou illisible : %s", path)
                self._sounds[name] = None
        return self._sounds[name]

    @property
    def sfx_volume(self) -> float:
        return self.prefs.master * self.prefs.sfx

    def _variant(self, name: str, muffle: int, reverb: int) -> pygame.mixer.Sound | None:
        """Le son `name` filtré (étouffé par `muffle` murs, avec l'écho de niveau `reverb`), fabriqué à la première demande.

        Sans filtre à appliquer, ou si le format du mixeur n'est pas du 16 bits, ou pour un son long : le son d'origine."""
        base = self._sound(name)
        if base is None or (muffle <= 0 and reverb <= 0):
            return base
        key = (name, muffle, reverb)
        if key not in self._variants:
            self._variants[key] = self._filtered(base, muffle, reverb)
        return self._variants[key]

    @staticmethod
    def _filtered(base: pygame.mixer.Sound, muffle: int, reverb: int) -> pygame.mixer.Sound:
        init = pygame.mixer.get_init()
        if init is None or init[1] != -16 or base.get_length() > REVERB_MAX_SOUND:
            return base
        rate, _, channels = init
        raw = base.get_raw()
        cutoff = MUFFLE_CUTOFFS[min(muffle, len(MUFFLE_CUTOFFS) - 1)]
        try:
            if cutoff:
                raw = dsp.lowpass(raw, channels, rate, cutoff)
            raw = dsp.echo(raw, channels, rate, REVERB_TAPS[min(reverb, len(REVERB_TAPS) - 1)])
            return pygame.mixer.Sound(buffer=raw)
        except (pygame.error, ValueError):
            return base

    def play(self, name: str, volume: float = 1.0, pan: float = 0.0, walls: int = 0, reverb: int = 0) -> bool:
        """Joue un effet ; renvoie faux s'il n'a pas pu l'être (muet, introuvable, plus de voie libre).

        `walls` : murs entre la source et le joueur (le son est étouffé et plus faible) ; `reverb` : niveau d'écho de la salle."""
        if not self.enabled:
            return False
        level = self.sfx_volume * volume * OCCLUSION_VOLUME ** max(0, walls)
        sound = self._variant(name, walls, reverb)
        if sound is None or level <= 0.0:
            return False
        channel = sound.play()
        if channel is None:
            return False
        channel.set_volume(*channel_volumes(level, pan))
        return True

    def play_at(self, name: str, source, listener, volume: float = 1.0, walls: int = 0, reverb: int = 0) -> bool:
        """Joue un effet localisé : plus faible avec la distance, balancé selon le côté de la source, sourd derrière un mur."""
        distance = pygame.Vector2(source).distance_to(listener)
        loudness = attenuation(distance)
        if loudness <= 0.0:
            return False
        return self.play(name, volume * loudness, stereo_pan(source[0] - listener[0]), walls, reverb)

    # --- Effets en boucle ----------------------------------------------------
    def start_loop(self, name: str, volume: float = 1.0) -> bool:
        """Lance un effet en boucle (sans effet s'il tourne déjà). Il se tait pendant la pause."""
        if name in self._loops:
            return True
        sound = self._sound(name) if self.enabled else None
        channel = sound.play(loops=-1) if sound is not None else None
        if channel is None:
            return False
        self._loops[name] = (channel, volume)
        self.apply_volumes()
        return True

    def stop_loop(self, name: str) -> None:
        loop = self._loops.pop(name, None)
        if loop is not None:
            loop[0].stop()

    def stop_loops(self) -> None:
        for name in list(self._loops):
            self.stop_loop(name)

    def is_looping(self, name: str) -> bool:
        return name in self._loops

    # --- Ambiances (boucles dont le volume et la balance suivent le joueur) ------
    def set_ambient(self, name: str, level: float, pan: float = 0.0) -> None:
        """Règle une ambiance en boucle : la lance si elle devient audible, l'arrête quand elle ne l'est plus."""
        if not self.enabled or level < AMBIENT_FLOOR:
            self.stop_ambient(name)
            return
        entry = self._ambient.get(name)
        if entry is None:
            sound = self._sound(name)
            channel = sound.play(loops=-1) if sound is not None else None
            if channel is None:
                return
            entry = self._ambient[name] = [channel, level, pan]
        entry[1], entry[2] = level, pan
        self._apply_ambient(entry)

    def stop_ambient(self, name: str | None = None) -> None:
        """Arrête une ambiance, ou toutes si `name` est omis."""
        for key in [name] if name is not None else list(self._ambient):
            entry = self._ambient.pop(key, None)
            if entry is not None:
                entry[0].stop()

    def is_ambient(self, name: str) -> bool:
        return name in self._ambient

    def ambient_volumes(self, name: str) -> tuple[float, float] | None:
        """Volumes (gauche, droite) actuellement appliqués à une ambiance, ou None si elle ne joue pas."""
        entry = self._ambient.get(name)
        if entry is None:
            return None
        return channel_volumes(0.0 if self.ducked else self.sfx_volume * entry[1], entry[2])

    def _apply_ambient(self, entry) -> None:
        name = next(key for key, value in self._ambient.items() if value is entry)
        entry[0].set_volume(*self.ambient_volumes(name))

    # --- Thème (une longue musique jouée une fois, comme le générique) -------------
    def sound_length(self, name: str) -> float | None:
        """Durée d'un son en secondes, ou None s'il est introuvable ou si l'audio est coupé."""
        sound = self._sound(name) if self.enabled else None
        return sound.get_length() if sound is not None else None

    def play_theme(self, name: str) -> float | None:
        """Joue `name` une fois, au volume de la musique. Renvoie sa durée, ou None s'il n'a pas pu l'être."""
        self.stop_theme()
        sound = self._sound(name) if self.enabled else None
        channel = sound.play() if sound is not None else None
        if channel is None:
            return None
        self._theme = channel
        self.apply_volumes()
        return sound.get_length()

    def stop_theme(self, fade_ms: int = 0) -> None:
        if self._theme is not None:
            if fade_ms > 0:
                self._theme.fadeout(fade_ms)
            else:
                self._theme.stop()
            self._theme = None

    @property
    def theme_playing(self) -> bool:
        return self._theme is not None and self._theme.get_busy()

    def set_music_muted(self, muted: bool) -> None:
        self.music_muted = muted
        self.apply_volumes()

    # --- Musique -------------------------------------------------------------
    def start_music(self) -> None:
        """Lance les deux couches en boucle (sans effet si elles tournent déjà)."""
        if not self.enabled or self._music_channels:
            return
        for name in MUSIC_LAYERS:
            sound = self._sound(name)
            channel = pygame.mixer.Channel(len(self._music_channels))
            if sound is not None:
                channel.play(sound, loops=-1)
            self._music_channels.append(channel)
        self.apply_volumes()

    def stop_music(self) -> None:
        for channel in self._music_channels:
            channel.stop()
        self._music_channels = []

    def set_tension(self, target: float) -> None:
        self.tension_target = max(0.0, min(1.0, target))

    def set_ducked(self, ducked: bool) -> None:
        self.ducked = ducked
        self.apply_volumes()

    def update(self, dt: float) -> None:
        """Fait avancer le fondu de la musique vers la tension demandée."""
        step = dt / TENSION_FADE_TIME
        if self.tension < self.tension_target:
            self.tension = min(self.tension_target, self.tension + step)
        else:
            self.tension = max(self.tension_target, self.tension - step)
        self.apply_volumes()

    def layer_volumes(self) -> tuple[float, float]:
        """Volumes finaux (calme, tendue) compte tenu des préférences, de la tension et de la pause."""
        base = 0.0 if self.music_muted else self.prefs.master * self.prefs.music * (DUCK_VOLUME if self.ducked else 1.0)
        calm, tense = music_levels(self.tension)
        return base * calm, base * tense

    def apply_volumes(self) -> None:
        """À appeler quand les préférences changent (réglages) ou à chaque image (fondu)."""
        for channel, volume in zip(self._music_channels, self.layer_volumes()):
            channel.set_volume(volume)
        if self._theme is not None:
            self._theme.set_volume(self.prefs.master * self.prefs.music)
        for channel, relative in self._loops.values():
            channel.set_volume(0.0 if self.ducked else self.sfx_volume * relative)
        for entry in self._ambient.values():
            self._apply_ambient(entry)
