"""Thèmes visuels des missions : palette du sol et des murs, lumière ambiante, teinte des lampes, poussière.

Un thème est choisi par la directive `@theme nom` de la carte (le vaisseau impérial par défaut). Données pures :
le dessin des tuiles est dans `tile_art.py`, la lumière lit `ambient` et `lamp_tints`.
"""

from __future__ import annotations

from dataclasses import dataclass

from game.settings import AMBIENT_LIGHT, COLORS, DUST_COLOR, LAMP_TINTS

Color = tuple[int, int, int]


@dataclass(frozen=True)
class Theme:
    id: str
    label: str
    floor_a: Color
    floor_b: Color
    wall: Color
    wall_top: Color
    wall_shade: Color
    ambient: Color  # lumière de base (la scène est multipliée par elle)
    lamp_tints: tuple[Color, ...]  # teintes des lampes, une par salle
    dust: Color  # poussière de pas
    floor_style: str  # "deck" (plaques), "soil" (sol de forêt), "sand" (sable)
    wall_style: str  # "plate" (tôle), "timber" (rondins), "adobe" (pisé)
    detail: tuple[Color, ...] = ()  # couleurs des détails du sol (feuilles, mousse, cailloux...)
    decor: tuple[str, ...] = ()  # genres de décor mural : "lantern"
    decor_colors: tuple[Color, ...] = ()  # couleurs des écrans / lanternes
    vent_color: Color | None = None  # vapeur ou brume des bouches (None : pas de bouches)
    wind: tuple[float, float] | None = None  # direction du vent (None : air calme)
    wind_kind: str = ""  # "sand" (grains) ou "leaf" (feuilles)
    wind_color: Color = (200, 180, 140)


IMPERIAL = Theme(
    "imperial",
    "Vaisseau impérial",
    COLORS["floor_a"],
    COLORS["floor_b"],
    COLORS["wall"],
    COLORS["wall_top"],
    COLORS["wall_shade"],
    AMBIENT_LIGHT,
    LAMP_TINTS,
    DUST_COLOR,
    "deck",
    "plate",
    vent_color=(206, 214, 226),  # pas d'écrans ni de voyants muraux à bord : seulement la vapeur
)
ENDOR = Theme(
    "endor",
    "Base terrestre d'Endor",
    (44, 50, 36),
    (40, 46, 32),
    (92, 76, 54),
    (138, 118, 82),
    (50, 40, 28),
    (98, 134, 118),  # nuit de forêt : un peu verte
    ((236, 228, 168), (176, 232, 196), (255, 214, 140)),
    (84, 72, 50),
    "soil",
    "timber",
    ((74, 62, 36), (58, 88, 44), (32, 58, 38), (96, 84, 54)),
    decor=("lantern",),
    decor_colors=((190, 235, 150), (255, 214, 120)),
    vent_color=(150, 178, 160),  # brume qui monte du sol
    wind=(0.45, 1.0),
    wind_kind="leaf",
    wind_color=(96, 120, 60),
)
TATOOINE = Theme(
    "tatooine",
    "Base terrestre de Tatooine",
    (176, 148, 100),
    (168, 140, 94),
    (206, 172, 122),
    (238, 208, 158),
    (128, 100, 68),
    (156, 144, 134),  # jour du désert : chaude et claire
    ((255, 220, 160), (255, 240, 200), (255, 196, 128)),
    (204, 178, 130),
    "sand",
    "adobe",
    ((142, 114, 76), (196, 170, 124), (120, 96, 64)),
    decor=("lantern",),
    decor_colors=((255, 190, 110), (255, 214, 140)),
    wind=(1.0, 0.18),
    wind_kind="sand",
    wind_color=(226, 200, 150),
)

THEMES = {t.id: t for t in (IMPERIAL, ENDOR, TATOOINE)}
DEFAULT_THEME = IMPERIAL.id


def get_theme(theme_id: str) -> Theme:
    return THEMES[theme_id]
