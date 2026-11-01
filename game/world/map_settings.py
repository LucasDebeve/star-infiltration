"""Réglages propres à une carte (directives `@lockdown`, `@waves`, `@detect`, `@stay`, `@ambient`). Données pures.

Chaque mission peut ainsi avoir son équilibrage sans toucher au code. Les valeurs sont données **pour la difficulté normale** ;
les autres difficultés les font varier dans la même proportion (voir `Difficulty.for_map`). Une directive absente laisse
la valeur de la difficulté (ou du thème) telle quelle.

    @lockdown 120        secondes entre l'alerte et le verrouillage
    @waves 2             vagues de renforts
    @detect 1.2          multiplie la vitesse de détection des gardes (et des caméras)
    @stay 20             secondes de présence d'un renfort
    @ambient 90,100,130  lumière ambiante (RVB), à la place de celle du thème
"""

from __future__ import annotations

from dataclasses import dataclass, replace

LIMITS = {"lockdown": (30.0, 600.0), "waves": (0, 8), "detect": (0.3, 3.0), "stay": (5.0, 120.0)}
NAMES = ("lockdown", "waves", "detect", "stay", "ambient")


@dataclass(frozen=True)
class MapSettings:
    lockdown: float | None = None
    waves: int | None = None
    detect: float | None = None
    stay: float | None = None
    ambient: tuple[int, int, int] | None = None

    def is_empty(self) -> bool:
        return all(getattr(self, name) is None for name in NAMES)


def apply_setting(current: MapSettings, name: str, args: str) -> MapSettings:
    """Renvoie `current` avec la directive `name` appliquée (ValueError en français si elle est illisible, hors limites ou répétée)."""
    if getattr(current, name) is not None:
        raise ValueError(f"@{name} est indiqué deux fois")
    args = args.strip()
    if name == "ambient":
        parts = [p.strip() for p in args.split(",")]
        try:
            color = tuple(int(p) for p in parts)
        except ValueError:
            raise ValueError("@ambient attend trois entiers séparés par des virgules, comme '90,100,130'") from None
        if len(color) != 3 or not all(0 <= c <= 255 for c in color):
            raise ValueError("@ambient attend trois valeurs entre 0 et 255, comme '90,100,130'")
        return replace(current, ambient=color)
    low, high = LIMITS[name]
    try:
        value = int(args) if name == "waves" else float(args)
    except ValueError:
        raise ValueError(f"@{name} attend un nombre{' entier' if name == 'waves' else ''}, reçu {args!r}") from None
    if not low <= value <= high:
        raise ValueError(f"@{name} {value:g} hors de {low:g}..{high:g}")
    return replace(current, **{name: value})
