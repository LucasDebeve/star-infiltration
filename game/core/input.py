"""Lecture des entrées, transformée en un état simple (facile à simuler dans les tests)."""
from __future__ import annotations

from dataclasses import dataclass, field

import pygame

from game.core import bindings, gamepad, touch
from game.settings import GAMEPAD_AIM_RADIUS


@dataclass
class InputState:
    move: pygame.Vector2 = field(default_factory=pygame.Vector2)  # direction souhaitée
    run: bool = False
    crouch: bool = False
    interact: bool = False  # touche d'interaction maintenue (les appuis arrivent par KEYDOWN)
    aim_screen: tuple[int, int] = (0, 0)  # position de la souris à l'écran
    aim_active: bool = False  # la souris est dans la fenêtre : la caméra peut se pencher vers elle


def _is_down(pressed, action: str) -> bool:
    return any(pressed[key] for key in bindings.current.keys(action))


def read_input() -> InputState:
    """Clavier et souris, et manette si on s'en sert : le clavier prime tant qu'il bouge, la manette complète le reste."""
    pressed = pygame.key.get_pressed()
    move = pygame.Vector2(
        _is_down(pressed, "right") - _is_down(pressed, "left"),
        _is_down(pressed, "down") - _is_down(pressed, "up"),
    )
    if move.length_squared() > 0:
        move.normalize_ip()
    pad, finger = gamepad.current, touch.current
    if move.length_squared() == 0:
        move = pad.move()  # analogique : pousser doucement le joystick avance doucement
    if move.length_squared() == 0:
        move = finger.move()
    state = InputState(
        move=move,
        run=_is_down(pressed, "run") or pad.run() or finger.run(),
        crouch=_is_down(pressed, "crouch") or pad.crouch() or finger.crouch(),
        interact=_is_down(pressed, "interact") or pad.interact() or finger.interact(),
        aim_screen=pygame.mouse.get_pos(),
        aim_active=pygame.mouse.get_focused() and pad.last_device != bindings.PAD,
    )
    if pad.connected and pad.last_device == bindings.PAD:  # on vise avec le joystick droit, sinon dans le sens où l'on regarde
        surface = pygame.display.get_surface()
        if surface is not None:
            center = pygame.Vector2(surface.get_size()) / 2
            target = center + pad.aim_direction() * GAMEPAD_AIM_RADIUS
            state.aim_screen = (round(target.x), round(target.y))
            state.aim_active = pad.aim().length_squared() > 0  # la caméra ne se penche que si on vise vraiment
    return state
