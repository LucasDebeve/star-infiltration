"""Scènes et gestionnaire de scènes (pile)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from game.core.game import Game


class Scene:
    """Classe de base d'un écran de jeu. Surcharger les méthodes utiles."""

    pad_context = "menu"  # comment la manette est traduite : "menu" (navigation) ou "game" (actions de jeu), voir `gamepad.py`

    def __init__(self, game: Game) -> None:
        self.game = game

    def on_enter(self) -> None:
        """Appelée quand la scène devient active."""

    def on_exit(self) -> None:
        """Appelée quand la scène est retirée."""

    def on_resume(self) -> None:
        """Appelée quand la scène du dessus est retirée et que celle-ci redevient active (fin d'une pause)."""

    def handle_event(self, event: pygame.event.Event) -> None:
        """Un événement pygame (clavier, souris, fenêtre...)."""

    def update(self, dt: float) -> None:
        """Logique du jeu ; `dt` en secondes."""

    def draw(self, surface: pygame.Surface) -> None:
        """Dessin de la scène sur `surface`."""


class SceneManager:
    """Pile de scènes : seule la scène du dessus est mise à jour et dessinée."""

    def __init__(self) -> None:
        self._stack: list[Scene] = []

    @property
    def current(self) -> Scene | None:
        return self._stack[-1] if self._stack else None

    def push(self, scene: Scene) -> None:
        self._stack.append(scene)
        scene.on_enter()

    def pop(self) -> Scene | None:
        if not self._stack:
            return None
        scene = self._stack.pop()
        scene.on_exit()
        if self._stack:
            self._stack[-1].on_resume()
        return scene

    def clear(self) -> None:
        """Retire toutes les scènes, de la plus haute à la plus basse (chacune est prévenue)."""
        while self._stack:
            self._stack.pop().on_exit()

    def replace(self, scene: Scene) -> None:
        """Remplace la scène du dessus sans réveiller celle du dessous."""
        if self._stack:
            self._stack.pop().on_exit()
        self.push(scene)
