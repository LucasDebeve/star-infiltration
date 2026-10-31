"""Menu d'un terminal : le jeu est en pause, on choisit une opération parmi celles que la carte autorise à ce terminal.

Une opération démarre une connexion : le menu se ferme, et le joueur doit rester près du terminal jusqu'à son terme
(voir `PlayScene.start_terminal_job`). Échap ferme le menu sans rien faire.
"""
from __future__ import annotations

import pygame

from game.scenes.menu_base import MenuScene
from game.settings import COLORS
from game.ui.backdrop import SnapshotBackdrop
from game.ui.menu import Button, Menu


class TerminalScene(MenuScene):
    title = "TERMINAL"
    top = 250

    def __init__(self, game, play_scene, terminal) -> None:
        self.play_scene = play_scene
        self.terminal = terminal
        self.actions = play_scene.terminal_actions(terminal)  # (action, libellé, disponible, précision)
        super().__init__(game, SnapshotBackdrop(game.screen))  # la dernière image du jeu, floutée
        self.subtitle = "Le jeu est en pause : choisissez une opération"

    def build_menu(self) -> Menu:
        items = []
        for action, label, available, _note in self.actions:
            button = Button(label, lambda action=action: self._choose(action))
            button.enabled = available
            items.append(button)
        items.append(Button("Fermer", self._close))
        return Menu(items, on_sound=self.sound, on_back=self._close)

    def choose(self, action: str) -> bool:
        """Lance l'opération `action` si elle est proposée et disponible. Renvoie vrai si c'est fait."""
        for name, _label, available, _note in self.actions:
            if name == action and available:
                self._choose(action)
                return True
        return False

    def _choose(self, action: str) -> None:
        self.game.scenes.pop()
        self.play_scene.start_terminal_job(self.terminal, action)

    def _close(self) -> None:
        self.game.scenes.pop()

    def on_enter(self) -> None:
        self.game.audio.set_ducked(True)
        self.game.events.emit("terminal_menu_opened", terminal=self.terminal)

    def on_exit(self) -> None:
        self.game.audio.set_ducked(False)

    def draw_extra(self, surface: pygame.Surface) -> None:
        index = self.menu.index
        note = self.actions[index][3] if index < len(self.actions) else "Retour au jeu"
        text = self.view.small_font.render(note, True, COLORS["text_dim"])
        surface.blit(text, text.get_rect(midtop=(surface.get_width() // 2, self.top + (len(self.menu.items)) * 62 + 14)))
