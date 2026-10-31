"""Commandes tactiles (version web sur téléphone ou tablette) : joystick virtuel à gauche, boutons à droite.

Elles n'apparaissent qu'à la première pression d'un doigt (`FINGERDOWN`) : au clavier ou à la manette, rien ne change. Le joystick
naît là où le pouce se pose, dans la moitié gauche de l'écran ; les boutons sont fixes. Comme la manette, les appuis (interagir,
leurre, uniforme, pause) sont **traduits en événements clavier** ; les actions maintenues (interagir, courir, s'accroupir) et le
mouvement sont lus à chaque image (`move`, `run`...). Les menus se touchent comme à la souris (SDL traduit le doigt en clic).
La disposition et la lecture sont pures : les tests envoient de faux événements de doigt.
"""
from __future__ import annotations

import pygame

from game.core import bindings
from game.settings import (
    COLORS,
    QUIT_KEY,
    RESTART_KEY,
    THROW_KEY,
    TOUCH_BUTTON_RADIUS,
    TOUCH_MARGIN,
    TOUCH_STICK_RADIUS,
)

FINGER_EVENTS = (pygame.FINGERDOWN, pygame.FINGERMOTION, pygame.FINGERUP)
# nom -> (libellé, colonne depuis la droite, rangée depuis le bas, tenu (True) ou appui (False))
BUTTONS = {
    "interact": ("E", 0, 0, True),
    "run": ("COURIR", 1, 0, True),
    "crouch": ("BAS", 0, 1, True),
    "throw": ("F", 1, 1, False),
    "disguise": ("U", 2, 1, False),
    "pause": ("II", 0, 2, False),
    "restart": ("R", 1, 2, False),
}


def layout(size: tuple[int, int]) -> dict[str, tuple[pygame.Vector2, int]]:
    """Centre et rayon de chaque bouton, en pixels, pour un écran de `size` : en colonnes serrées dans le coin bas droit."""
    width, height = size
    step = 2 * TOUCH_BUTTON_RADIUS + TOUCH_MARGIN
    return {
        name: (pygame.Vector2(width - TOUCH_MARGIN - TOUCH_BUTTON_RADIUS - col * step, height - TOUCH_MARGIN - TOUCH_BUTTON_RADIUS - row * step), TOUCH_BUTTON_RADIUS)
        for name, (_, col, row, _) in BUTTONS.items()
    }


class TouchControls:
    def __init__(self) -> None:
        self.active = False  # un doigt s'est posé au moins une fois : on affiche les commandes
        self.size = (1, 1)
        self._stick: tuple[int, pygame.Vector2, pygame.Vector2] | None = None  # (doigt, point d'origine, position actuelle)
        self._buttons: dict[int, str] = {}  # doigt -> bouton tenu

    # --- Lecture à chaque image -------------------------------------------------------
    def move(self) -> pygame.Vector2:
        """Direction du joystick virtuel, de longueur 0..1 (nulle au repos)."""
        if self._stick is None:
            return pygame.Vector2()
        _, origin, current = self._stick
        offset = (current - origin) / TOUCH_STICK_RADIUS
        return offset if offset.length() <= 1 else offset.normalize()

    def held(self, name: str) -> bool:
        return name in self._buttons.values()

    def run(self) -> bool:
        return self.held("run")

    def crouch(self) -> bool:
        return self.held("crouch")

    def interact(self) -> bool:
        return self.held("interact")

    # --- Événements --------------------------------------------------------------------
    def process(self, event: pygame.event.Event, size: tuple[int, int]) -> list[pygame.event.Event] | None:
        """Les événements clavier équivalents à un geste, ou None si `event` n'est pas un événement de doigt."""
        if event.type not in FINGER_EVENTS:
            return None
        self.size = size
        point = pygame.Vector2(event.x * size[0], event.y * size[1])
        finger = event.finger_id
        if event.type == pygame.FINGERDOWN:
            self.active = True
            return self._down(finger, point)
        if event.type == pygame.FINGERMOTION:
            if self._stick is not None and self._stick[0] == finger:
                self._stick = (finger, self._stick[1], point)
            return []
        return self._up(finger)

    def _button_at(self, point: pygame.Vector2) -> str | None:
        for name, (center, radius) in layout(self.size).items():
            if point.distance_to(center) <= radius + TOUCH_MARGIN / 2:
                return name
        return None

    def _down(self, finger: int, point: pygame.Vector2) -> list[pygame.event.Event]:
        name = self._button_at(point)
        if name is not None:
            self._buttons[finger] = name
            key = self._key(name)
            return [_key_event(pygame.KEYDOWN, key)] if key is not None and (name == "interact" or not BUTTONS[name][3]) else []
        if point.x < self.size[0] / 2 and self._stick is None:  # le pouce gauche pose le joystick là où il est
            self._stick = (finger, point, point)
        return []

    def _up(self, finger: int) -> list[pygame.event.Event]:
        if self._stick is not None and self._stick[0] == finger:
            self._stick = None
        name = self._buttons.pop(finger, None)
        key = self._key(name) if name == "interact" else None
        return [_key_event(pygame.KEYUP, key)] if key is not None else []

    @staticmethod
    def _key(name: str) -> int | None:
        """Touche que remplace le bouton (celle que le joueur a configurée pour l'action)."""
        if name == "pause":
            return QUIT_KEY
        if name == "restart":
            return RESTART_KEY
        if name == "throw":
            return THROW_KEY
        if name in ("interact", "disguise"):
            return bindings.current.keys(name)[0]
        return None  # courir et s'accroupir se lisent à chaque image

    # --- Dessin ------------------------------------------------------------------------
    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        if not self.active:
            return
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        color = COLORS["text"]
        for name, (center, radius) in layout(surface.get_size()).items():
            down = self.held(name)
            pygame.draw.circle(overlay, (*color, 90 if down else 40), center, radius)
            pygame.draw.circle(overlay, (*color, 150), center, radius, 2)
            label = font.render(BUTTONS[name][0], True, color)
            overlay.blit(label, label.get_rect(center=center))
        if self._stick is not None:
            _, origin, current = self._stick
            knob = origin + self.move() * TOUCH_STICK_RADIUS
            pygame.draw.circle(overlay, (*color, 40), origin, TOUCH_STICK_RADIUS)
            pygame.draw.circle(overlay, (*color, 150), origin, TOUCH_STICK_RADIUS, 2)
            pygame.draw.circle(overlay, (*color, 130), knob, TOUCH_BUTTON_RADIUS // 2)
        surface.blit(overlay, (0, 0))


def _key_event(kind: int, key: int) -> pygame.event.Event:
    return pygame.event.Event(kind, key=key, mod=0, unicode="", scancode=0)


current = TouchControls()  # état partagé, comme `gamepad.current`
