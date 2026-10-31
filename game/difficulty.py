"""Niveaux de difficulté : réglages de la détection et de l'alerte. Logique pure."""
from __future__ import annotations

from dataclasses import dataclass, replace

from game.settings import DEFAULT_DIFFICULTY, DIFFICULTIES


@dataclass(frozen=True)
class Difficulty:
    key: str
    label: str
    detect: float  # multiplie la vitesse à laquelle les gardes repèrent le joueur
    lockdown_time: float  # secondes entre l'alerte et le verrouillage du croiseur
    waves: int  # vagues de renforts pendant une alerte
    reinforcement_stay: float  # secondes de présence d'un renfort


    def for_map(self, settings) -> Difficulty:
        """Cette difficulté avec les réglages d'une carte : ils valent pour la difficulté normale, les autres suivent la même proportion
        (le verrouillage et la présence des renforts) ou le même écart (le nombre de vagues, la détection)."""
        if settings is None or settings.is_empty():
            return self
        normal = get_difficulty(DEFAULT_DIFFICULTY)
        changes = {}
        if settings.lockdown is not None:
            changes["lockdown_time"] = round(settings.lockdown * self.lockdown_time / normal.lockdown_time, 1)
        if settings.waves is not None:
            changes["waves"] = max(0, settings.waves + self.waves - normal.waves)
        if settings.detect is not None:
            changes["detect"] = round(settings.detect * self.detect / normal.detect, 3)
        if settings.stay is not None:
            changes["reinforcement_stay"] = round(settings.stay * self.reinforcement_stay / normal.reinforcement_stay, 1)
        return replace(self, **changes)


def get_difficulty(key: str) -> Difficulty:
    """La difficulté de clé `key` (inconnue : la difficulté par défaut, pour tolérer un vieux fichier de préférences)."""
    if key not in DIFFICULTIES:
        key = DEFAULT_DIFFICULTY
    cfg = DIFFICULTIES[key]
    return Difficulty(key, cfg["label"], cfg["detect"], cfg["lockdown"], cfg["waves"], cfg["stay"])


def all_difficulties() -> list[Difficulty]:
    return [get_difficulty(key) for key in DIFFICULTIES]
