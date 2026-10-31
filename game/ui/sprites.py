"""Personnages vus de dessus : l'agent rebelle et les gardes impériaux, dessinés par code (aucune image à fournir).

Chaque personnage est décrit dans un repère local (`u` vers l'avant, `v` vers la droite), puis tourné vers là où il regarde :
ombre, jambes et bras qui se balancent avec la marche, sac, torse, tête casquée. La posture change l'allure (accroupi : tassé,
course : penché en avant), et le liseré du garde suit son état d'alerte. Rien ici ne dépend de l'état du jeu : on passe la
position, la direction, la phase du pas et l'état, et l'on obtient une image, donc c'est testable sur une simple surface.
"""
from __future__ import annotations

import math

import pygame

from game.settings import COLORS, SPRITE_BREATH, SPRITE_LEAN, SPRITE_SCALE, SPRITE_SIZE, SPRITE_SWING

OUTLINE = COLORS["player_outline"]
ELLIPSE_POINTS = 14


class Frame:
    """Passage du repère du personnage (avant, droite) à l'écran."""

    def __init__(self, center, facing, scale: float = 1.0) -> None:
        self.center = pygame.Vector2(center)
        f = pygame.Vector2(facing)
        self.forward = f.normalize() if f.length_squared() > 1e-9 else pygame.Vector2(1, 0)
        self.right = pygame.Vector2(-self.forward.y, self.forward.x)
        self.scale = scale * SPRITE_SIZE  # un peu plus grand que la boîte de collision : le personnage se lit mieux

    def point(self, u: float, v: float) -> tuple[float, float]:
        p = self.center + (self.forward * u + self.right * v) * self.scale
        return p.x, p.y

    def points(self, pts) -> list[tuple[float, float]]:
        return [self.point(u, v) for u, v in pts]

    def ellipse(self, u0: float, v0: float, ru: float, rv: float) -> list[tuple[float, float]]:
        return self.points(
            (u0 + ru * math.cos(t), v0 + rv * math.sin(t)) for t in (math.tau * i / ELLIPSE_POINTS for i in range(ELLIPSE_POINTS))
        )


def _shape(surface, color, points, outline: bool = True) -> None:
    pygame.draw.polygon(surface, color, points)
    if outline:
        pygame.draw.polygon(surface, OUTLINE, points, 1)


def _disc(surface, frame: Frame, color, u: float, v: float, radius: float, outline: bool = True) -> None:
    x, y = frame.point(u, v)
    r = max(1, round(radius * frame.scale))
    pygame.draw.circle(surface, color, (round(x), round(y)), r)
    if outline:
        pygame.draw.circle(surface, OUTLINE, (round(x), round(y)), r, 1)


def _limb(surface, frame: Frame, color, a, b, width: float) -> None:
    pygame.draw.line(surface, OUTLINE, frame.point(*a), frame.point(*b), round(width * frame.scale) + 1)
    pygame.draw.line(surface, color, frame.point(*a), frame.point(*b), max(1, round(width * frame.scale)))


def _shadow(surface, center, facing, ru: float, rv: float, scale: float) -> None:
    frame = Frame((center[0] + 2, center[1] + 3), facing, scale)
    pygame.draw.polygon(surface, COLORS["shadow"], frame.ellipse(0, 0, ru, rv))


def swing(phase: float, amplitude: float, stride: float, side: int) -> float:
    """Avancée (px) du pied ou de la main du côté `side` (+1 droite, -1 gauche) : les côtés sont en opposition de phase."""
    return math.sin(phase + (math.pi if side < 0 else 0.0)) * amplitude * stride


