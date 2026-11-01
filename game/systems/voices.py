"""Répliques et radios des gardes : on choisit quelle variante jouer, sans se répéter ni couvrir une réplique par une autre.

Chaque catégorie (`suspect`, `chase`, `lost`, `radio`) a quelques variantes `voice_<catégorie>_<n>`. On les tire dans un sac
mélangé : aucune ne revient avant que toutes soient passées, et la première d'un nouveau sac n'est jamais la dernière de
l'ancien. Un délai global (`VOICE_GAP`) évite que deux gardes parlent en même temps, un délai par catégorie
(`VOICE_CATEGORY_COOLDOWN`) que la même scène se répète. Pur : l'horloge avance par `tick(dt)`.
"""

from __future__ import annotations

import random

from game.settings import VOICE_CATEGORY_COOLDOWN, VOICE_GAP, VOICE_LINES


class VoiceBank:
    def __init__(self, lines=None, rng: random.Random | None = None, gap: float = VOICE_GAP, cooldown: float = VOICE_CATEGORY_COOLDOWN) -> None:
        self.lines = dict(VOICE_LINES if lines is None else lines)
        self.rng = rng or random.Random()
        self.gap, self.cooldown = gap, cooldown
        self.clock = 0.0
        self._last_any = float("-inf")
        self._last: dict[str, float] = {}
        self._bags: dict[str, list[int]] = {}
        self._previous: dict[str, int] = {}

    def tick(self, dt: float) -> None:
        self.clock += dt

    def ready(self, category: str, *, urgent: bool = False) -> bool:
        """Vrai si la catégorie peut parler maintenant. Une réplique `urgent` (repérage) ignore le délai de catégorie."""
        if category not in self.lines or self.lines[category] <= 0:
            return False
        if self.clock - self._last_any < self.gap:
            return False
        return urgent or self.clock - self._last.get(category, float("-inf")) >= self.cooldown

    def pick(self, category: str, *, urgent: bool = False) -> str | None:
        """Nom du son à jouer pour `category`, ou None si c'est trop tôt (ou la catégorie inconnue)."""
        if not self.ready(category, urgent=urgent):
            return None
        bag = self._bags.get(category)
        if not bag:
            bag = list(range(1, self.lines[category] + 1))
            self.rng.shuffle(bag)
            if len(bag) > 1 and bag[-1] == self._previous.get(category):
                bag[0], bag[-1] = bag[-1], bag[0]  # on pioche par la fin : la dernière jouée ne rouvre pas le sac suivant
            self._bags[category] = bag
        number = bag.pop()
        self._previous[category] = number
        self._last_any = self._last[category] = self.clock
        return f"voice_{category}_{number}"
