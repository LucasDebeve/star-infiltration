"""Réglages : volumes, éclairage, plein écran, difficulté. Enregistrés dès qu'on les change."""

from __future__ import annotations

import pygame

from game.difficulty import all_difficulties, get_difficulty
from game.scenes.menu_base import MenuScene
from game.settings import COLORS, VOLUME_STEP
from game.ui.menu import Button, Choice, Menu, Slider, Toggle


class SettingsScene(MenuScene):
    title = "RÉGLAGES"
    top = 160
    row_height = 46  # neuf lignes : on resserre pour rester au-dessus du texte d'aide
    row_gap = 6

    def __init__(self, game, backdrop) -> None:
        super().__init__(game, backdrop)

    def build_menu(self) -> Menu:
        return Menu(
            [
                self._volume("Volume général", "master"),
                self._volume("Musique", "music"),
                self._volume("Effets sonores", "sfx"),
                Toggle("Éclairage dynamique", lambda: self.game.prefs.lighting, lambda on: self._set("lighting", on)),
                Toggle("Secousses de l'écran", lambda: self.game.prefs.screen_shake, lambda on: self._set("screen_shake", on)),
                Toggle("Plein écran", lambda: self.game.prefs.fullscreen, self._set_fullscreen),
                Choice(
                    "Difficulté",
                    [(d.key, d.label) for d in all_difficulties()],
                    lambda: self.game.prefs.difficulty,
                    lambda key: self._set("difficulty", key),
                ),
                Button("Commandes : touches et manette", self._controls),
                Button("Retour", self._back),
            ],
            on_sound=self.sound,
            on_back=self._back,
        )

    def _volume(self, label: str, name: str) -> Slider:
        return Slider(label, lambda: getattr(self.game.prefs, name), lambda value: self._set(name, value), step=VOLUME_STEP)

    def _set(self, name: str, value) -> None:
        setattr(self.game.prefs, name, value)
        self.game.prefs.save()
        self.game.audio.apply_volumes()  # sans effet si ce n'est pas un volume

    def _set_fullscreen(self, wanted: bool) -> None:
        self.game.set_fullscreen(wanted)
        self._set("fullscreen", self.game.fullscreen)  # ce que le système a vraiment accordé

    def _controls(self) -> None:
        from game.scenes.controls_scene import ControlsScene  # import tardif : cette scène a besoin de `MenuScene`, comme celle-ci

        self.game.scenes.push(ControlsScene(self.game, self.backdrop))

    def _back(self) -> None:
        self.game.scenes.pop()

    def draw_extra(self, surface: pygame.Surface) -> None:
        difficulty = get_difficulty(self.game.prefs.difficulty)
        lines = (
            f"{difficulty.label} : détection des gardes ×{difficulty.detect:g}, verrouillage en {difficulty.lockdown_time:.0f} s, {difficulty.waves} vague(s) de renforts.",
            "La difficulté s'applique à la prochaine mission.     Haut / Bas : choisir     Gauche / Droite : régler     Échap : retour",
        )
        y = surface.get_height() - 70
        for i, line in enumerate(lines):
            text = self.view.small_font.render(line, True, COLORS["text_dim"])
            surface.blit(text, text.get_rect(midtop=(surface.get_width() // 2, y + i * 24)))
