"""Carte de la campagne : on choisit une mission parmi celles débloquées, on voit les rangs obtenus et ceux à viser."""

from __future__ import annotations

import math

import pygame

from game.campaign import AVAILABLE, BEATEN, COMPLETED, HIDDEN, LOCKED, MAX_DANGER, OBTAINED, mission_status, rank_ladder
from game.core.scene import Scene
from game.progress import format_score, format_time
from game.scenes import navigation
from game.settings import COLORS, MENU_KEYS, SCREEN_SIZE
from game.ui.backdrop import Starfield
from game.ui.crawl import wrap_words
from game.ui.menu import MenuView

NODE_RADIUS = 38
NODE_SPACING = 240
PATH_Y = 235  # hauteur du chemin de la campagne
WAVE = 34  # ondulation verticale du chemin
SIDE_MARGIN = 130
PANEL = pygame.Rect(60, 372, 1160, 296)
MESSAGE_TIME = 2.6
PULSE_SPEED = 3.0  # rad/s : la couronne de la mission disponible pulse


def node_positions(count: int, width: int, selected: int, spacing: int = NODE_SPACING) -> list[tuple[int, int]]:
    """Position de chaque mission sur le chemin : centré s'il tient à l'écran, sinon on fait défiler pour garder la sélection au centre."""
    total = (count - 1) * spacing
    if total + 2 * SIDE_MARGIN <= width:
        left = (width - total) / 2
    else:
        left = max(width - SIDE_MARGIN - total, min(SIDE_MARGIN, width / 2 - selected * spacing))
    return [(round(left + i * spacing), round(PATH_Y + WAVE * math.sin(i * 1.4))) for i in range(count)]


def rank_color(letter: str) -> tuple[int, int, int]:
    return COLORS[f"rank_{letter}"]


