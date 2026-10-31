"""Générique défilant « en perspective » : mise en page du texte, rendu penché, déroulé par phases, maintien pour passer.

Principe du rendu : le texte est dessiné à plat sur une grande image jaune ; à l'écran, chaque rangée de pixels
prend la rangée de texte que la perspective y projette, et la largeur diminue vers l'horizon (le texte s'éloigne).
Les calculs (mise en page, projection, déroulé) sont purs et testés sans fenêtre.
"""
from __future__ import annotations

import math
from typing import Callable, Sequence

import pygame

from game.settings import (
    COLORS,
    CRAWL_END_PAUSE,
    CRAWL_LOGO_TIME,
    CRAWL_PROLOGUE_TIME,
    CRAWL_SKIP_HOLD,
    CRAWL_SKIP_KEYS,
    CRAWL_STOP_SCALE,
)

TEXT_WIDTH = 760  # largeur du texte à plat, en pixels (c'est aussi sa largeur à l'écran en bas de l'écran)
HORIZON = 40  # ordonnée écran de la ligne de fuite
FOCAL = 520.0  # force de la perspective : plus petit, plus le texte du bas est étiré et celui du haut écrasé
T_MIN = 0.2  # échelle sous laquelle le texte n'est plus dessiné (il a disparu dans le lointain)
FADE_ROWS = 150  # hauteur (en rangées) du fondu vers l'horizon
PARAGRAPH_GAP = 1.1  # espace entre paragraphes, en hauteurs de ligne
LINE_SPACING = 1.5  # interligne du texte courant, en hauteurs de police
PROLOGUE_FADE = 1.2  # fondus d'entrée et de sortie de la phrase d'accroche
LOGO_START_SCALE = 2.2  # taille de départ du titre qui s'éloigne (1 = taille normale)


# --- Mise en page du texte (pur) -----------------------------------------------------------
Measure = Callable[[str], int]


def wrap_words(text: str, measure: Measure, max_width: int) -> list[list[str]]:
    """Coupe `text` en lignes de mots, chacune de largeur au plus `max_width` (un mot trop long reste seul)."""
    lines: list[list[str]] = []
    line: list[str] = []
    for word in text.split():
        candidate = [*line, word]
        if line and measure(" ".join(candidate)) > max_width:
            lines.append(line)
            line = [word]
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines


def justify_positions(words: Sequence[str], measure: Measure, width: int, justify: bool) -> list[tuple[str, int]]:
    """Abscisse de chaque mot. Justifié : l'espace restant est réparti entre les mots, pour un bloc aux bords nets."""
    if len(words) <= 1 or not justify:
        x, out = 0, []
        for word in words:
            out.append((word, x))
            x += measure(word + " ")
        return out
    gap = (width - sum(measure(w) for w in words)) / (len(words) - 1)
    x, out = 0.0, []
    for word in words:
        out.append((word, round(x)))
        x += measure(word) + gap
    return out