# --- L'agent rebelle ------------------------------------------------------------------------------------------------
def draw_player(
    surface: pygame.Surface, center, facing, stance: str, phase: float = 0.0, stride: float = 0.0, time: float = 0.0, disguised: bool = False
) -> None:
    """`stance` : "crouch", "walk" ou "run". `phase` : cycle de marche (rad). `stride` : 0 à l'arrêt, 1 en marche.
    `disguised` : en uniforme impérial (tunique grise, calot sombre, plus de sac ni de liseré rebelle)."""
    scale = SPRITE_SCALE[stance]
    frame = Frame(center, facing, scale)
    amplitude, lean = SPRITE_SWING[stance], SPRITE_LEAN[stance]
    vest = COLORS["uniform"] if disguised else COLORS[f"player_{stance}"]
    breath = SPRITE_BREATH * math.sin(time * 2.4) * (1 - stride)

    _shadow(surface, center, facing, 11, 12, scale)
    if not disguised:
        _shape(surface, COLORS["sprite_pack"], frame.points(((-10.5, -5), (-5.5, -5.5), (-5.5, 5.5), (-10.5, 5))))  # sac (un officier n'en porte pas)
    for side in (-1, 1):  # bottes
        step = swing(phase, amplitude, stride, side)
        _shape(surface, COLORS["sprite_boot"], frame.ellipse(step + lean * 0.3, side * 3.6, 4.6, 2.7))
    _shape(surface, vest, frame.ellipse(-0.5 + lean * 0.4, 0, 6.6, 10.4 + breath))  # torse
    pygame.draw.line(surface, tuple(max(0, c - 55) for c in vest), *frame.points(((-3.5 + lean * 0.4, -8), (-3.5 + lean * 0.4, 8))), 2)  # ceinture
    left = swing(phase, amplitude * 0.9, stride, -1)
    right_hand = (7.5 - lean * 0.2 if stance != "run" else 5.5, 7.4)
    _limb(surface, frame, vest, (0.5, -8.2), (3.0 + left * 0.8 + lean * 0.4, -9.6), 4)  # bras gauche qui balance
    _disc(surface, frame, COLORS["sprite_skin"], 3.0 + left * 0.8 + lean * 0.4, -9.8, 2.3)
    _limb(surface, frame, vest, (0.5, 8.2), right_hand, 4)  # bras droit tendu vers le pistolet
    _limb(surface, frame, COLORS["guard_gun"], right_hand, (right_hand[0] + 7.0, right_hand[1]), 3)  # pistolet
    _disc(surface, frame, COLORS["sprite_skin"], right_hand[0], right_hand[1], 2.3)
    head_u = 1.6 + lean
    if disguised:  # calot d'officier : dessus sombre, visière qui avance, petit insigne rouge
        _disc(surface, frame, COLORS["sprite_skin"], head_u, 0, 5.2)
        _shape(surface, COLORS["uniform_cap"], frame.ellipse(head_u - 0.6, 0, 5.4, 6.0))
        _shape(surface, _dim(COLORS["uniform_cap"], 0.75), frame.points(((head_u + 3.6, -3.6), (head_u + 6.2, -2.4), (head_u + 6.2, 2.4), (head_u + 3.6, 3.6))), outline=False)
        pygame.draw.circle(surface, COLORS["status_alert"], tuple(round(c) for c in frame.point(head_u + 0.4, 0)), 1)
        return
    _disc(surface, frame, COLORS["sprite_helmet"], head_u, 0, 5.8)  # casque
    pygame.draw.line(surface, COLORS["sprite_stripe"], *frame.points(((head_u - 4.4, 0), (head_u + 1.2, 0))), max(1, round(2 * scale)))
    _shape(surface, COLORS["sprite_glass"], frame.points(((head_u + 2.6, -3.5), (head_u + 5.2, -2.4), (head_u + 5.2, 2.4), (head_u + 2.6, 3.5))), outline=False)  # lunettes


# --- Le garde impérial ----------------------------------------------------------------------------------------------------------
def draw_guard(
    surface: pygame.Surface,
    center,
    facing,
    state_color,
    phase: float = 0.0,
    stride: float = 0.0,
    aiming: bool = False,
    reinforcement: bool = False,
    time: float = 0.0,
) -> None:
    """`state_color` : la couleur d'alerte (liseré, épaulettes, œil de la visière). `aiming` : en poursuite, le fusil est épaulé."""
    frame = Frame(center, facing)
    armor, shade, under = COLORS["armor_white"], COLORS["armor_shade"], COLORS["armor_under"]
    amplitude = SPRITE_SWING["walk"] * (1.25 if aiming else 1.0)
    breath = SPRITE_BREATH * math.sin(time * 2.0) * (1 - stride)

    _shadow(surface, center, facing, 11.5, 12.5, 1.0)
    for side in (-1, 1):  # jambes
        step = swing(phase, amplitude, stride, side)
        _limb(surface, frame, under, (step - 3.5, side * 3.4), (step + 1.5, side * 3.4), 4.2)
        _shape(surface, shade, frame.ellipse(step + 2.2, side * 3.4, 3.4, 2.4))
    _shape(surface, armor, frame.ellipse(-1.6, 0, 6.6, 9.6 + breath))  # plastron
    _shape(surface, shade, frame.ellipse(-0.4, 0, 2.6, 4.6), outline=False)  # plaque centrale
    pygame.draw.line(surface, state_color, *frame.points(((-5.6, -6.2), (-5.6, 6.2))), 3)  # liseré d'alerte dans le dos
    for side in (-1, 1):  # épaulettes
        _shape(surface, state_color if side > 0 else armor, frame.ellipse(-0.6, side * 9.4, 3.4, 3.0))
    # Fusil tenu à droite, mains sur la poignée et le garde-main ; épaulé (plus avancé, bras tendus) en poursuite.
    muzzle = 20.5 if aiming else 18.0
    grip, hand = (6.5, 7.6) if aiming else (4.6, 7.6), (12.5, 7.6) if aiming else (10.0, 7.6)
    _limb(surface, frame, COLORS["guard_gun"], (1.0, 7.6), (muzzle, 7.6), 3.4)
    _limb(surface, frame, under, (-0.6, 8.6), grip, 3.6)  # bras en combinaison sombre : on les distingue de l'armure
    _limb(surface, frame, under, (-0.6, -8.6), (hand[0] - 3.5, 0.5), 3.6)
    _limb(surface, frame, under, (hand[0] - 3.5, 0.5), hand, 3.2)
    _disc(surface, frame, COLORS["guard_gun"], grip[0], grip[1], 2.0)
    _disc(surface, frame, COLORS["guard_gun"], hand[0], hand[1], 2.0)
    head_u = 0.6 + (1.4 if aiming else 0.0)
    _disc(surface, frame, shade, head_u, 0, 6.2)  # casque
    _disc(surface, frame, armor, head_u - 0.5, 0, 4.7, outline=False)
    if reinforcement:  # les renforts portent une bande bleue sur le casque
        pygame.draw.line(surface, COLORS["guard_reinforcement"], *frame.points(((head_u - 5.2, 0), (head_u + 0.6, 0))), 3)
    _shape(surface, COLORS["guard_visor"], frame.points(((head_u + 1.8, -4.6), (head_u + 5.4, -3.4), (head_u + 5.4, 3.4), (head_u + 1.8, 4.6))), outline=False)  # visière
    pygame.draw.line(surface, state_color, *frame.points(((head_u + 4.0, -2.8), (head_u + 4.0, 2.8))), 2)  # œil de la visière


