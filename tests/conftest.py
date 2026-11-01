"""Les tests tournent sans fenêtre ni son (SDL « dummy »)."""

import os
import tempfile
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

# Les préférences du joueur ne doivent jamais être lues ni écrites par les tests : dossier temporaire dédié.
os.environ["STAR_INFILTRATION_HOME"] = tempfile.mkdtemp(prefix="star-infiltration-tests-")

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_preferences():
    """Chaque test repart de préférences par défaut : aucun réglage ne fuit d'un test à l'autre."""
    for leftover in Path(os.environ["STAR_INFILTRATION_HOME"]).glob("*"):
        leftover.unlink()
    yield


@pytest.fixture(autouse=True)
def _default_controls():
    """Touches par défaut et pas de manette au départ de chaque test (ces réglages sont partagés par tout le programme)."""
    from game.core import bindings, gamepad, touch

    touch.current = touch.TouchControls()
    bindings.load({})
    bindings.device = bindings.KEYBOARD
    gamepad.current = gamepad.Gamepad()
    yield


@pytest.fixture
def game():
    """Un jeu complet (fenêtre factice, audio factice, préférences et progression vierges)."""
    import pygame

    from game.core.game import Game

    g = Game()
    pygame.event.clear()  # le pilote vidéo factice envoie des « perte de focus » au démarrage, qui mettraient en pause
    yield g
    pygame.quit()