def render_crawl_text(episode: str, title: str, paragraphs: Sequence[str], fonts: dict[str, pygame.font.Font], width: int = TEXT_WIDTH) -> pygame.Surface:
    """Texte à plat sur fond transparent : épisode et titre centrés, puis les paragraphes justifiés."""
    yellow = COLORS["crawl_yellow"]
    body = fonts["body"]
    measure = lambda s: body.size(s)[0]  # noqa: E731
    line_h = round(body.get_height() * LINE_SPACING)
    blocks: list[tuple[str, object, int]] = [("center", fonts["episode"].render(episode, True, yellow), 0), ("center", fonts["title"].render(title.upper(), True, yellow), round(line_h * 0.9))]
    for paragraph in paragraphs:
        lines = wrap_words(paragraph, measure, width)
        for i, words in enumerate(lines):
            blocks.append(("line", (words, i == len(lines) - 1), 0 if i else round(line_h * PARAGRAPH_GAP)))
    height = sum(
        (item.get_height() if kind == "center" else line_h) + gap for kind, item, gap in blocks
    ) + line_h
    surf = pygame.Surface((width, height), pygame.SRCALPHA)
    y = 0
    for kind, item, gap in blocks:
        y += gap
        if kind == "center":
            surf.blit(item, item.get_rect(midtop=(width // 2, y)))
            y += item.get_height()
        else:
            words, last = item
            for word, x in justify_positions(words, measure, width, justify=not last):
                surf.blit(body.render(word, True, yellow), (x, y))
            y += line_h
    return surf


# --- Projection en perspective (pur) ---------------------------------------------------------
def plane_distance(t: float) -> float:
    """Distance (sur le plan du texte) projetée à l'échelle t (1 = bas de l'écran, 0 = horizon)."""
    return FOCAL * (1.0 / t - 1.0)


def scroll_distance(text_height: int) -> float:
    """Distance à faire défiler : le texte s'arrête quand sa dernière ligne s'est éloignée à l'échelle `CRAWL_STOP_SCALE`.

    On n'attend pas qu'elle ait disparu à l'horizon (ni la fin de la musique) : l'introduction resterait trop longue.
    """
    return text_height + plane_distance(CRAWL_STOP_SCALE)


class PerspectiveCrawl:
    """Dessine le texte à plat penché vers l'horizon, avec un fondu dans le lointain."""

    def __init__(self, size: tuple[int, int]) -> None:
        self.size = size
        width, height = size
        bottom = height
        self.rows: list[tuple[int, float, int]] = []  # (y, distance sur le plan, largeur à l'écran), de l'horizon vers le bas
        first = math.ceil(HORIZON + T_MIN * (bottom - HORIZON))
        self.top = first
        for y in range(first, bottom):
            t = (y - HORIZON) / (bottom - HORIZON)
            self.rows.append((y, plane_distance(t), max(1, round(TEXT_WIDTH * t))))
        self._layer = pygame.Surface((TEXT_WIDTH, bottom - first), pygame.SRCALPHA)
        self._fade = pygame.Surface(self._layer.get_size(), pygame.SRCALPHA)
        for y in range(self._fade.get_height()):  # opaque en bas, transparent près de l'horizon
            level = round(255 * min(1.0, y / FADE_ROWS))
            pygame.draw.line(self._fade, (255, 255, 255, level), (0, y), (TEXT_WIDTH, y))

    def draw(self, surface: pygame.Surface, text: pygame.Surface, scroll: float) -> None:
        """`scroll` : distance parcourue sur le plan (0 : la première ligne vient d'apparaître en bas)."""
        layer, text_h = self._layer, text.get_height()
        layer.fill((0, 0, 0, 0))
        for y, p, width in self.rows:
            src = scroll - p
            if 0 <= src < text_h:
                row = pygame.transform.scale(text.subsurface((0, int(src), TEXT_WIDTH, 1)), (width, 1))
                layer.blit(row, ((TEXT_WIDTH - width) // 2, y - self.top))
        layer.blit(self._fade, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(layer, ((self.size[0] - TEXT_WIDTH) // 2, self.top))


# --- Déroulé par phases (pur) -------------------------------------------------------------------
PROLOGUE, LOGO, CRAWL, END, DONE = "prologue", "logo", "crawl", "end", "done"


class CrawlTimeline:
    """Phrase d'accroche (facultative) -> titre qui s'éloigne -> texte qui défile -> courte pause -> fin."""

    def __init__(self, distance: float, speed: float, has_prologue: bool) -> None:
        self.distance, self.speed = distance, speed
        self.phase = PROLOGUE if has_prologue else LOGO
        self.time = 0.0  # temps écoulé dans la phase
        self.elapsed = 0.0

    @property
    def scroll(self) -> float:
        return min(self.distance, self.time * self.speed) if self.phase == CRAWL else (self.distance if self.phase in (END, DONE) else 0.0)

    @property
    def done(self) -> bool:
        return self.phase == DONE

    @property
    def phase_progress(self) -> float:
        """Avancement (0..1) de la phase en cours, pour les fondus (nul pour le texte, qui a sa propre mesure)."""
        length = {PROLOGUE: CRAWL_PROLOGUE_TIME, LOGO: CRAWL_LOGO_TIME, END: CRAWL_END_PAUSE}.get(self.phase)
        return min(1.0, self.time / length) if length else 0.0

    def update(self, dt: float) -> None:
        if self.done:
            return
        self.time += dt
        self.elapsed += dt
        lengths = {PROLOGUE: CRAWL_PROLOGUE_TIME, LOGO: CRAWL_LOGO_TIME, CRAWL: self.distance / self.speed, END: CRAWL_END_PAUSE}
        following = {PROLOGUE: LOGO, LOGO: CRAWL, CRAWL: END, END: DONE}
        while not self.done and self.time >= lengths[self.phase]:
            self.time -= lengths[self.phase]
            self.phase = following[self.phase]

    def skip(self) -> None:
        self.phase = DONE


class HoldToSkip:
    """Passer l'introduction en maintenant l'une des touches `keys` pendant `hold` secondes."""

    def __init__(self, keys: Sequence[int] = CRAWL_SKIP_KEYS, hold: float = CRAWL_SKIP_HOLD) -> None:
        self.keys, self.hold = tuple(keys), hold
        self._down: set[int] = set()
        self.held = 0.0

    def press(self, key: int) -> None:
        if key in self.keys:
            self._down.add(key)

    def release(self, key: int) -> None:
        self._down.discard(key)

    @property
    def active(self) -> bool:
        return bool(self._down)

    @property
    def progress(self) -> float:
        return min(1.0, self.held / self.hold)

    def update(self, dt: float) -> bool:
        """Vrai quand la touche a été maintenue assez longtemps. Relâcher remet la jauge à zéro."""
        self.held = self.held + dt if self._down else 0.0
        return self.held >= self.hold


# --- Titre et accroche ------------------------------------------------------------------------------
def draw_logo(surface: pygame.Surface, logo: pygame.Surface, progress: float) -> None:
    """Le titre commence grand et s'éloigne jusqu'à disparaître au centre de l'écran."""
    eased = progress ** 0.8
    scale = LOGO_START_SCALE * (1.0 - eased)
    if scale < 0.02:
        return
    size = (max(1, round(logo.get_width() * scale)), max(1, round(logo.get_height() * scale)))
    image = pygame.transform.smoothscale(logo, size)
    image.set_alpha(round(255 * min(1.0, (1.0 - progress) * 3.0)))  # il s'efface en toute fin de course
    surface.blit(image, image.get_rect(center=(surface.get_width() // 2, surface.get_height() // 2 - 20)))


def draw_prologue(surface: pygame.Surface, text: pygame.Surface, progress: float, length: float) -> None:
    """Phrase d'accroche bleue : fondu d'entrée, maintien, fondu de sortie."""
    t = progress * length
    alpha = min(1.0, t / PROLOGUE_FADE, (length - t) / PROLOGUE_FADE)
    if alpha > 0:
        text.set_alpha(round(255 * alpha))
        surface.blit(text, text.get_rect(center=surface.get_rect().center))
