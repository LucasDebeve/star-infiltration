"""Directeur sonore : traduit les événements du jeu en sons, sans que le jeu connaisse l'audio.

Il s'abonne à l'`EventBus` (pas, portes, objets, alerte...) et observe les gardes pour annoncer qu'ils se
méfient ou qu'ils ont repéré le joueur. Pendant l'alerte générale, la musique normale continue et le klaxon
tourne en boucle ; la musique ne devient plus tendue qu'à l'approche de l'alerte (un garde qui enquête).
`audio` est tout objet qui offre `play`, `play_at` et `set_tension` : les tests injectent un faux.

Acoustique (`set_acoustics`) : un son localisé arrive étouffé s'il traverse des murs ou des portes fermées, et résonne selon la
taille de la salle où il retentit ; les pas du joueur résonnent dans sa propre salle. Sans acoustique (cartes de test), tout est net.
Voix : les gardes lancent une réplique quand ils soupçonnent, repèrent ou perdent le joueur, et la radio crachote à l'alerte
(`VoiceBank` choisit la variante sans répéter).
"""

from __future__ import annotations

import random

import pygame

from game.ai.guard import GuardState
from game.settings import ALERT_LOOP_VOLUME, HACK_TICK_INTERVAL, RADIO_VOLUME, VOICE_VOLUME
from game.systems.voices import VoiceBank

# Événement -> (son, volume). Les événements localisés sont traités à part.
PLAIN_SOUNDS = {
    "item_picked": ("pickup", 1.0),
    "interaction_denied": ("door_denied", 1.0),
    "terminal_hacked": ("hack_done", 1.0),
    "terminal_menu_opened": ("terminal_open", 1.0),
    "camera_spotted": ("spotted", 0.8),
    "cameras_disabled": ("camera_off", 1.0),
    "lights_out": ("lights_out", 1.0),
    "power_cut": ("power_down", 1.0),
    "uniform_stolen": ("locker_open", 1.0),
    "disguise_changed": ("disguise", 0.9),
    "ships_released": ("tractor_off", 1.0),
    "cells_opened": ("cell_open", 1.0),
    "prisoner_freed": ("hack_done", 1.0),  # toute la coque l'entend : non localisé
    "mission_complete": ("win", 1.0),
    "player_caught": ("caught", 1.0),
    "reinforcements_arrived": ("reinforcements", 1.0),
    "lockdown": ("lockdown", 1.0),
}
STEP_SOUNDS = {"run": ("step_walk", 0.5), "walk": ("step_walk", 0.2)}
TENSION_SUSPICION = 0.4  # musique un peu plus tendue tant qu'un garde enquête (avant l'alerte générale)
ALERT_LOOP = "alert"


