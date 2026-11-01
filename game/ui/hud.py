"""HUD : posture, alerte, objectif, inventaire, invite d'interaction, messages, aide, debug."""

from __future__ import annotations

import math

import pygame

from game.ai.guard import GuardState
from game.core import bindings
from game.entities.player import Player, Stance
from game.items import Inventory
from game.settings import COLORS, LOCKDOWN_WARNING_TIME, TOAST_DURATION
from game.systems.interaction import Prompt
from game.ui.icons import draw_item_icon, item_color

STANCE_LABELS = {Stance.CROUCH: "Accroupi", Stance.WALK: "Marche", Stance.RUN: "Course"}


def help_lines() -> tuple[str, str]:
    """Rappel des commandes (écran de pause), avec les touches ou boutons réellement utilisés."""
    label = bindings.label
    return (
        f"{label('move')} : se déplacer     {label('run')} : courir (bruyant)     {label('crouch')} : s'accroupir (silencieux)",
        f"{label('interact')} : interagir (maintenir pour pirater)     {label('throw')} : lancer un leurre     {label('pause')} : pause     {label('restart')} : recommencer (fin de mission)",
    )


VISIBILITY_LABELS = {  # zone d'éclairement -> (libellé, clé de couleur) : dans l'ombre on est moins repérable
    "shadow": ("dans l'ombre", "status_calm"),
    "dim": ("pénombre", "text_dim"),
    "lit": ("en pleine lumière", "status_suspect"),
}
DISGUISE_LABELS = {  # état du déguisement -> (libellé, clé de couleur)
    "worn": ("Uniforme : porté (on vous prend pour un officier)", "status_calm"),
    "blown": ("Couverture grillée", "status_alert"),
    "stowed": ("Uniforme : dans le sac", "text_dim"),
}
# Niveau de menace (GuardState.threat) -> (libellé, clé de couleur)
STATUS = {0: ("DISCRET", "status_calm"), 1: ("SUSPECT", "status_suspect"), 2: ("ALERTE", "status_alert")}
STATUS_MARGIN = 12
STATUS_PADDING = (14, 7)
STATUS_DOT_RADIUS = 6
STATUS_BLINK_SPEED = 8.0  # rad/s : clignotement du voyant en alerte
END_DIM = 150  # opacité du voile sur les écrans de fin
SLOT_SIZE = 58
SLOT_GAP = 8
SLOT_MIN = 4  # emplacements affichés même vides, pour une barre stable
SLOT_MARGIN = 12
SLOT_ICON = 28
TIP_PADDING = (22, 12)
TIP_BOTTOM = 40  # entre le bandeau d'astuce et le bas de l'écran
TOAST_FADE = 0.5  # secondes de fondu à la fin d'un message
TOAST_LINE_HEIGHT = 34
TOAST_BOTTOM_OFFSET = 110  # au-dessus du bas de l'écran
PROMPT_GAP = 30  # entre l'objet et l'invite, en pixels
PROMPT_BAR_SIZE = (96, 6)
TIMER_BLINK_SPEED = 9.0  # rad/s : le chronomètre clignote sous le seuil d'avertissement
VIGNETTE_STEPS = 14
VIGNETTE_DEPTH = 0.16  # fraction de l'écran couverte par le halo rouge
VIGNETTE_MAX_ALPHA = 120
VIGNETTE_PULSE_SPEED = 3.0  # rad/s
DENIED_FLASH = 0.35  # secondes de clignotement de l'invite après une action refusée
DENIED_SHAKE = 3  # amplitude (px) de la secousse


