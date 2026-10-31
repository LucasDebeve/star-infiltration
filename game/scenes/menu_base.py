"""Base commune des scènes de menu : clavier, souris, fond animé, titre, sons."""
from __future__ import annotations

import pygame

from game.core.scene import Scene
from game.settings import MENU_KEYS
from game.ui.menu import ROW_GAP, ROW_HEIGHT, Menu, MenuView, row_rects


def _is(key: int, action: str) -> bool:
    return key in MENU_KEYS[action]


class MenuScene(Scene):
    title = ""
    subtitle = ""
    big_title = False
    top = 270  # ordonnée de la première ligne
    row_height = ROW_HEIGHT  # une liste longue peut resserrer ses lignes
    row_gap = ROW_GAP

    def __init__(self, game, backdrop) -> None:
        super().__init__(game)
        self.backdrop = backdrop
        self.view = MenuView()
        self.menu: Menu = self.build_menu()

    def build_menu(self) -> Menu:
        raise NotImplementedError

    def sound(self, name: str) -> None:
        self.game.audio.play(name)

    # --- Entrées -------------------------------------------------------------
    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if _is(event.key, "up"):
                self.menu.move(-1)
            elif _is(event.key, "down"):
                self.menu.move(1)
            elif _is(event.key, "left"):
                self.menu.adjust(-1)
            elif _is(event.key, "right"):
                self.menu.adjust(1)
            elif _is(event.key, "confirm"):
                self.menu.activate()
            elif _is(event.key, "back"):
                self.menu.back()
        elif event.type == pygame.MOUSEMOTION:
            self.menu.select(self._row_at(event.pos))
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            row = self._row_at(event.pos)
            if row is not None:
                self.menu.select(row)
                self._click(row, event.pos)

    def _row_at(self, pos) -> int | None:
        for i, rect in enumerate(row_rects(self.game.screen.get_size(), len(self.menu.items), self.top, self.row_height, self.row_gap)):
            if rect.collidepoint(pos):
                return i
        return None

    def _click(self, row: int, pos) -> None:
        """Clic : un curseur se règle selon le côté cliqué, tout le reste s'active."""
        item = self.menu.items[row]
        if item.fraction() is None:
            self.menu.activate()
            return
        rect = row_rects(self.game.screen.get_size(), len(self.menu.items), self.top, self.row_height, self.row_gap)[row]
        self.menu.adjust(1 if pos[0] > rect.centerx + 60 else -1)

    # --- Boucle --------------------------------------------------------------
    def update(self, dt: float) -> None:
        self.backdrop.update(dt)

    def draw(self, surface: pygame.Surface) -> None:
        self.backdrop.draw(surface)
        self.view.draw_title(surface, self.title, self.subtitle, big=self.big_title)
        self.view.draw_menu(surface, self.menu, self.top, self.row_height, self.row_gap)
        self.draw_extra(surface)

    def draw_extra(self, surface: pygame.Surface) -> None:
        """Éléments propres à une scène, sous le menu."""