# --- Le prisonnier -----------------------------------------------------------------------------------------------------------------
def draw_prisoner(surface: pygame.Surface, center, facing, captive: bool, phase: float = 0.0, stride: float = 0.0, time: float = 0.0) -> None:
    """Prisonnier en combinaison orange : agenouillé, poignets entravés devant lui, tant qu'il est captif ; libre, il marche comme l'agent."""
    frame = Frame(center, facing, 0.92 if captive else 1.0)
    suit = COLORS["prisoner_suit"]
    amplitude = SPRITE_SWING["walk"]
    breath = SPRITE_BREATH * math.sin(time * 1.8)
    _shadow(surface, center, facing, 10.5, 11.5, frame.scale)
    for side in (-1, 1):  # jambes (repliées sous lui quand il est captif)
        step = 0.0 if captive else swing(phase, amplitude, stride, side)
        _shape(surface, _dim(suit, 0.72), frame.ellipse(step - (2.0 if captive else 0.0), side * 3.4, 4.8 if captive else 4.4, 2.8))
    _shape(surface, suit, frame.ellipse(-0.5, 0, 6.4, 9.6 + breath))  # torse
    pygame.draw.line(surface, _dim(suit, 0.6), *frame.points(((-3.2, -7), (-3.2, 7))), 2)
    if captive:  # poignets liés devant, menottes grises
        _limb(surface, frame, suit, (0.5, -8), (6.0, -1.8), 4)
        _limb(surface, frame, suit, (0.5, 8), (6.0, 1.8), 4)
        _disc(surface, frame, COLORS["prisoner_cuff"], 6.4, 0, 3.0)
        pygame.draw.line(surface, OUTLINE, *frame.points(((6.4, -2), (6.4, 2))), 1)
    else:
        left = swing(phase, amplitude * 0.9, stride, -1)
        _limb(surface, frame, suit, (0.5, -8), (3.0 + left * 0.8, -9.4), 4)
        _limb(surface, frame, suit, (0.5, 8), (3.0 - left * 0.8, 9.4), 4)
        _disc(surface, frame, COLORS["sprite_skin"], 3.0 + left * 0.8, -9.6, 2.2)
        _disc(surface, frame, COLORS["sprite_skin"], 3.0 - left * 0.8, 9.6, 2.2)
        _disc(surface, frame, COLORS["prisoner_cuff"], 3.0 + left * 0.8, -9.6, 1.2, outline=False)  # restes des menottes aux poignets
    head_u = 2.4 if captive else 1.6  # tête baissée quand il est captif
    _disc(surface, frame, COLORS["sprite_skin"], head_u, 0, 5.4)
    _shape(surface, (54, 44, 40), frame.ellipse(head_u - 1.6, 0, 4.2, 5.0), outline=False)  # cheveux
    _disc(surface, frame, (54, 44, 40), head_u - 1.6, 0, 3.4, outline=False)


def _dim(color, factor: float):
    return tuple(max(0, min(255, round(c * factor))) for c in color)
