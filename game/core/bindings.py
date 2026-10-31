"""Touches du jeu : liaisons remappables, étiquettes lisibles, et ce qu'on affiche selon le périphérique utilisé.

Chaque action a deux emplacements de touche (par exemple Z et la flèche haut pour avancer). Les touches réservées
(pause, debug, éclairage, recommencer) ne se remappent pas. Les liaisons actives sont dans `current` (lues par `input.py`
et par la scène de jeu) ; elles sont enregistrées dans les préférences sous forme de noms de touches, tolérants aux
erreurs : un nom inconnu retombe sur la touche par défaut.
"""
from __future__ import annotations

from dataclasses import dataclass

import pygame

from game.settings import DEBUG_KEY, KEYS, LIGHTING_KEY, QUIT_KEY, RESTART_KEY, THROW_KEY

ACTIONS = ("up", "down", "left", "right", "run", "crouch", "interact", "throw", "disguise")
ACTION_LABELS = {
    "up": "Avancer",
    "down": "Reculer",
    "left": "Aller à gauche",
    "right": "Aller à droite",
    "run": "Courir",
    "crouch": "S'accroupir",
    "interact": "Interagir / pirater",
    "throw": "Lancer un leurre",
    "disguise": "Enfiler l'uniforme",
}
SLOTS = 2
DEFAULTS = {**{action: tuple(keys) for action, keys in KEYS.items()}, "throw": (THROW_KEY,)}
RESERVED = frozenset({QUIT_KEY, DEBUG_KEY, LIGHTING_KEY, RESTART_KEY})

KEY_NAMES = {  # noms pygame -> libellés français (les autres touches s'affichent en majuscules)
    "left shift": "Maj gauche",
    "right shift": "Maj droite",
    "left ctrl": "Ctrl gauche",
    "right ctrl": "Ctrl droite",
    "left alt": "Alt gauche",
    "right alt": "Alt droite",
    "space": "Espace",
    "return": "Entrée",
    "tab": "Tab",
    "up": "Haut",
    "down": "Bas",
    "left": "Gauche",
    "right": "Droite",
    "escape": "Échap",
    "backspace": "Retour",
    "caps lock": "Verr. maj",
}
# Ce qu'affichent les astuces et les invites quand on joue à la manette.
PAD_LABELS = {
    "interact": "A",
    "throw": "X",
    "disguise": "LB",
    "crouch": "B",
    "run": "RT",
    "pause": "Start",
    "restart": "Y",
    "move": "le joystick gauche",
    "up": "joystick haut",
    "down": "joystick bas",
    "left": "joystick gauche",
    "right": "joystick droite",
}
KEYBOARD_FIXED = {"pause": "Échap", "restart": "R"}
PAD = "pad"
KEYBOARD = "keyboard"


def key_label(code: int) -> str:
    name = pygame.key.name(code)
    if not name:
        return "?"
    return KEY_NAMES.get(name, name.upper() if len(name) == 1 else name.capitalize())


@dataclass(frozen=True)
class RebindResult:
    ok: bool
    message: str = ""
    swapped_with: str | None = None  # l'action qui a récupéré l'ancienne touche


