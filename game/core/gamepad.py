"""Manette : lecture du joystick et des boutons, et traduction des appuis en touches pour les scènes.

En jeu, les mouvements et les actions maintenues (courir, s'accroupir, interagir) sont lus à chaque image (`move`, `run`...).
Les appuis (interagir, lancer un leurre, recommencer, pause) et toute la navigation des menus sont **traduits en événements
clavier** (`translate`) : les scènes n'ont rien à savoir de la manette, et le maintien pour passer le générique marche aussi.

Disposition (norme SDL, boutons nommés comme sur une manette Xbox) :
    joystick gauche / croix : se déplacer · joystick droit : viser · RT ou RB : courir · B ou clic du joystick : s'accroupir
    A : interagir / confirmer · X : lancer un leurre · LB : enfiler l'uniforme · Y : recommencer · Start : pause · menus : croix ou joystick, A, B
Un « pad » est tout objet qui offre `get_axis(axe) -> -1..1`, `get_button(bouton) -> bool`, `name` et `instance_id` :
les tests en injectent un faux.
"""
from __future__ import annotations

import pygame

from game.core import bindings
from game.settings import (
    GAMEPAD_DEADZONE,
    GAMEPAD_NAV_OFF,
    GAMEPAD_NAV_ON,
    GAMEPAD_TRIGGER,
    RESTART_KEY,
)

MENU = "menu"
GAME = "game"

A, B, X, Y = pygame.CONTROLLER_BUTTON_A, pygame.CONTROLLER_BUTTON_B, pygame.CONTROLLER_BUTTON_X, pygame.CONTROLLER_BUTTON_Y
START = pygame.CONTROLLER_BUTTON_START
LEFT_STICK, RIGHT_SHOULDER = pygame.CONTROLLER_BUTTON_LEFTSTICK, pygame.CONTROLLER_BUTTON_RIGHTSHOULDER
LEFT_SHOULDER = pygame.CONTROLLER_BUTTON_LEFTSHOULDER
DPAD = {
    pygame.CONTROLLER_BUTTON_DPAD_UP: (0, -1),
    pygame.CONTROLLER_BUTTON_DPAD_DOWN: (0, 1),
    pygame.CONTROLLER_BUTTON_DPAD_LEFT: (-1, 0),
    pygame.CONTROLLER_BUTTON_DPAD_RIGHT: (1, 0),
}
ARROWS = {(0, -1): pygame.K_UP, (0, 1): pygame.K_DOWN, (-1, 0): pygame.K_LEFT, (1, 0): pygame.K_RIGHT}
AXIS_LX, AXIS_LY = pygame.CONTROLLER_AXIS_LEFTX, pygame.CONTROLLER_AXIS_LEFTY
AXIS_RX, AXIS_RY = pygame.CONTROLLER_AXIS_RIGHTX, pygame.CONTROLLER_AXIS_RIGHTY
AXIS_RT = pygame.CONTROLLER_AXIS_TRIGGERRIGHT
CONTROLLER_EVENTS = (
    pygame.CONTROLLERBUTTONDOWN,
    pygame.CONTROLLERBUTTONUP,
    pygame.CONTROLLERAXISMOTION,
    pygame.CONTROLLERDEVICEADDED,
    pygame.CONTROLLERDEVICEREMOVED,
)


def _key_event(kind: int, key: int) -> pygame.event.Event:
    return pygame.event.Event(kind, key=key, mod=0, unicode="", scancode=0)


def apply_deadzone(x: float, y: float, deadzone: float = GAMEPAD_DEADZONE) -> pygame.Vector2:
    """Joystick -> vecteur de longueur 0..1 : rien sous la zone morte, puis une course qui repart de zéro (pas de saut)."""
    v = pygame.Vector2(x, y)
    length = v.length()
    if length < deadzone:
        return pygame.Vector2()
    return v.normalize() * min(1.0, (length - deadzone) / (1.0 - deadzone))


class SDLPad:
    """Une vraie manette (API « game controller » de SDL, qui uniformise les boutons d'une marque à l'autre)."""

    def __init__(self, device_index: int) -> None:
        from pygame._sdl2 import controller

        self._controller = controller.Controller(device_index)
        self.name = self._controller.name
        self.instance_id = self._controller.as_joystick().get_instance_id()

    def get_axis(self, axis: int) -> float:
        return self._controller.get_axis(axis) / 32768.0

    def get_button(self, button: int) -> bool:
        return bool(self._controller.get_button(button))

    def quit(self) -> None:
        self._controller.quit()