class Hud:
    def __init__(self) -> None:
        self.font = pygame.font.Font(None, 26)
        self.small = pygame.font.Font(None, 21)
        self.tiny = pygame.font.Font(None, 17)
        self.big = pygame.font.Font(None, 96)
        self.big_timer = pygame.font.Font(None, 52)
        self._vignette: pygame.Surface | None = None  # halo d'alarme, construit à la première alerte
        self._denied_timer = 0.0
        self._toasts: list[list] = []  # [texte, couleur RVB, temps restant]

    def _text(self, surface, font, text, pos, color) -> None:
        surface.blit(font.render(text, True, COLORS["shadow"]), (pos[0] + 1, pos[1] + 1))
        surface.blit(font.render(text, True, color), pos)

    def draw(
        self,
        surface: pygame.Surface,
        *,
        fps: float,
        player: Player,
        tile: tuple[int, int],
        debug: bool,
        threat: GuardState = GuardState.PATROL,
        inventory: Inventory | None = None,
        objective: str = "",
        lockdown_left: float | None = None,
        visibility: str | None = None,
        disguise: str | None = None,
    ) -> None:
        x, y = 12, 10
        self._text(surface, self.font, f"Posture : {STANCE_LABELS[player.stance]}", (x, y), COLORS["text"])
        if visibility is not None:
            label, color_key = VISIBILITY_LABELS[visibility]
            self._text(surface, self.small, f"Visibilité : {label}", (x, y + 24), COLORS[color_key])
        if disguise is not None:
            label, color_key = DISGUISE_LABELS[disguise]
            self._text(surface, self.small, label, (x, y + 42), COLORS[color_key])
        if debug:
            lines = (
                f"FPS : {fps:.0f}",
                f"Position : {player.pos.x:.0f}, {player.pos.y:.0f}  (tuile {tile[0]}, {tile[1]})",
                f"Rayon de bruit : {player.noise_radius:.0f} px",
            )
            for i, line in enumerate(lines, start=1):
                self._text(surface, self.small, line, (x, y + 52 + i * 20), COLORS["text_dim"])

        if lockdown_left is not None:
            self._draw_alarm_vignette(surface)
        self._draw_status(surface, threat.threat)
        if lockdown_left is not None:
            self._draw_lockdown(surface, lockdown_left)
        if objective:
            self._draw_objective(surface, objective)
        self._draw_inventory(surface, inventory or Inventory())
        self._draw_toasts(surface)

    def _draw_status(self, surface: pygame.Surface, level: int) -> None:
        """Pastille en haut à droite : l'état d'alerte le plus élevé parmi les gardes."""
        label, color_key = STATUS[level]
        color = COLORS[color_key]
        text = self.font.render(label, True, COLORS["text"])
        pad_x, pad_y = STATUS_PADDING
        dot_space = 2 * STATUS_DOT_RADIUS + 8
        box = pygame.Rect(0, 0, text.get_width() + 2 * pad_x + dot_space, text.get_height() + 2 * pad_y)
        box.topright = (surface.get_width() - STATUS_MARGIN, STATUS_MARGIN)

        panel = pygame.Surface(box.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, (*COLORS["alert_bubble"], 190), panel.get_rect(), border_radius=box.height // 2)
        pygame.draw.rect(panel, (*color, 255), panel.get_rect(), 2, border_radius=box.height // 2)
        surface.blit(panel, box)

        blink = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() / 1000 * STATUS_BLINK_SPEED) if level == 2 else 1.0
        dot_color = tuple(round(c * (0.45 + 0.55 * blink)) for c in color)
        dot = (box.x + pad_x + STATUS_DOT_RADIUS, box.centery)
        pygame.draw.circle(surface, dot_color, dot, STATUS_DOT_RADIUS)
        surface.blit(text, (box.x + pad_x + dot_space, box.y + pad_y))

    def draw_dev(self, surface: pygame.Surface, active: list[str]) -> None:
        """Bandeau du mode développeur (en haut à droite) : rappelle qu'on triche et ce qui est actif."""
        text = "DEV" + (" : " + ", ".join(active) if active else "")
        label = self.small.render(text, True, COLORS["status_suspect"])
        surface.blit(label, label.get_rect(topright=(surface.get_width() - 12, 10)))

    def draw_caught(self, surface: pygame.Surface) -> None:
        self._draw_end_screen(surface, "CAPTURÉ", "status_alert", f"{bindings.label('restart')} : recommencer     {bindings.label('pause')} : menu")

    def draw_locked_down(self, surface: pygame.Surface) -> None:
        self._draw_end_screen(surface, "VERROUILLAGE", "status_alert", f"Le croiseur est scellé     {bindings.label('restart')} : recommencer     {bindings.label('pause')} : menu")

    def draw_won(self, surface: pygame.Surface) -> None:
        self._draw_end_screen(surface, "MISSION ACCOMPLIE", "status_calm", f"{bindings.label('restart')} : rejouer     {bindings.label('pause')} : menu")

    def _draw_end_screen(self, surface: pygame.Surface, title: str, color_key: str, hint: str) -> None:
        """Voile sombre, titre et consigne."""
        veil = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        veil.fill((*COLORS["background"], END_DIM))
        surface.blit(veil, (0, 0))
        center = surface.get_rect().center
        text = self.big.render(title, True, COLORS[color_key])
        surface.blit(text, text.get_rect(center=(center[0], center[1] - 20)))
        sub = self.font.render(hint, True, COLORS["text"])
        surface.blit(sub, sub.get_rect(center=(center[0], center[1] + 40)))

    # --- Objectif ------------------------------------------------------------
    def _draw_objective(self, surface: pygame.Surface, text: str) -> None:
        label = self.small.render(text, True, COLORS["text"])
        box = label.get_rect().inflate(24, 12)
        box.midtop = (surface.get_width() // 2, STATUS_MARGIN)
        panel = pygame.Surface(box.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, (*COLORS["panel"], 170), panel.get_rect(), border_radius=8)
        surface.blit(panel, box)
        surface.blit(label, label.get_rect(center=box.center))

    # --- Astuces contextuelles -------------------------------------------------------
    def draw_tip(self, surface: pygame.Surface, text: str, alpha: float = 1.0) -> None:
        """Bandeau d'astuce en bas de l'écran (une ou deux lignes), qui apparaît et disparaît en fondu."""
        if alpha <= 0:
            return
        lines = [self.font.render(line, True, COLORS["text"]) for line in text.split("\n")]
        width = max(line.get_width() for line in lines) + 2 * TIP_PADDING[0]
        height = sum(line.get_height() for line in lines) + (len(lines) - 1) * 4 + 2 * TIP_PADDING[1]
        box = pygame.Rect(0, 0, width, height)
        box.midbottom = (surface.get_width() // 2, surface.get_height() - TIP_BOTTOM)
        panel = pygame.Surface(box.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, (*COLORS["panel"], 225), panel.get_rect(), border_radius=12)
        pygame.draw.rect(panel, (*COLORS["terminal_screen"], 255), panel.get_rect(), 2, border_radius=12)
        y = TIP_PADDING[1]
        for line in lines:
            panel.blit(line, line.get_rect(midtop=(box.w // 2, y)))
            y += line.get_height() + 4
        panel.set_alpha(round(255 * min(1.0, alpha)))
        surface.blit(panel, box)

    # --- Inventaire ----------------------------------------------------------
    def _draw_inventory(self, surface: pygame.Surface, inventory: Inventory) -> None:
        """Barre d'emplacements en bas à droite : une pile par type d'objet."""
        stacks = inventory.stacks()
        slots = max(SLOT_MIN, len(stacks))
        width = slots * SLOT_SIZE + (slots - 1) * SLOT_GAP
        x0 = surface.get_width() - SLOT_MARGIN - width
        y0 = surface.get_height() - SLOT_MARGIN - SLOT_SIZE
        for i in range(slots):
            rect = pygame.Rect(x0 + i * (SLOT_SIZE + SLOT_GAP), y0, SLOT_SIZE, SLOT_SIZE)
            panel = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(panel, (*COLORS["panel"], 190), panel.get_rect(), border_radius=8)
            surface.blit(panel, rect)
            if i >= len(stacks):
                pygame.draw.rect(surface, COLORS["panel_border"], rect, 1, border_radius=8)
                continue
            item, count = stacks[i]
            pygame.draw.rect(surface, item_color(item), rect, 2, border_radius=8)
            draw_item_icon(surface, item, (rect.centerx, rect.centery - 5), SLOT_ICON)
            name = self.tiny.render(item.short_label, True, COLORS["text_dim"])
            surface.blit(name, name.get_rect(midbottom=(rect.centerx, rect.bottom - 4)))
            if count > 1:
                label = self.small.render(f"x{count}", True, COLORS["text"])
                surface.blit(label, label.get_rect(topright=(rect.right - 5, rect.y + 4)))

    # --- Messages ------------------------------------------------------------
    def notify(self, text: str, color: tuple[int, int, int] | None = None) -> None:
        """Affiche un message quelques secondes (les plus récents en bas)."""
        self._toasts.append([text, color or COLORS["text"], TOAST_DURATION])

    def clear_notifications(self) -> None:
        self._toasts.clear()
        self._denied_timer = 0.0

    def flash_denied(self) -> None:
        """L'action demandée est refusée : l'invite secoue et passe au rouge un instant."""
        self._denied_timer = DENIED_FLASH

    def update(self, dt: float) -> None:
        self._denied_timer = max(0.0, self._denied_timer - dt)
        for toast in self._toasts:
            toast[2] -= dt
        self._toasts = [t for t in self._toasts if t[2] > 0]

    def _draw_toasts(self, surface: pygame.Surface) -> None:
        width, height = surface.get_size()
        for i, (text, color, left) in enumerate(reversed(self._toasts)):
            label = self.font.render(text, True, color)
            box = label.get_rect().inflate(28, 12)
            box.midbottom = (width // 2, height - TOAST_BOTTOM_OFFSET - i * TOAST_LINE_HEIGHT)
            alpha = round(255 * min(1.0, left / TOAST_FADE))
            panel = pygame.Surface(box.size, pygame.SRCALPHA)
            pygame.draw.rect(panel, (*COLORS["panel"], round(200 * alpha / 255)), panel.get_rect(), border_radius=10)
            pygame.draw.rect(panel, (*color, alpha), panel.get_rect(), 1, border_radius=10)
            label.set_alpha(alpha)
            surface.blit(panel, box)
            surface.blit(label, label.get_rect(center=box.center))

    # --- Invite d'interaction ------------------------------------------------
    def draw_prompt(self, surface: pygame.Surface, screen_pos: tuple[int, int], prompt: Prompt, progress: float = 0.0) -> None:
        """Bulle « [E] action » au-dessus d'un objet ; barre de progression pour les actions maintenues."""
        denied = self._denied_timer > 0
        color = COLORS["text"] if prompt.enabled else COLORS["status_alert"]
        label = self.small.render(prompt.label, True, color)
        key = self.small.render(bindings.label("interact"), True, COLORS["panel"])
        cap = pygame.Rect(0, 0, max(22, key.get_width() + 10), 22)  # la pastille s'adapte à « E », « Ctrl gauche » ou « A »
        gap = 8
        box = pygame.Rect(0, 0, (cap.w + gap if prompt.enabled else 0) + label.get_width() + 20, 32)
        shake = round(DENIED_SHAKE * math.sin(self._denied_timer * 70)) if denied else 0
        box.midbottom = (screen_pos[0] + shake, screen_pos[1] - PROMPT_GAP)

        panel = pygame.Surface(box.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, (*(COLORS["status_alert"] if denied else COLORS["panel"]), 215), panel.get_rect(), border_radius=10)
        pygame.draw.rect(panel, (*color, 255), panel.get_rect(), 3 if denied else 1, border_radius=10)
        surface.blit(panel, box)

        x = box.x + 10
        if prompt.enabled:
            cap.midleft = (x, box.centery)
            pygame.draw.rect(surface, COLORS["text"], cap, border_radius=5)
            surface.blit(key, key.get_rect(center=cap.center))
            x += cap.w + gap
        surface.blit(label, label.get_rect(midleft=(x, box.centery)))

        if progress > 0:
            bar = pygame.Rect(0, 0, *PROMPT_BAR_SIZE)
            bar.midtop = (box.centerx, box.bottom + 4)
            pygame.draw.rect(surface, COLORS["panel"], bar, border_radius=3)
            fill = bar.copy()
            fill.w = max(2, round(bar.w * progress))
            pygame.draw.rect(surface, COLORS["terminal_screen"], fill, border_radius=3)
            pygame.draw.rect(surface, COLORS["panel_border"], bar, 1, border_radius=3)

    # --- Alerte globale ------------------------------------------------------
    def _draw_lockdown(self, surface: pygame.Surface, seconds_left: float) -> None:
        """Chronomètre de verrouillage sous la pastille d'alerte ; il clignote dans les dernières secondes."""
        seconds = max(0, math.ceil(seconds_left))
        label = self.big_timer.render(f"{seconds // 60}:{seconds % 60:02d}", True, COLORS["text"])
        caption = self.small.render("VERROUILLAGE", True, COLORS["status_alert"])
        box = pygame.Rect(0, 0, max(label.get_width(), caption.get_width()) + 28, label.get_height() + caption.get_height() + 14)
        box.topright = (surface.get_width() - STATUS_MARGIN, STATUS_MARGIN + 44)
        urgent = seconds_left <= LOCKDOWN_WARNING_TIME
        blink = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() / 1000 * TIMER_BLINK_SPEED) if urgent else 1.0

        panel = pygame.Surface(box.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, (*COLORS["panel"], 200), panel.get_rect(), border_radius=10)
        border = tuple(round(c * (0.4 + 0.6 * blink)) for c in COLORS["status_alert"])
        pygame.draw.rect(panel, (*border, 255), panel.get_rect(), 2, border_radius=10)
        surface.blit(panel, box)
        surface.blit(caption, caption.get_rect(midtop=(box.centerx, box.y + 6)))
        if blink > 0.35:
            surface.blit(label, label.get_rect(midbottom=(box.centerx, box.bottom - 4)))

    def _draw_alarm_vignette(self, surface: pygame.Surface) -> None:
        """Halo rouge pulsant sur les bords de l'écran (feux d'alarme)."""
        if self._vignette is None or self._vignette.get_size() != surface.get_size():
            self._vignette = self._build_vignette(surface.get_size())
        pulse = 0.55 + 0.45 * math.sin(pygame.time.get_ticks() / 1000 * VIGNETTE_PULSE_SPEED)
        self._vignette.set_alpha(round(255 * pulse))
        surface.blit(self._vignette, (0, 0))

    @staticmethod
    def _build_vignette(size: tuple[int, int]) -> pygame.Surface:
        """Cadres concentriques de plus en plus transparents vers le centre."""
        vignette = pygame.Surface(size, pygame.SRCALPHA)
        width, height = size
        depth = min(width, height) * VIGNETTE_DEPTH
        for i in range(VIGNETTE_STEPS):
            inset = depth * i / VIGNETTE_STEPS
            alpha = round(VIGNETTE_MAX_ALPHA * (1 - i / VIGNETTE_STEPS) ** 2)
            rect = pygame.Rect(0, 0, width, height).inflate(-2 * inset, -2 * inset)
            pygame.draw.rect(vignette, (*COLORS["alarm"], alpha), rect, max(1, round(depth / VIGNETTE_STEPS) + 1))
        return vignette
