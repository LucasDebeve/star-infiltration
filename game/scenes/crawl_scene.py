"""Générique de mission : texte défilant en perspective sur les étoiles, avec la musique du générique.

Phrase d'accroche bleue (si la mission en a une) -> titre qui s'éloigne -> texte qui défile -> la mission commence.
On peut passer l'introduction en maintenant Espace, Entrée ou Échap une seconde.
"""

from __future__ import annotations

import pygame

from game.core.scene import Scene
from game.scenes import navigation
from game.settings import COLORS, CRAWL_PROLOGUE_TIME, CRAWL_SPEED, CRAWL_THEME, SCREEN_SIZE, TITLE
from game.ui.backdrop import Starfield
from game.ui.crawl import (
    CRAWL,
    END,
    LOGO,
    PROLOGUE,
    CrawlTimeline,
    HoldToSkip,
    PerspectiveCrawl,
    draw_logo,
    draw_prologue,
    render_crawl_text,
    scroll_distance,
)

MUSIC_FADE_MS = 1500  # fondu de la musique quand le générique s'arrête : il se termine avant elle
HINT = "Maintenez Espace, Entrée ou Échap pour passer l'introduction"
HINT_MARGIN = 36
HINT_BAR = (260, 5)


class CrawlScene(Scene):
    def __init__(self, game, mission) -> None:
        super().__init__(game)
        self.mission = mission
        size = game.screen.get_size() if game.screen else SCREEN_SIZE
        fonts = {
            "body": pygame.font.Font(None, 40),
            "episode": pygame.font.Font(None, 46),
            "title": pygame.font.Font(None, 62),
        }
        self.text = render_crawl_text(mission.episode, mission.title, mission.intro, fonts)
        self.perspective = PerspectiveCrawl(size)
        self.backdrop = Starfield(size, seed=21, ship=False)
        distance = scroll_distance(self.text.get_height())
        self.timeline = CrawlTimeline(distance, CRAWL_SPEED, mission.prologue is not None)
        self.skip = HoldToSkip()
        self._small = pygame.font.Font(None, 24)
        self._logo = self._render_logo()
        self._prologue = fonts["body"].render(mission.prologue, True, COLORS["crawl_blue"]) if mission.prologue else None
        self._theme_started = False
        self._finished = False

    @staticmethod
    def _render_logo() -> pygame.Surface:
        font = pygame.font.Font(None, 150)
        text = TITLE.upper()
        outline = font.render(text, True, COLORS["player_outline"])
        face = font.render(text, True, COLORS["crawl_yellow"])
        logo = pygame.Surface((face.get_width() + 8, face.get_height() + 8), pygame.SRCALPHA)
        for dx, dy in ((0, 4), (8, 4), (4, 0), (4, 8)):
            logo.blit(outline, (dx, dy))
        logo.blit(face, (4, 4))
        return logo

    # --- Cycle de vie --------------------------------------------------------
    def on_enter(self) -> None:
        self.game.audio.set_music_muted(True)  # le générique a sa propre musique
        self.game.audio.set_tension(0.0)

    def on_exit(self) -> None:
        self.game.audio.stop_theme(MUSIC_FADE_MS)
        self.game.audio.set_music_muted(False)

    # --- Entrées ---------------------------------------------------------------
    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            self.skip.press(event.key)
        elif event.type == pygame.KEYUP:
            self.skip.release(event.key)

    # --- Boucle ------------------------------------------------------------------
    def update(self, dt: float) -> None:
        self.backdrop.update(dt)
        if not self._theme_started and self.timeline.phase in (LOGO, CRAWL):  # la musique démarre avec le titre
            self._theme_started = True
            self.game.audio.play_theme(CRAWL_THEME)
        self.timeline.update(dt)
        if self.skip.update(dt):
            self.timeline.skip()
        if self.timeline.done and not self._finished:
            self._finished = True
            navigation.start_play(self.game, self.mission)

    def draw(self, surface: pygame.Surface) -> None:
        self.backdrop.draw(surface)
        phase = self.timeline.phase
        if phase == PROLOGUE and self._prologue is not None:
            draw_prologue(surface, self._prologue, self.timeline.phase_progress, CRAWL_PROLOGUE_TIME)
        elif phase == LOGO:
            draw_logo(surface, self._logo, self.timeline.phase_progress)
        elif phase in (CRAWL, END):
            self.perspective.draw(surface, self.text, self.timeline.scroll)
        self._draw_hint(surface)

    def _draw_hint(self, surface: pygame.Surface) -> None:
        text = self._small.render(HINT, True, COLORS["text_dim"])
        rect = text.get_rect(midbottom=(surface.get_width() // 2, surface.get_height() - HINT_MARGIN))
        surface.blit(text, rect)
        if self.skip.active:  # jauge de maintien
            bar = pygame.Rect(0, 0, *HINT_BAR)
            bar.midtop = (rect.centerx, rect.bottom + 6)
            pygame.draw.rect(surface, COLORS["panel"], bar, border_radius=3)
            fill = bar.copy()
            fill.w = max(2, round(bar.w * self.skip.progress))
            pygame.draw.rect(surface, COLORS["crawl_yellow"], fill, border_radius=3)
            pygame.draw.rect(surface, COLORS["panel_border"], bar, 1, border_radius=3)