class CampaignScene(Scene):
    def __init__(self, game, selected=None) -> None:
        super().__init__(game)
        self.campaign, self.progress = game.campaign, game.progress
        mission = selected or self.campaign.current(self.progress)
        self.index = self.campaign.index_of(mission)
        self.time = 0.0
        self.message, self.message_left = "", 0.0
        size = game.screen.get_size() if game.screen else SCREEN_SIZE
        self.size = size
        self.backdrop = Starfield(size)
        self.view = MenuView()
        self.font = pygame.font.Font(None, 28)
        self.big = pygame.font.Font(None, 54)
        self.letter_font = pygame.font.Font(None, 56)
        self.small = pygame.font.Font(None, 24)

    # --- État ------------------------------------------------------------------
    @property
    def mission(self):
        return self.campaign.missions[self.index]

    def status_of(self, mission) -> str:
        return mission_status(self.campaign, mission, self.progress)

    def move(self, direction: int) -> None:
        index = max(0, min(len(self.campaign.missions) - 1, self.index + direction))
        if index != self.index:
            self.index = index
            self.game.audio.play("ui_move")

    def activate(self) -> None:
        """Lance la mission choisie, ou explique pourquoi elle est verrouillée."""
        if self.status_of(self.mission) == LOCKED:
            previous = self.campaign.missions[self.index - 1]
            self.message, self.message_left = f"Terminez « {previous.title} » pour débloquer cette mission", MESSAGE_TIME
            self.game.audio.play("door_denied")
            return
        self.game.audio.play("ui_select")
        navigation.launch_mission(self.game, self.mission)

    # --- Cycle de vie ----------------------------------------------------------
    def on_enter(self) -> None:
        self.game.audio.start_music()
        self.game.audio.set_tension(0.0)

    # --- Entrées -----------------------------------------------------------------
    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key in MENU_KEYS["left"] + MENU_KEYS["up"]:
                self.move(-1)
            elif event.key in MENU_KEYS["right"] + MENU_KEYS["down"]:
                self.move(1)
            elif event.key in MENU_KEYS["confirm"]:
                self.activate()
            elif event.key in MENU_KEYS["back"]:
                self.game.audio.play("ui_back")
                self.game.scenes.pop()
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            hit = self._node_at(event.pos)
            if hit is not None:
                if hit == self.index:
                    self.activate()  # un second clic sur la mission choisie la lance
                else:
                    self.index = hit
                    self.game.audio.play("ui_move")

    def _node_at(self, pos) -> int | None:
        for i, (x, y) in enumerate(node_positions(len(self.campaign.missions), self.size[0], self.index)):
            if math.dist(pos, (x, y)) <= NODE_RADIUS + 6:
                return i
        return None

    # --- Boucle ----------------------------------------------------------------------
    def update(self, dt: float) -> None:
        self.time += dt
        self.message_left = max(0.0, self.message_left - dt)
        self.backdrop.update(dt)

    def draw(self, surface: pygame.Surface) -> None:
        self.backdrop.draw(surface)
        self.view.draw_title(surface, "CAMPAGNE", big=False, y=22)
        positions = node_positions(len(self.campaign.missions), self.size[0], self.index)
        self._draw_path(surface, positions)
        for i, (mission, pos) in enumerate(zip(self.campaign.missions, positions)):
            self._draw_node(surface, i, mission, pos)
        self._draw_panel(surface)
        self._draw_footer(surface)

    # --- Dessin ------------------------------------------------------------------------
    def _draw_path(self, surface: pygame.Surface, positions) -> None:
        for i in range(len(positions) - 1):
            unlocked = self.status_of(self.campaign.missions[i + 1]) != LOCKED
            a, b = pygame.Vector2(positions[i]), pygame.Vector2(positions[i + 1])
            if unlocked:
                pygame.draw.line(surface, COLORS["terminal_screen"], a, b, 3)
            else:  # pointillé : la suite n'est pas encore accessible
                steps = int(a.distance_to(b) // 14)
                for k in range(0, steps, 2):
                    p, q = a.lerp(b, k / steps), a.lerp(b, min(1.0, (k + 1) / steps))
                    pygame.draw.line(surface, COLORS["panel_border"], p, q, 2)

    def _draw_node(self, surface: pygame.Surface, index: int, mission, pos) -> None:
        status = self.status_of(mission)
        record = self.progress.record_of(mission.id)
        x, y = pos
        selected = index == self.index
        if status == COMPLETED:
            ring = rank_color(record.best_rank)
        elif status == AVAILABLE:
            pulse = 0.65 + 0.35 * math.sin(self.time * PULSE_SPEED)
            ring = tuple(round(c * pulse) for c in COLORS["terminal_screen"])
        else:
            ring = COLORS["panel_border"]
        pygame.draw.circle(surface, COLORS["shadow"], (x + 2, y + 4), NODE_RADIUS)
        pygame.draw.circle(surface, COLORS["panel"], (x, y), NODE_RADIUS)
        pygame.draw.circle(surface, ring, (x, y), NODE_RADIUS, 4)
        if status == COMPLETED:
            letter = self.letter_font.render(record.best_rank, True, ring)
            surface.blit(letter, letter.get_rect(center=(x, y)))
        elif status == AVAILABLE:
            number = self.letter_font.render(str(index + 1), True, COLORS["text"])
            surface.blit(number, number.get_rect(center=(x, y)))
        else:
            self._draw_padlock(surface, (x, y), ring)
        label = self.font.render(mission.title, True, COLORS["text"] if selected else COLORS["text_dim"])
        surface.blit(label, label.get_rect(midtop=(x, y + NODE_RADIUS + 12)))
        if selected:  # repère : quatre coins autour du nœud
            r = NODE_RADIUS + 12
            for sx in (-1, 1):
                for sy in (-1, 1):
                    corner = (x + sx * r, y + sy * r)
                    pygame.draw.line(surface, COLORS["text"], corner, (corner[0] - sx * 10, corner[1]), 2)
                    pygame.draw.line(surface, COLORS["text"], corner, (corner[0], corner[1] - sy * 10), 2)

    @staticmethod
    def _draw_padlock(surface: pygame.Surface, center, color) -> None:
        x, y = center
        pygame.draw.arc(surface, color, (x - 8, y - 17, 16, 20), 0, math.pi, 3)
        pygame.draw.line(surface, color, (x - 8, y - 8), (x - 8, y - 2), 3)
        pygame.draw.line(surface, color, (x + 8, y - 8), (x + 8, y - 2), 3)
        pygame.draw.rect(surface, color, (x - 12, y - 3, 24, 18), border_radius=3)
        pygame.draw.circle(surface, COLORS["panel"], (x, y + 5), 3)

    def _draw_panel(self, surface: pygame.Surface) -> None:
        mission, status = self.mission, self.status_of(self.mission)
        record = self.progress.record_of(mission.id)
        panel = pygame.Surface(PANEL.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, (*COLORS["panel"], 225), panel.get_rect(), border_radius=14)
        pygame.draw.rect(panel, (*COLORS["panel_border"], 255), panel.get_rect(), 1, border_radius=14)
        surface.blit(panel, PANEL)

        x, y = PANEL.x + 28, PANEL.y + 20
        for text, font, color in ((mission.episode, self.font, COLORS["crawl_yellow"]), (mission.title, self.big, COLORS["text"])):
            image = font.render(text, True, color)
            surface.blit(image, (x, y))
            y += image.get_height() + 2
        y += 8
        summary = mission.summary if status != LOCKED else "Mission verrouillée."
        measure = lambda s: self.font.size(s)[0]  # noqa: E731
        for words in wrap_words(summary, measure, 470):
            surface.blit(self.font.render(" ".join(words), True, COLORS["text_dim"]), (x, y))
            y += self.font.get_height() + 2
        self._draw_status(surface, (x, PANEL.bottom - 52), status)

        facts = [("Temps de référence", format_time(mission.par_time))]
        if record is not None:
            facts += [("Meilleur score", f"{format_score(record.best_score)} pts"), ("Meilleur temps", format_time(record.best_time)), ("Terminée", f"{record.completions} fois" if record.completions > 1 else "1 fois")]
        fx, fy = PANEL.x + 520, PANEL.y + 24
        self._draw_danger(surface, (fx, fy), mission.danger)
        fy += self.font.get_height() + 10
        for label, value in facts:
            surface.blit(self.small.render(label, True, COLORS["text_dim"]), (fx, fy))
            value_img = self.font.render(value, True, COLORS["text"])
            surface.blit(value_img, value_img.get_rect(topright=(fx + 270, fy - 2)))
            fy += self.font.get_height() + 10
        self._draw_ranks(surface, (PANEL.x + 840, PANEL.y + 18), rank_ladder(record, status))

    def _draw_danger(self, surface: pygame.Surface, pos, danger: int) -> None:
        """Niveau de menace : cinq pastilles, remplies jusqu'au niveau de la mission."""
        surface.blit(self.small.render("Menace", True, COLORS["text_dim"]), pos)
        for i in range(MAX_DANGER):
            center = (pos[0] + 270 - 14 - (MAX_DANGER - 1 - i) * 22, pos[1] + 9)
            filled = i < danger
            color = COLORS["status_alert"] if danger >= 4 else COLORS["status_suspect"] if danger >= 3 else COLORS["status_calm"]
            pygame.draw.circle(surface, color if filled else COLORS["panel_border"], center, 8 if filled else 6, 0 if filled else 2)

    def _draw_status(self, surface: pygame.Surface, pos, status: str) -> None:
        texts = {LOCKED: ("VERROUILLÉE", COLORS["text_dim"]), AVAILABLE: ("DISPONIBLE", COLORS["terminal_screen"])}
        record = self.progress.record_of(self.mission.id)
        text, color = texts.get(status) or (f"TERMINÉE, RANG {record.best_rank}", rank_color(record.best_rank))
        surface.blit(self.font.render(text, True, color), pos)

    def _draw_ranks(self, surface: pygame.Surface, pos, ladder) -> None:
        x, y = pos
        surface.blit(self.font.render("Rangs", True, COLORS["text_dim"]), (x, y))
        y += self.font.get_height() + 6
        for letter, name, minimum, state in ladder:
            color = rank_color(letter) if state != HIDDEN else COLORS["panel_border"]
            dim = state in (BEATEN, HIDDEN)
            circle = (x + 16, y + 14)
            if state == OBTAINED:
                pygame.draw.circle(surface, color, circle, 17)
                pygame.draw.circle(surface, COLORS["panel"], circle, 14)
            pygame.draw.circle(surface, color if not dim else COLORS["panel_border"], circle, 15, 2)
            image = self.font.render(letter, True, color if not dim else COLORS["panel_border"])
            surface.blit(image, image.get_rect(center=circle))
            surface.blit(self.font.render(name if state != HIDDEN else "???", True, COLORS["text"] if not dim else COLORS["text_dim"]), (x + 42, y + 4))
            detail = {OBTAINED: "obtenu", BEATEN: "dépassé", HIDDEN: ""}.get(state, "à viser")
            tag = f"dès {format_score(minimum)}" if state != HIDDEN else ""
            surface.blit(self.small.render(f"{tag}   {detail}".strip(), True, color if state == OBTAINED else COLORS["text_dim"]), (x + 190, y + 7))
            y += 34

    def _draw_footer(self, surface: pygame.Surface) -> None:
        text = "Gauche / Droite : choisir     Entrée : lancer     Échap : retour"
        image = self.font.render(text, True, COLORS["text_dim"])
        surface.blit(image, image.get_rect(midbottom=(surface.get_width() // 2, surface.get_height() - 12)))
        if self.message_left > 0:
            warning = self.font.render(self.message, True, COLORS["status_alert"])
            box = warning.get_rect(center=(surface.get_width() // 2, PANEL.y - 22)).inflate(30, 14)
            pygame.draw.rect(surface, COLORS["panel"], box, border_radius=10)
            pygame.draw.rect(surface, COLORS["status_alert"], box, 1, border_radius=10)
            surface.blit(warning, warning.get_rect(center=box.center))