class Gamepad:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self.pads: dict[int, object] = {}
        self.last_device = bindings.KEYBOARD  # dernier périphérique utilisé : clavier / souris, ou manette
        self._facing = pygame.Vector2(1, 0)  # dernière direction visée, pour lancer un leurre sans toucher au joystick droit
        self._nav = {"x": 0, "y": 0}  # joystick gauche dans les menus : direction déjà annoncée

    # --- Branchement ---------------------------------------------------------
    def open_existing(self) -> None:
        try:
            from pygame._sdl2 import controller

            controller.init()
            for index in range(controller.get_count()):
                if controller.is_controller(index):
                    self.add(SDLPad(index))
        except (ImportError, pygame.error):
            pass  # pas de manette ou pas de gestion des manettes : le clavier suffit

    def add(self, pad) -> None:
        self.pads[pad.instance_id] = pad

    def remove(self, instance_id: int) -> None:
        pad = self.pads.pop(instance_id, None)
        if pad is not None and hasattr(pad, "quit"):
            pad.quit()
        if not self.pads and self.last_device == bindings.PAD:
            self.last_device = bindings.KEYBOARD

    @property
    def connected(self) -> bool:
        return bool(self.pads)

    @property
    def name(self) -> str:
        return next(iter(self.pads.values())).name if self.pads else ""

    # --- Lecture à chaque image ------------------------------------------------------------
    def _stick(self, ax: int, ay: int) -> pygame.Vector2:
        best = pygame.Vector2()
        if not self.enabled:
            return best
        for pad in self.pads.values():
            v = apply_deadzone(pad.get_axis(ax), pad.get_axis(ay))
            if v.length_squared() > best.length_squared():
                best = v
        return best

    def _held(self, *buttons: int) -> bool:
        return self.enabled and any(pad.get_button(b) for pad in self.pads.values() for b in buttons)

    def move(self) -> pygame.Vector2:
        """Joystick gauche, ou croix directionnelle (qui prime : elle est tout ou rien)."""
        pad_dir = pygame.Vector2()
        if self.enabled:
            for button, (dx, dy) in DPAD.items():
                if any(pad.get_button(button) for pad in self.pads.values()):
                    pad_dir += (dx, dy)
        if pad_dir.length_squared() > 0:
            return pad_dir.normalize()
        return self._stick(AXIS_LX, AXIS_LY)

    def aim(self) -> pygame.Vector2:
        """Joystick droit (nul au repos)."""
        return self._stick(AXIS_RX, AXIS_RY)

    def aim_direction(self) -> pygame.Vector2:
        """Où l'on vise : le joystick droit, sinon la dernière direction regardée (joystick gauche compris)."""
        for v in (self.aim(), self.move()):
            if v.length_squared() > 0:
                self._facing = v.normalize()
                break
        return pygame.Vector2(self._facing)

    def run(self) -> bool:
        if not self.enabled:
            return False
        trigger = any(pad.get_axis(AXIS_RT) > GAMEPAD_TRIGGER for pad in self.pads.values())
        return trigger or self._held(RIGHT_SHOULDER)

    def crouch(self) -> bool:
        return self._held(B, LEFT_STICK)

    def interact(self) -> bool:
        return self._held(A)

    # --- Événements ------------------------------------------------------------------------------
    def note_device(self, event: pygame.event.Event) -> None:
        """Retient le dernier périphérique utilisé (pour afficher « A » ou « E » dans les invites)."""
        if event.type == pygame.KEYDOWN:
            self.last_device = bindings.KEYBOARD
        elif event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN):
            self.last_device = bindings.KEYBOARD

    def process(self, event: pygame.event.Event, context: str = MENU) -> list[pygame.event.Event] | None:
        """Un événement de manette : renvoie les événements clavier équivalents (liste éventuellement vide).
        Renvoie None si ce n'est pas un événement de manette (l'appelant le traite alors normalement)."""
        if event.type not in CONTROLLER_EVENTS:
            return None
        if event.type == pygame.CONTROLLERDEVICEADDED:
            try:
                self.add(SDLPad(event.device_index))
            except (ImportError, pygame.error):
                pass
            return []
        if event.type == pygame.CONTROLLERDEVICEREMOVED:
            self.remove(event.instance_id)
            return []
        if not self.enabled:
            return []
        if event.type == pygame.CONTROLLERAXISMOTION:
            return self._axis_event(event, context)
        down = event.type == pygame.CONTROLLERBUTTONDOWN
        if down:
            self.last_device = bindings.PAD
        kind = pygame.KEYDOWN if down else pygame.KEYUP
        return [_key_event(kind, key) for key in self._keys_for_button(event.button, context)]

    def _keys_for_button(self, button: int, context: str) -> list[int]:
        if context == GAME:
            if button == A:
                return list(bindings.current.keys("interact")[:1])
            if button == X:
                return list(bindings.current.keys("throw")[:1])
            if button == LEFT_SHOULDER:
                return list(bindings.current.keys("disguise")[:1])
            if button == Y:
                return [RESTART_KEY]
            if button == START:
                return [pygame.K_ESCAPE]
            return []
        if button in DPAD:
            return [ARROWS[DPAD[button]]]
        if button in (A, START):
            return [pygame.K_RETURN]
        if button == B:
            return [pygame.K_ESCAPE]
        return []

    def _axis_event(self, event: pygame.event.Event, context: str) -> list[pygame.event.Event]:
        value = event.value / 32768.0
        if abs(value) > 0.5 and event.axis in (AXIS_LX, AXIS_LY, AXIS_RX, AXIS_RY, AXIS_RT):
            self.last_device = bindings.PAD
        if context != MENU or event.axis not in (AXIS_LX, AXIS_LY):
            return []
        name = "x" if event.axis == AXIS_LX else "y"
        state = self._nav[name]
        if state == 0 and abs(value) >= GAMEPAD_NAV_ON:
            state = 1 if value > 0 else -1
            self._nav[name] = state
            key = ARROWS[(state, 0)] if name == "x" else ARROWS[(0, state)]
            return [_key_event(pygame.KEYDOWN, key), _key_event(pygame.KEYUP, key)]
        if state != 0 and abs(value) <= GAMEPAD_NAV_OFF:
            self._nav[name] = 0  # le joystick est revenu au centre : il pourra annoncer une nouvelle direction
        return []


current = Gamepad()
