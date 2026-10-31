"""Terminal : un menu d'opérations (télécharger des données, désactiver des caméras, couper la lumière d'une salle)."""
from __future__ import annotations

import math
from dataclasses import dataclass

import pygame

from game.entities.entity import Entity
from game.settings import COLORS, TERMINAL_JOB_TIME, TERMINAL_LINK_RANGE, TERMINAL_REACH
from game.systems.interaction import InteractionContext, Prompt
from game.terminals import DATA, TerminalSpec

SIZE = 24
BLINK_SPEED = 5.0  # rad/s


@dataclass
class TerminalJob:
    """Une opération en cours : le joueur doit rester près du terminal le temps de la connexion."""

    action: str  # `terminals.DATA`, `CAMERAS` ou `LIGHTS`
    duration: float
    elapsed: float = 0.0

    @property
    def progress(self) -> float:
        return min(1.0, self.elapsed / self.duration)


class Terminal(Entity):
    """Un terminal ouvre un menu (le jeu est en pause) : on y choisit parmi ce que la carte lui a permis de faire."""

    reach = TERMINAL_REACH
    hold_time = 0.0  # un simple appui ouvre le menu

    def __init__(self, x: float, y: float, spec: TerminalSpec | None = None) -> None:
        super().__init__(x, y, SIZE, SIZE)
        self.spec = spec or TerminalSpec((0, 0))
        self.hacked = False  # les données ont été téléchargées
        self.job: TerminalJob | None = None
        self._age = 0.0

    @property
    def capabilities(self) -> tuple[str, ...]:
        return self.spec.capabilities

    @property
    def tile(self) -> tuple[int, int]:
        return self.spec.tile

    @property
    def anchor(self) -> pygame.Vector2:
        return self.pos

    def distance_to(self, point: pygame.Vector2) -> float:
        return self.pos.distance_to(point)

    def prompt(self, inventory) -> Prompt | None:
        if self.job is not None:
            return None  # une connexion est en cours
        if self.capabilities == (DATA,) and self.hacked:
            return None  # un terminal de données dont on a tout pris n'a plus rien à offrir
        return Prompt("Utiliser le terminal")

    def interact(self, ctx: InteractionContext) -> None:
        ctx.events.emit("terminal_opened", terminal=self)

    # --- Connexion -----------------------------------------------------------------
    def start(self, action: str) -> None:
        self.job = TerminalJob(action, TERMINAL_JOB_TIME[action])

    def advance(self, dt: float, player_pos: pygame.Vector2) -> str | None:
        """Fait avancer la connexion. Renvoie l'action qui vient de s'achever, 'lost' si le joueur s'est trop éloigné, sinon None."""
        if self.job is None:
            return None
        if self.pos.distance_to(player_pos) > TERMINAL_LINK_RANGE:
            self.job = None
            return "lost"
        self.job.elapsed += dt
        if self.job.progress >= 1.0:
            action, self.job = self.job.action, None
            return action
        return None

    @property
    def screen_color(self) -> tuple[int, int, int]:
        return COLORS["terminal_done" if self.hacked else "terminal_screen" if DATA in self.capabilities else "console_live"]

    def update(self, dt: float, tilemap=None) -> None:
        self._age += dt

    def draw(self, surface: pygame.Surface, camera, progress: float = 0.0) -> None:
        body = pygame.Rect(0, 0, self.width, self.height)
        body.center = camera.world_to_screen(self.pos)
        screen_color = self.screen_color
        pygame.draw.rect(surface, COLORS["shadow"], body.move(2, 3), border_radius=4)
        pygame.draw.rect(surface, COLORS["terminal_body"], body, border_radius=4)
        pygame.draw.rect(surface, COLORS["player_outline"], body, 2, border_radius=4)

        screen = body.inflate(-8, -12)
        screen.y -= 2
        pygame.draw.rect(surface, tuple(c * 0.25 for c in screen_color), screen, border_radius=2)
        if self.hacked and self.capabilities == (DATA,):  # coche (un terminal qui sait faire autre chose reste en service)
            a, b, c = (screen.x + 3, screen.centery), (screen.centerx - 1, screen.bottom - 3), (screen.right - 3, screen.y + 3)
            pygame.draw.lines(surface, screen_color, False, [a, b, c], 2)
            return
        if self.job is not None:
            progress = self.job.progress
        if progress > 0:  # barre de téléchargement sur l'écran
            bar = pygame.Rect(screen.x + 2, screen.centery - 2, round((screen.w - 4) * progress), 4)
            pygame.draw.rect(surface, screen_color, bar)
        else:  # lignes de code qui clignotent
            blink = 0.5 + 0.5 * math.sin(self._age * BLINK_SPEED)
            for i in range(3):
                width = screen.w - 6 - (i % 2) * 6
                color = tuple(round(c * (0.5 + 0.5 * blink if i == 1 else 0.7)) for c in screen_color)
                pygame.draw.line(surface, color, (screen.x + 3, screen.y + 4 + i * 4), (screen.x + 3 + width, screen.y + 4 + i * 4), 1)
        pygame.draw.rect(surface, screen_color, screen, 1, border_radius=2)