class KeyBindings:
    def __init__(self) -> None:
        self.slots: dict[str, list[int | None]] = {}
        self.reset()

    def reset(self) -> None:
        self.slots = {action: [*DEFAULTS[action], *([None] * (SLOTS - len(DEFAULTS[action])))] for action in ACTIONS}

    # --- Lecture ---------------------------------------------------------------
    def keys(self, action: str) -> tuple[int, ...]:
        return tuple(key for key in self.slots[action] if key is not None)

    def key_at(self, action: str, slot: int) -> int | None:
        return self.slots[action][slot]

    def slot_label(self, action: str, slot: int) -> str:
        key = self.slots[action][slot]
        return key_label(key) if key is not None else "—"

    def is_default(self) -> bool:
        return all(self.slots[a] == [*DEFAULTS[a], *([None] * (SLOTS - len(DEFAULTS[a])))] for a in ACTIONS)

    def owner_of(self, key: int) -> tuple[str, int] | None:
        for action in ACTIONS:
            for slot, bound in enumerate(self.slots[action]):
                if bound == key:
                    return action, slot
        return None

    # --- Remappage -------------------------------------------------------------------
    def rebind(self, action: str, slot: int, key: int) -> RebindResult:
        """Donne `key` à l'emplacement `slot` de `action`. Si une autre liaison l'avait, elles échangent leurs touches."""
        if key in RESERVED:
            return RebindResult(False, f"{key_label(key)} est une touche réservée")
        current = self.slots[action][slot]
        if current == key:
            return RebindResult(True)
        owner = self.owner_of(key)
        if owner is None:
            self.slots[action][slot] = key
            return RebindResult(True)
        other, other_slot = owner
        if other == action:  # la même action : les deux emplacements s'échangent
            self.slots[action][slot], self.slots[action][other_slot] = key, current
            return RebindResult(True)
        if current is None and sum(k is not None for k in self.slots[other]) == 1:
            return RebindResult(False, f"{ACTION_LABELS[other]} n'aurait plus aucune touche")
        self.slots[other][other_slot] = current  # l'autre action reprend notre ancienne touche (ou la perd si on n'en avait pas)
        self.slots[action][slot] = key
        if not self.keys(other) or not self.keys(action):
            self.slots[other][other_slot], self.slots[action][slot] = key, current  # annule
            return RebindResult(False, f"{ACTION_LABELS[other]} n'aurait plus aucune touche")
        return RebindResult(True, f"{key_label(key)} était utilisée pour « {ACTION_LABELS[other]} » : échangées", other)

    def clear(self, action: str, slot: int) -> RebindResult:
        """Vide un emplacement, à condition qu'il reste une touche à l'action."""
        if self.slots[action][slot] is None:
            return RebindResult(True)
        if len(self.keys(action)) <= 1:
            return RebindResult(False, f"{ACTION_LABELS[action]} doit garder une touche")
        self.slots[action][slot] = None
        return RebindResult(True)

    # --- Enregistrement ------------------------------------------------------------------
    def to_prefs(self) -> dict[str, list[str | None]]:
        """Seules les actions modifiées sont enregistrées, par noms de touches (indépendants de la version de pygame)."""
        default = KeyBindings()
        return {
            action: [pygame.key.name(key) if key is not None else None for key in self.slots[action]]
            for action in ACTIONS
            if self.slots[action] != default.slots[action]
        }

    @classmethod
    def from_prefs(cls, data) -> KeyBindings:
        """Tolérant : tout ce qui est illisible, réservé, en double ou laisse une action sans touche est ignoré."""
        bindings = cls()
        if not isinstance(data, dict):
            return bindings
        for action in ACTIONS:
            names = data.get(action)
            if not isinstance(names, list) or len(names) != SLOTS:
                continue
            keys = [_key_from_name(name) for name in names]
            if any(key is None and name is not None for key, name in zip(keys, names)):
                continue  # un nom de touche illisible : on garde les touches par défaut de cette action
            real = [k for k in keys if k is not None]
            if not real or len(set(real)) != len(real) or any(k in RESERVED for k in real):
                continue
            bindings.slots[action] = [*real, *([None] * (SLOTS - len(real)))]  # une touche vide passe toujours en second
        seen: dict[int, str] = {}  # une même touche ne peut servir à deux actions : on revient aux défauts pour les fautives
        for action in ACTIONS:
            for key in bindings.keys(action):
                if key in seen and seen[key] != action:
                    bindings.slots[action] = [*DEFAULTS[action], *([None] * (SLOTS - len(DEFAULTS[action])))]
                    break
                seen[key] = action
        return bindings


def _key_from_name(name) -> int | None:
    if not isinstance(name, str) or not name:
        return None
    try:
        return pygame.key.key_code(name)
    except (ValueError, pygame.error):
        return None


# --- État partagé : liaisons actives et périphérique en cours d'utilisation -----------------------------------
current = KeyBindings()
device = KEYBOARD  # "keyboard" (clavier et souris) ou "pad" (manette) : choisit ce qu'affichent invites et astuces


def load(prefs_keys) -> None:
    global current
    current = KeyBindings.from_prefs(prefs_keys)


def label(action: str, for_device: str | None = None) -> str:
    """Ce qu'il faut afficher pour désigner une action : la touche (clavier) ou le bouton (manette)."""
    if (for_device or device) == PAD:
        return PAD_LABELS[action]
    if action == "move":
        return " ".join(current.slot_label(a, 0) for a in ("up", "left", "down", "right"))
    if action in KEYBOARD_FIXED:
        return KEYBOARD_FIXED[action]
    return key_label(current.keys(action)[0])
