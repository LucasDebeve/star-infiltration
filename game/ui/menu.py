"""Menus : modèle (éléments, navigation, réglages) pur et testable, plus son affichage.

Éléments : `Button` (action), `Slider` (valeur bornée), `Toggle` (oui / non), `Choice` (liste de valeurs).
`Menu` gère la sélection ; la scène lui transmet les touches ou la souris, et un callback joue les sons.
"""

from __future__ import annotations

from typing import Any, Callable

import pygame

from game.settings import COLORS

SoundCallback = Callable[[str], None]


class MenuItem:
    enabled = True

    def __init__(self, label: str) -> None:
        self.label = label

    def activate(self) -> bool:
        """Touche Entrée / clic. Renvoie vrai si quelque chose s'est passé."""
        return False

    def adjust(self, direction: int) -> bool:
        """Flèche gauche (-1) ou droite (+1). Renvoie vrai si la valeur a changé."""
        return False

    def value_text(self) -> str:
        return ""

    def fraction(self) -> float | None:
        """Remplissage (0..1) d'une barre, pour les curseurs."""
        return None


class Button(MenuItem):
    def __init__(self, label: str, action: Callable[[], None]) -> None:
        super().__init__(label)
        self.action = action

    def activate(self) -> bool:
        if not self.enabled:
            return False
        self.action()
        return True


class Slider(MenuItem):
    def __init__(self, label: str, get: Callable[[], float], set_: Callable[[float], None], step: float = 0.1, lo: float = 0.0, hi: float = 1.0) -> None:
        super().__init__(label)
        self.get, self.set, self.step, self.lo, self.hi = get, set_, step, lo, hi

    def adjust(self, direction: int) -> bool:
        before = self.get()
        value = round(max(self.lo, min(self.hi, before + direction * self.step)), 2)
        if value == before:
            return False
        self.set(value)
        return True

    def activate(self) -> bool:
        return True  # Entrée sur un curseur : simple retour sonore (aperçu du volume)

    def value_text(self) -> str:
        return f"{round(self.get() * 100)} %"

    def fraction(self) -> float:
        return (self.get() - self.lo) / (self.hi - self.lo)


class Toggle(MenuItem):
    def __init__(self, label: str, get: Callable[[], bool], set_: Callable[[bool], None]) -> None:
        super().__init__(label)
        self.get, self.set = get, set_

    def activate(self) -> bool:
        self.set(not self.get())
        return True

    def adjust(self, direction: int) -> bool:
        wanted = direction > 0
        if self.get() == wanted:
            return False
        self.set(wanted)
        return True

    def value_text(self) -> str:
        return "Activé" if self.get() else "Désactivé"


class Choice(MenuItem):
    def __init__(self, label: str, options: list[tuple[Any, str]], get: Callable[[], Any], set_: Callable[[Any], None]) -> None:
        super().__init__(label)
        self.options, self.get, self.set = options, get, set_

    def _index(self) -> int:
        keys = [key for key, _ in self.options]
        return keys.index(self.get()) if self.get() in keys else 0

    def adjust(self, direction: int) -> bool:
        self.set(self.options[(self._index() + direction) % len(self.options)][0])
        return True

    def activate(self) -> bool:
        return self.adjust(1)

    def value_text(self) -> str:
        return self.options[self._index()][1]


class KeyBind(MenuItem):
    """Une commande remappable : deux emplacements de touche. Gauche / droite choisit l'emplacement, Entrée le change."""

    def __init__(self, label: str, texts: Callable[[], tuple[str, str]], capture: Callable[[int], None]) -> None:
        super().__init__(label)
        self.texts, self.capture = texts, capture
        self.slot = 0

    def adjust(self, direction: int) -> bool:
        self.slot = (self.slot + direction) % 2
        return True

    def activate(self) -> bool:
        self.capture(self.slot)
        return True

    def value_text(self) -> str:
        parts = list(self.texts())
        parts[self.slot] = f"[{parts[self.slot]}]"  # l'emplacement que « Entrée » va changer
        return "   ".join(parts)


