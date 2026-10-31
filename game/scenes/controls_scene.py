"""Commandes : remapper les touches du clavier et régler l'usage de la manette. Enregistré dès qu'on change quelque chose."""
from __future__ import annotations

import pygame

from game.core import bindings
from game.scenes.menu_base import MenuScene
from game.settings import COLORS
from game.ui.menu import Button, KeyBind, Menu, Toggle

PAD_HELP = (
    "Manette : joystick gauche ou croix : se déplacer     joystick droit : viser     RT ou RB : courir     B : s'accroupir",
    "A : interagir     X : leurre     LB : uniforme     Y : recommencer     Start : pause     (dans les menus : croix, A pour valider, B pour revenir)",
)


class ControlsScene(MenuScene):
    title = "COMMANDES"
    top = 124
    row_height = 36  # douze lignes : on resserre pour garder la place du texte d'aide en dessous
    row_gap = 3

    def __init__(self, game, backdrop) -> None:
        super().__init__(game, backdrop)
        self.waiting: tuple[str, int] | None = None  # (action, emplacement) en attente d'une touche
        self.message = ""

    def build_menu(self) -> Menu:
        items = [
            KeyBind(
                bindings.ACTION_LABELS[action],
                lambda action=action: (bindings.current.slot_label(action, 0), bindings.current.slot_label(action, 1)),
                lambda slot, action=action: self._start_capture(action, slot),
            )
            for action in bindings.ACTIONS
        ]
        items += [
            Toggle("Utiliser la manette", lambda: self.game.prefs.gamepad, self._set_gamepad),
            Button("Rétablir les touches par défaut", self._reset),
            Button("Retour", self._back),
        ]
        return Menu(items, on_sound=self.sound, on_back=self._back)

    # --- Actions ---------------------------------------------------------------------
    def _start_capture(self, action: str, slot: int) -> None:
        self.waiting = (action, slot)
        self.message = ""

    def _finish_capture(self, key: int) -> None:
        action, slot = self.waiting
        self.waiting = None
        result = bindings.current.rebind(action, slot, key)
        self.message = result.message
        self.sound("ui_select" if result.ok else "door_denied")
        if result.ok:
            self._save()

    def _clear_selected(self) -> None:
        item = self.menu.selected
        if isinstance(item, KeyBind):
            action = bindings.ACTIONS[self.menu.index]
            result = bindings.current.clear(action, item.slot)
            self.message = result.message
            self.sound("ui_select" if result.ok else "door_denied")
            if result.ok:
                self._save()

    def _reset(self) -> None:
        bindings.current.reset()
        self.message = "Touches par défaut rétablies"
        self._save()

    def _set_gamepad(self, enabled: bool) -> None:
        self.game.prefs.gamepad = enabled
        self.game.gamepad.enabled = enabled
        self.game.prefs.save()

    def _save(self) -> None:
        self.game.prefs.keys = bindings.current.to_prefs()
        self.game.prefs.save()

    def _back(self) -> None:
        self.game.scenes.pop()

    # --- Entrées ---------------------------------------------------------------------------
    def handle_event(self, event: pygame.event.Event) -> None:
        if self.waiting is not None:  # on attend la nouvelle touche : tout le reste est suspendu
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.waiting = None
                    self.message = "Changement annulé"
                else:
                    self._finish_capture(event.key)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                self.waiting = None
            return
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_DELETE, pygame.K_BACKSPACE):
            self._clear_selected()
            return
        super().handle_event(event)

    # --- Dessin -------------------------------------------------------------------------------
    def draw_extra(self, surface: pygame.Surface) -> None:
        small = self.view.small_font
        width = surface.get_width() // 2
        pad = self.game.gamepad
        status = f"Manette détectée : {pad.name}" if pad.connected else "Aucune manette détectée : branchez-en une, elle sera reconnue aussitôt"
        lines = [
            (PAD_HELP[0], COLORS["text_dim"]),
            (PAD_HELP[1], COLORS["text_dim"]),
            (status, COLORS["status_calm"] if pad.connected else COLORS["text_dim"]),
        ]
        y = surface.get_height() - 118
        for i, (line, color) in enumerate(lines):
            text = small.render(line, True, color)
            surface.blit(text, text.get_rect(midtop=(width, y + i * 21)))
        text = small.render("Gauche / droite : choisir l'emplacement     Entrée : changer     Suppr : vider", True, COLORS["text_dim"])
        surface.blit(text, text.get_rect(midtop=(width, y + 3 * 21)))
        if self.message:
            note = small.render(self.message, True, COLORS["status_suspect"])
            surface.blit(note, note.get_rect(midtop=(width, y + 4 * 21 + 2)))
        if self.waiting is not None:
            self._draw_capture(surface)

    def _draw_capture(self, surface: pygame.Surface) -> None:
        veil = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        veil.fill((*COLORS["background"], 190))
        surface.blit(veil, (0, 0))
        action, slot = self.waiting
        title = self.view.heading_font.render(bindings.ACTION_LABELS[action], True, COLORS["text"])
        prompt = self.view.item_font.render("Appuyez sur la nouvelle touche", True, COLORS["terminal_screen"])
        hint = self.view.small_font.render("Échap : annuler", True, COLORS["text_dim"])
        center = surface.get_rect().center
        surface.blit(title, title.get_rect(midbottom=(center[0], center[1] - 10)))
        surface.blit(prompt, prompt.get_rect(midtop=(center[0], center[1] + 6)))
        surface.blit(hint, hint.get_rect(midtop=(center[0], center[1] + 52)))
