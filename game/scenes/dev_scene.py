"""Menu développeur (`--dev`) : jouer n'importe quel niveau sans le débloquer, et régler les outils de test.

Les parties lancées d'ici n'ont pas de mission : ni score, ni enregistrement, la progression n'est pas touchée.
"""
from __future__ import annotations

from pathlib import Path

import pygame

from game.dev import DEV_KEYS, DEV_LABELS
from game.scenes.menu_base import MenuScene
from game.settings import COLORS, MAPS_DIR
from game.ui.menu import Button, Menu, Toggle


class DevScene(MenuScene):
    title = "MODE DÉVELOPPEUR"
    subtitle = "Jouer n'importe quel niveau — la progression n'est pas enregistrée"
    top = 124
    row_height = 32
    row_gap = 2

    def __init__(self, game, backdrop) -> None:
        super().__init__(game, backdrop)
        self.font = pygame.font.Font(None, 22)

    def build_menu(self) -> Menu:
        dev = self.game.dev
        items = [
            Toggle("Invincible (les gardes ne capturent plus)", lambda: dev.invincible, lambda v: setattr(dev, "invincible", v)),
            Toggle("Fantôme (gardes et caméras aveugles et sourds)", lambda: dev.ghost, lambda v: setattr(dev, "ghost", v)),
        ]
        for number, mission in enumerate(self.game.campaign.missions, start=1):
            items.append(Button(f"{number:>2}. {mission.title}", lambda m=mission: self.play(m.map_path)))
        for path in self.extra_maps():
            items.append(Button(f"Carte libre : {path.name}", lambda p=path: self.play(p)))
        items.append(Button("Retour", self.game.scenes.pop))
        return Menu(items, on_sound=self.sound, on_back=self.game.scenes.pop)

    def extra_maps(self) -> list[Path]:
        """Les cartes de `assets/maps` qu'aucune mission n'utilise (à tester sans les inscrire à la campagne)."""
        used = {Path(m.map_path).resolve() for m in self.game.campaign.missions}
        return sorted(p for p in Path(MAPS_DIR).glob("*.txt") if p.resolve() not in used)

    def play(self, map_path) -> None:
        from game.scenes.play_scene import PlayScene

        self.game.scenes.push(PlayScene(self.game, Path(map_path)))

    def draw_extra(self, surface: pygame.Surface) -> None:
        keys = "   ".join(f"{pygame.key.name(key).upper()} {DEV_LABELS[name]}" for name, key in DEV_KEYS.items())
        text = self.font.render(f"En jeu : {keys}", True, COLORS["text_dim"])
        surface.blit(text, text.get_rect(midbottom=(surface.get_width() // 2, surface.get_height() - 14)))
