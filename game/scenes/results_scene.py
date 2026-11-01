"""Écran de fin de mission : temps, alertes déclenchées, leurres utilisés, score et rang obtenu."""

from __future__ import annotations

import pygame

from game.progress import MissionResult, RecordUpdate, format_score, format_time, rank_name
from game.scenes import navigation
from game.scenes.campaign_scene import rank_color
from game.scenes.menu_base import MenuScene
from game.settings import COLORS
from game.ui.backdrop import SnapshotBackdrop
from game.ui.menu import Button, Menu

REVEAL_STEP = 0.45  # secondes entre l'apparition de deux lignes de statistiques
RANK_DELAY = 0.5  # secondes entre la dernière ligne et l'arrivée du rang
RANK_GROW = 0.35  # durée de l'apparition du rang (il grossit)
PANEL_WIDTH = 760
PANEL_TOP = 150
PANEL_HEIGHT = 280


class ResultsScene(MenuScene):
    title = "MISSION ACCOMPLIE"
    top = 452

    def __init__(self, game, play_scene, mission, result: MissionResult, update: RecordUpdate) -> None:
        self.play_scene, self.mission, self.result, self.update_info = play_scene, mission, result, update
        self.time = 0.0
        self._rank_sound = False
        super().__init__(game, SnapshotBackdrop(game.screen))  # la dernière image du jeu, floutée, derrière les résultats
        self.subtitle = f"{mission.episode} : {mission.title}"
        self.font = pygame.font.Font(None, 34)
        self.small = pygame.font.Font(None, 24)
        self.score_font = pygame.font.Font(None, 56)
        self.rank_font = pygame.font.Font(None, 190)

    # --- Menu ---------------------------------------------------------------------
    def build_menu(self) -> Menu:
        items = []
        following = self.game.campaign.next_after(self.mission)
        if following is not None:
            items.append(Button("Mission suivante", lambda: navigation.next_mission(self.game, following)))
        items += [
            Button("Rejouer la mission", self._replay),
            Button("Carte de la campagne", lambda: navigation.open_campaign(self.game, self.mission)),
            Button("Menu principal", lambda: navigation.open_main_menu(self.game)),
        ]
        return Menu(items, on_sound=self.sound, on_back=lambda: navigation.open_campaign(self.game, self.mission))

    def _replay(self) -> None:
        self.game.scenes.pop()  # retire les résultats : on revient à la partie, qui recommence (sans le générique)
        self.play_scene.restart()

    # --- Contenu ----------------------------------------------------------------------
    def rows(self) -> list[tuple[str, str, int]]:
        """(libellé, valeur, points) de chaque ligne de statistiques."""
        stats, r = self.result.stats, self.result
        return [
            ("Temps", f"{format_time(stats.time)}   (réf. {format_time(self.mission.par_time)})", r.time_points),
            ("Alertes déclenchées", str(stats.alerts), r.alert_points),
            ("Leurres utilisés", str(stats.decoys), r.decoy_points),
        ]

    def badges(self) -> list[str]:
        """Les distinctions de cette partie."""
        u = self.update_info
        if u.first_completion:
            return ["PREMIÈRE RÉUSSITE"]
        badges = []
        if u.rank_improved:
            badges.append("NOUVEAU RANG")
        if u.new_best_score:
            badges.append("NOUVEAU RECORD")
        if u.new_best_time:
            badges.append("MEILLEUR TEMPS")
        return badges

    # --- Boucle -------------------------------------------------------------------------
    def update(self, dt: float) -> None:
        super().update(dt)
        self.time += dt
        if not self._rank_sound and self.time >= self._rank_time:
            self._rank_sound = True
            self.game.audio.play("hack_done")

    @property
    def _rank_time(self) -> float:
        return REVEAL_STEP * (len(self.rows()) + 1) + RANK_DELAY

    def draw_extra(self, surface: pygame.Surface) -> None:
        panel = pygame.Rect((surface.get_width() - PANEL_WIDTH) // 2, PANEL_TOP, PANEL_WIDTH, PANEL_HEIGHT)
        backing = pygame.Surface(panel.size, pygame.SRCALPHA)
        pygame.draw.rect(backing, (*COLORS["panel"], 215), backing.get_rect(), border_radius=14)
        pygame.draw.rect(backing, (*COLORS["panel_border"], 255), backing.get_rect(), 1, border_radius=14)
        surface.blit(backing, panel)

        x, y = panel.x + 30, panel.y + 26
        for i, (label, value, points) in enumerate(self.rows()):
            alpha = max(0.0, min(1.0, (self.time - i * REVEAL_STEP) / REVEAL_STEP))
            if alpha <= 0:
                break
            self._stat_row(surface, (x, y), label, value, points, alpha)
            y += 58
        total_alpha = max(0.0, min(1.0, (self.time - len(self.rows()) * REVEAL_STEP) / REVEAL_STEP))
        if total_alpha > 0:
            line = pygame.Rect(x, y - 6, 410, 2)
            pygame.draw.rect(surface, COLORS["panel_border"], line)
            self._blit_alpha(surface, self.font.render("Score", True, COLORS["text_dim"]), (x, y + 8), total_alpha)
            score = self.score_font.render(f"{format_score(self.result.score)}", True, COLORS["text"])
            self._blit_alpha(surface, score, (x + 410 - score.get_width(), y), total_alpha)
        self._draw_rank(surface, panel)

    def _stat_row(self, surface, pos, label: str, value: str, points: int, alpha: float) -> None:
        x, y = pos
        self._blit_alpha(surface, self.font.render(label, True, COLORS["text_dim"]), (x, y), alpha)
        value_img = self.font.render(value, True, COLORS["text"])
        self._blit_alpha(surface, value_img, (x + 410 - value_img.get_width() - 90, y), alpha)
        gained = self.font.render(f"+{points}", True, COLORS["status_calm"] if points else COLORS["text_dim"])
        self._blit_alpha(surface, gained, (x + 410 - gained.get_width(), y), alpha)

    @staticmethod
    def _blit_alpha(surface: pygame.Surface, image: pygame.Surface, pos, alpha: float) -> None:
        image.set_alpha(round(255 * alpha))
        surface.blit(image, pos)

    def _draw_rank(self, surface: pygame.Surface, panel: pygame.Rect) -> None:
        progress = max(0.0, min(1.0, (self.time - self._rank_time) / RANK_GROW))
        center = (panel.right - 150, panel.y + 120)
        letter = self.result.rank
        color = rank_color(letter)
        if progress > 0:
            image = self.rank_font.render(letter, True, color)
            scale = 0.4 + 0.6 * progress + 0.18 * (1 - abs(2 * progress - 1))  # il grossit, avec un petit dépassement
            image = pygame.transform.smoothscale(image, (max(1, round(image.get_width() * scale)), max(1, round(image.get_height() * scale))))
            image.set_alpha(round(255 * progress))
            pygame.draw.circle(surface, color, center, round(96 * scale), 3)
            surface.blit(image, image.get_rect(center=center))
            name = self.font.render(rank_name(letter).upper(), True, color)
            surface.blit(name, name.get_rect(midtop=(center[0], center[1] + 104)))
        if progress >= 1.0:
            for i, badge in enumerate(self.badges()):
                chip = self.small.render(badge, True, COLORS["panel"])
                box = chip.get_rect(midtop=(center[0], center[1] + 140 + i * 30)).inflate(20, 8)
                pygame.draw.rect(surface, COLORS["crawl_yellow"], box, border_radius=8)
                surface.blit(chip, chip.get_rect(center=box.center))