class Menu:
    def __init__(self, items: list[MenuItem], on_sound: SoundCallback | None = None, on_back: Callable[[], None] | None = None) -> None:
        if not items:
            raise ValueError("Un menu a besoin d'au moins un élément")
        self.items = items
        self.index = next((i for i, item in enumerate(items) if item.enabled), 0)
        self._sound = on_sound or (lambda name: None)
        self._on_back = on_back

    @property
    def selected(self) -> MenuItem:
        return self.items[self.index]

    def move(self, direction: int) -> None:
        """Descend (+1) ou monte (-1) en bouclant, en sautant les éléments désactivés."""
        for _ in range(len(self.items)):
            self.index = (self.index + direction) % len(self.items)
            if self.selected.enabled:
                self._sound("ui_move")
                return

    def select(self, index: int | None) -> None:
        """Sélection à la souris (`None` : le pointeur n'est sur aucune ligne). Ne fait du bruit que si elle change."""
        if index is not None and 0 <= index < len(self.items) and self.items[index].enabled and index != self.index:
            self.index = index
            self._sound("ui_move")

    def activate(self) -> None:
        if self.selected.activate():
            self._sound("ui_select")

    def adjust(self, direction: int) -> None:
        if self.selected.adjust(direction):
            self._sound("ui_select")

    def back(self) -> None:
        if self._on_back:
            self._sound("ui_back")
            self._on_back()


# --- Affichage ---------------------------------------------------------------
ROW_HEIGHT = 54
ROW_WIDTH = 620
ROW_GAP = 8
TRACK_WIDTH = 190
TRACK_HEIGHT = 10


def row_rects(size: tuple[int, int], count: int, top: int, height: int = ROW_HEIGHT, gap: int = ROW_GAP) -> list[pygame.Rect]:
    """Rectangles des lignes d'un menu centré horizontalement (sert à dessiner et à repérer la souris)."""
    return [pygame.Rect((size[0] - ROW_WIDTH) // 2, top + i * (height + gap), ROW_WIDTH, height) for i in range(count)]


class MenuView:
    def __init__(self) -> None:
        self.title_font = pygame.font.Font(None, 92)
        self.heading_font = pygame.font.Font(None, 64)
        self.item_font = pygame.font.Font(None, 38)
        self.small_font = pygame.font.Font(None, 24)

    def draw_title(self, surface: pygame.Surface, title: str, subtitle: str = "", *, big: bool = True, y: int = 70) -> None:
        font = self.title_font if big else self.heading_font
        shadow = font.render(title, True, COLORS["shadow"])
        text = font.render(title, True, COLORS["text"])
        rect = text.get_rect(midtop=(surface.get_width() // 2, y))
        surface.blit(shadow, rect.move(3, 4))
        surface.blit(text, rect)
        if subtitle:
            sub = self.small_font.render(subtitle, True, COLORS["text_dim"])
            surface.blit(sub, sub.get_rect(midtop=(rect.centerx, rect.bottom + 6)))

    def draw_menu(self, surface: pygame.Surface, menu: Menu, top: int, height: int = ROW_HEIGHT, gap: int = ROW_GAP) -> list[pygame.Rect]:
        rects = row_rects(surface.get_size(), len(menu.items), top, height, gap)
        for i, (item, rect) in enumerate(zip(menu.items, rects)):
            self._draw_row(surface, item, rect, selected=i == menu.index)
        return rects

    def _draw_row(self, surface: pygame.Surface, item: MenuItem, rect: pygame.Rect, selected: bool) -> None:
        accent = COLORS["terminal_screen"]
        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, (*COLORS["panel"], 215 if selected else 150), panel.get_rect(), border_radius=12)
        pygame.draw.rect(panel, (*(accent if selected else COLORS["panel_border"]), 255), panel.get_rect(), 2 if selected else 1, border_radius=12)
        surface.blit(panel, rect)

        color = COLORS["text"] if selected else COLORS["text_dim"]
        if not item.enabled:
            color = COLORS["panel_border"]
        label = self.item_font.render(item.label, True, color)
        surface.blit(label, label.get_rect(midleft=(rect.x + 24, rect.centery)))
        if selected:  # repère à gauche
            pygame.draw.polygon(surface, accent, [(rect.x + 8, rect.centery - 7), (rect.x + 8, rect.centery + 7), (rect.x + 16, rect.centery)])

        value = item.value_text()
        right = rect.right - 24
        if value:
            text = self.item_font.render(value, True, accent if selected else COLORS["text_dim"])
            surface.blit(text, text.get_rect(midright=(right, rect.centery)))
            right -= text.get_width() + 18
        fraction = item.fraction()
        if fraction is not None:
            track = pygame.Rect(right - TRACK_WIDTH, rect.centery - TRACK_HEIGHT // 2, TRACK_WIDTH, TRACK_HEIGHT)
            pygame.draw.rect(surface, COLORS["background"], track, border_radius=5)
            fill = track.copy()
            fill.w = max(0, round(track.w * fraction))
            if fill.w:
                pygame.draw.rect(surface, accent if selected else COLORS["text_dim"], fill, border_radius=5)
            pygame.draw.rect(surface, COLORS["panel_border"], track, 1, border_radius=5)