class SoundDirector:
    def __init__(self, audio, events, voices: VoiceBank | None = None) -> None:
        self.audio = audio
        self.events = events
        self.voices = voices or VoiceBank(rng=random.Random())
        self.acoustics = None  # `Acoustics` de la carte : sans elle, aucun son n'est étouffé ni ne résonne
        self.listener = pygame.Vector2()  # position du joueur : les sons localisés s'entendent depuis là
        self._guard_states: dict[int, GuardState] = {}
        self._hack_timer = 0.0
        self._handlers = {name: self._plain(*spec, radio=name in self.RADIO_EVENTS) for name, spec in PLAIN_SOUNDS.items()}
        self._handlers.update(
            alert_raised=self._on_alert_raised,
            footstep=self._on_footstep,
            door_opened=self._on_door_opened,
            decoy_thrown=self._on_decoy_thrown,
            decoy_beep=self._on_decoy_beep,
            button_pressed=self._on_button_pressed,
            field_toggled=self._on_field_toggled,
            vent_burst=self._on_vent_burst,
        )
        self._buttons: dict[str, pygame.Vector2] = {}  # position des boutons et des champs, pour localiser leurs sons
        self._fields: dict[str, pygame.Vector2] = {}

    # --- Cycle de vie --------------------------------------------------------
    def attach(self) -> None:
        for name, handler in self._handlers.items():
            self.events.subscribe(name, handler)

    def detach(self) -> None:
        for name, handler in self._handlers.items():
            self.events.unsubscribe(name, handler)
        self.audio.stop_loop(ALERT_LOOP)

    def set_acoustics(self, acoustics) -> None:
        self.acoustics = acoustics

    def _at(self, sound: str, pos, volume: float = 1.0) -> None:
        """Joue un son localisé, avec l'étouffement et l'écho que la carte lui donne."""
        extra = self.acoustics.effects(pos, self.listener) if self.acoustics is not None else {}
        self.audio.play_at(sound, pos, self.listener, volume, **extra)

    def _own(self, sound: str, volume: float) -> None:
        """Joue un son du joueur : il résonne dans sa salle."""
        extra = self.acoustics.own(self.listener) if self.acoustics is not None else {}
        self.audio.play(sound, volume, **extra)

    # --- Événements ----------------------------------------------------------
    RADIO_EVENTS = ("camera_spotted", "reinforcements_arrived")  # ces événements font aussi crachoter la radio des gardes

    def _plain(self, sound: str, volume: float, radio: bool = False):
        def handler(**_payload) -> None:
            self.audio.play(sound, volume)
            if radio:
                self._radio()

        return handler

    def _radio(self) -> None:
        name = self.voices.pick("radio", urgent=True)
        if name is not None:
            self.audio.play(name, RADIO_VOLUME)

    def _on_alert_raised(self, **_payload) -> None:
        self._radio()

    def _voice(self, category: str, pos, *, urgent: bool = False) -> None:
        """Un garde en `pos` lance une réplique de `category` (si le banc de voix l'autorise)."""
        name = self.voices.pick(category, urgent=urgent)
        if name is not None:
            self._at(name, pos, VOICE_VOLUME)

    def _on_footstep(self, stance: str, **_payload) -> None:
        sound, volume = STEP_SOUNDS.get(stance, STEP_SOUNDS["walk"])
        self._own(sound, volume)

    def _on_door_opened(self, door, **_payload) -> None:
        self._at("door_open", door.anchor)

    def set_anchors(self, buttons: dict, fields: dict) -> None:
        """Positions (px) des boutons et des champs de force de la carte : leurs sons s'entendent de là où ils sont."""
        self._buttons = {k: pygame.Vector2(v) for k, v in buttons.items()}
        self._fields = {k: pygame.Vector2(v) for k, v in fields.items()}

    def _on_button_pressed(self, button, **_payload) -> None:
        self._play_from("button_press", self._buttons.get(button))

    def _on_field_toggled(self, field, active, **_payload) -> None:
        self._play_from("field_on" if active else "field_off", self._fields.get(field))

    def _on_vent_burst(self, pos, **_payload) -> None:
        self._at("steam_vent", pos, 0.7)

    def _play_from(self, sound: str, pos) -> None:
        if pos is None:  # position inconnue : on l'entend comme un bruit proche plutôt que de le perdre
            self.audio.play(sound, 0.6)
        else:
            self._at(sound, pos)

    def _on_decoy_thrown(self, pos, **_payload) -> None:
        self.audio.play("decoy_throw", 0.8)

    def _on_decoy_beep(self, pos, **_payload) -> None:
        self._at("decoy_beep", pos)

    # --- Observation à chaque image -------------------------------------------
    def update(self, dt: float, guards, listener, *, hacking: bool, alert_active: bool) -> None:
        self.listener.update(listener)
        self.voices.tick(dt)
        self._announce_guards(guards)
        self._tick_hacking(dt, hacking)
        self._alert_klaxon(alert_active)
        suspicious = max((g.state.threat for g in guards), default=0) > 0
        # Pendant l'alerte, la musique reste la musique normale : c'est le klaxon qui porte la tension.
        self.audio.set_tension(TENSION_SUSPICION if suspicious and not alert_active else 0.0)

    def _alert_klaxon(self, alert_active: bool) -> None:
        if alert_active:
            self.audio.start_loop(ALERT_LOOP, ALERT_LOOP_VOLUME)
        else:
            self.audio.stop_loop(ALERT_LOOP)

    def _announce_guards(self, guards) -> None:
        """Un garde qui passe de calme à méfiant, ou à la poursuite, le fait savoir (un nouvel arrivant se tait)."""
        states = {id(g): g.state for g in guards}
        for guard in guards:
            before = self._guard_states.get(id(guard))
            if before is None or before is guard.state:
                continue
            if guard.state is GuardState.CHASE:
                self._at("spotted", guard.pos)
                self._voice("chase", guard.pos, urgent=True)
            elif before is GuardState.PATROL and guard.state is GuardState.INVESTIGATE:
                self._at("suspect", guard.pos, 0.8)
                self._voice("suspect", guard.pos)
            elif before is GuardState.CHASE and guard.state is GuardState.SEARCH:
                self._voice("lost", guard.pos)
        self._guard_states = states

    def _tick_hacking(self, dt: float, hacking: bool) -> None:
        if not hacking:
            self._hack_timer = 0.0
            return
        self._hack_timer -= dt
        if self._hack_timer <= 0:
            self._hack_timer = HACK_TICK_INTERVAL
            self.audio.play("hack_tick", 0.7)
