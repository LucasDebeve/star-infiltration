"""Fenêtre et boucle principale."""
from __future__ import annotations

import pygame

from game.campaign import Campaign, load_campaign
from game.core import bindings, gamepad, touch
from game.core.audio import Audio
from game.core.events import EventBus
from game.core.preferences import Preferences
from game.core.scene import SceneManager
from game.progress import Progress
from game.settings import ASSETS_DIR, COLORS, FPS, MAX_DT, SCREEN_SIZE, TITLE


def _set_window_icon() -> None:
    """Icône de la fenêtre et de la barre des tâches (`assets/icon.png`) ; sans elle, le jeu garde l'icône par défaut."""
    try:
        pygame.display.set_icon(pygame.image.load(str(ASSETS_DIR / "icon.png")))
    except (pygame.error, FileNotFoundError):
        pass


class Game:
    def __init__(
        self,
        size: tuple[int, int] = SCREEN_SIZE,
        prefs: Preferences | None = None,
        progress: Progress | None = None,
        campaign: Campaign | None = None,
        dev=None,
    ) -> None:
        pygame.init()
        _set_window_icon()
        # SCALED : résolution logique fixe, la fenêtre peut être agrandie sans casser la caméra.
        self.screen = pygame.display.set_mode(size, pygame.SCALED | pygame.RESIZABLE)
        pygame.display.set_caption(TITLE)
        self.clock = pygame.time.Clock()
        self.events = EventBus()
        self.scenes = SceneManager()
        self.running = False
        self.prefs = prefs or Preferences.load()
        self.progress = progress or Progress.load()  # missions terminées et meilleurs scores
        self.campaign = campaign or load_campaign()
        self.dev = dev  # `DevTools` en mode développeur (`--dev`), sinon None : aucun outil de test
        self.audio = Audio(self.prefs)
        bindings.load(self.prefs.keys)  # touches remappées
        self.gamepad = gamepad.Gamepad(self.prefs.gamepad)
        gamepad.current = self.gamepad
        self.gamepad.open_existing()
        self._touch_font = pygame.font.Font(None, 22)
        self.fullscreen = False
        self.set_fullscreen(self.prefs.fullscreen)

    def set_fullscreen(self, wanted: bool) -> None:
        """Bascule le plein écran si besoin ; si le système refuse, on reste en fenêtre."""
        if wanted == self.fullscreen:
            return
        try:
            pygame.display.toggle_fullscreen()
        except pygame.error:
            return
        self.fullscreen = wanted

    def quit(self) -> None:
        self.running = False

    def step(self, dt: float) -> None:
        """Une image : événements, mise à jour, dessin. Séparée de `run` pour les tests."""
        scene = self.scenes.current
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.quit()
                continue
            translated = touch.current.process(event, self.screen.get_size())  # doigt : commandes tactiles
            if translated is None:
                translated = self.gamepad.process(event, scene.pad_context if scene else gamepad.MENU)
            if translated is None:  # clavier, souris, fenêtre
                self.gamepad.note_device(event)
                if scene:
                    scene.handle_event(event)
            elif scene:  # manette : ses appuis arrivent aux scènes sous forme de touches
                for key_event in translated:
                    scene.handle_event(key_event)
        bindings.device = self.gamepad.last_device
        self.audio.update(dt)
        if scene:
            scene.update(dt)
            self.screen.fill(COLORS["background"])
            scene.draw(self.screen)
            if scene.pad_context == gamepad.GAME:  # les commandes tactiles ne couvrent que la partie (les menus se touchent)
                touch.current.draw(self.screen, self._touch_font)
        pygame.display.flip()

    async def run_async(self) -> None:
        """Même boucle que `run`, mais qui rend la main au navigateur à chaque image (version web, voir `packaging/web/main.py`)."""
        import asyncio

        self.running = True
        while self.running and self.scenes.current:
            dt = min(self.clock.tick(FPS) / 1000, MAX_DT)
            self.step(dt)
            await asyncio.sleep(0)
        pygame.quit()

    def run(self) -> None:
        self.running = True
        while self.running and self.scenes.current:
            dt = min(self.clock.tick(FPS) / 1000, MAX_DT)
            self.step(dt)
        pygame.quit()
