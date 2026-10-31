"""Menu principal : campagne, réglages, quitter."""
from __future__ import annotations

from game.scenes.campaign_scene import CampaignScene
from game.scenes.menu_base import MenuScene
from game.scenes.settings_scene import SettingsScene
from game.settings import SCREEN_SIZE
from game.ui.backdrop import Starfield
from game.ui.menu import Button, Menu


class MainMenuScene(MenuScene):
    title = "STAR INFILTRATION"
    subtitle = "Un agent rebelle. Un croiseur impérial. Une seule chance."
    big_title = True
    top = 300

    def __init__(self, game) -> None:
        super().__init__(game, Starfield(SCREEN_SIZE))

    def build_menu(self) -> Menu:
        items = [Button("Campagne", self._campaign), Button("Réglages", self._settings)]
        if self.game.dev is not None:
            items.append(Button("Mode développeur", self._dev))
        items.append(Button("Quitter", self.game.quit))
        return Menu(items, on_sound=self.sound)

    def on_enter(self) -> None:
        self.game.audio.start_music()
        self.game.audio.set_tension(0.0)

    def _campaign(self) -> None:
        self.game.scenes.push(CampaignScene(self.game))

    def _dev(self) -> None:
        from game.scenes.dev_scene import DevScene

        self.game.scenes.push(DevScene(self.game, self.backdrop))

    def _settings(self) -> None:
        self.game.scenes.push(SettingsScene(self.game, self.backdrop))
