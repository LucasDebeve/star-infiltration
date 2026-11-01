"""Menu pause : reprendre, recommencer, réglages, retour au menu principal, quitter."""

from __future__ import annotations

import pygame

from game.difficulty import get_difficulty
from game.scenes.menu_base import MenuScene
from game.scenes.settings_scene import SettingsScene
from game.settings import COLORS
from game.ui.backdrop import SnapshotBackdrop
from game.ui.hud import help_lines
from game.ui.menu import Button, Menu


class PauseScene(MenuScene):
    title = "PAUSE"
    top = 210

    def __init__(self, game, play_scene) -> None:
        self.play_scene = play_scene
        # L'écran contient encore la dernière image du jeu : on la fige, floutée, derrière le menu.
        super().__init__(game, SnapshotBackdrop(game.screen))
        self.subtitle = f"Difficulté : {get_difficulty(game.prefs.difficulty).label}"

    def build_menu(self) -> Menu:
        return Menu(
            [
                Button("Reprendre", self._resume),
                Button("Recommencer la mission", self._restart),
                Button("Réglages", self._settings),
                Button("Menu principal", self._main_menu),
                Button("Quitter le jeu", self.game.quit),
            ],
            on_sound=self.sound,
            on_back=self._resume,
        )

    def on_enter(self) -> None:
        self.game.audio.set_ducked(True)

    def on_exit(self) -> None:
        self.game.audio.set_ducked(False)

    def _resume(self) -> None:
        self.game.scenes.pop()

    def _restart(self) -> None:
        self.game.scenes.pop()
        self.play_scene.restart()

    def _settings(self) -> None:
        self.game.scenes.push(SettingsScene(self.game, self.backdrop))

    def _main_menu(self) -> None:
        from game.scenes.main_menu import MainMenuScene  # import tardif : main_menu importe PlayScene, qui importe cette scène

        self.game.scenes.clear()
        self.game.scenes.push(MainMenuScene(self.game))

    def draw_extra(self, surface: pygame.Surface) -> None:
        y = surface.get_height() - 62
        for i, line in enumerate(help_lines()):
            text = self.view.small_font.render(line, True, COLORS["text_dim"])
            surface.blit(text, text.get_rect(midtop=(surface.get_width() // 2, y + i * 24)))
