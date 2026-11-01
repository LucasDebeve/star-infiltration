"""Dessin des props : conteneurs, vaisseaux (chasseur, navette), champ de force animé.

Tout est dessiné par le code (pas d'image à charger). Les sprites sont mis en cache : seul le champ de force
est animé, et il ne redessine que quelques lignes par image.
"""

from __future__ import annotations

import math
from functools import lru_cache

import pygame

from game.settings import (
    COLORS,
    CONTAINER_PALETTE,
    CONTAINER_STRIPES,
    FIELD_GATE_BAND,
    FIELD_PENDING_BLINK,
    FIELD_SCAN_SPACING,
    FIELD_SCAN_SPEED,
)
from game.world.props import BOX_KIND, FIELD_KIND, SHIP_KIND, Prop

FIGHTER_MAX_TILES = 9  # une coque jusqu'à 3 × 3 tuiles est un chasseur ; au-delà, une navette
CRATE_INSET = 2


def _variant(prop: Prop, count: int) -> int:
    """Variante stable de la position (deux conteneurs voisins n'ont pas la même couleur)."""
    return (prop.x * 7 + prop.y * 13 + prop.w * 3) % count


def _shade(color, factor: float) -> tuple[int, int, int]:
    return tuple(max(0, min(255, round(c * factor))) for c in color)


# --- Caisses et conteneurs ---------------------------------------------------
@lru_cache(maxsize=96)
def box_sprite(w: int, h: int, variant: int, tile_size: int) -> pygame.Surface:
    surf = pygame.Surface((w * tile_size, h * tile_size), pygame.SRCALPHA)
    rect = surf.get_rect().inflate(-2 * CRATE_INSET, -2 * CRATE_INSET)
    outline = COLORS["player_outline"]
    if w == 1 and h == 1:
        _draw_crate(surf, rect, variant)
    else:
        _draw_container(surf, rect, variant)
    pygame.draw.rect(surf, outline, rect, 2, border_radius=3)
    return surf


def _draw_crate(surf: pygame.Surface, rect: pygame.Rect, variant: int) -> None:
    """Petite caisse : plateau, renforts en croix, rivets, bande de danger sur un côté."""
    body, light, dark = COLORS["crate_body"], COLORS["crate_light"], COLORS["crate_dark"]
    pygame.draw.rect(surf, body, rect, border_radius=3)
    pygame.draw.line(surf, light, rect.topleft, rect.topright, 2)  # reflet en haut et à gauche
    pygame.draw.line(surf, light, rect.topleft, rect.bottomleft, 2)
    pygame.draw.line(surf, dark, rect.bottomleft, rect.bottomright, 3)
    pygame.draw.line(surf, dark, rect.topright, rect.bottomright, 3)
    inner = rect.inflate(-10, -10)
    pygame.draw.rect(surf, _shade(body, 0.82), inner)
    pygame.draw.line(surf, dark, inner.topleft, inner.bottomright, 2)
    pygame.draw.line(surf, dark, inner.topright, inner.bottomleft, 2)
    pygame.draw.rect(surf, dark, inner, 1)
    for corner in (rect.topleft, rect.topright, rect.bottomleft, rect.bottomright):
        pygame.draw.circle(surf, light, (corner[0] + (3 if corner[0] == rect.left else -3), corner[1] + (3 if corner[1] == rect.top else -3)), 1)
    if variant % 2 == 0:  # certaines caisses portent une bande de danger
        band = pygame.Rect(rect.x + 4, rect.bottom - 8, rect.w - 8, 4)
        for i in range(0, band.w, 6):
            pygame.draw.polygon(surf, COLORS["hazard_yellow"], [(band.x + i, band.bottom), (band.x + i + 3, band.bottom), (band.x + i + 6, band.y), (band.x + i + 3, band.y)])


def _draw_container(surf: pygame.Surface, rect: pygame.Rect, variant: int) -> None:
    """Conteneur de fret : coque ondulée, cadre, bande de couleur, poignées de porte à une extrémité."""
    hull = CONTAINER_PALETTE[variant % len(CONTAINER_PALETTE)]
    stripe = CONTAINER_STRIPES[variant % len(CONTAINER_STRIPES)]
    pygame.draw.rect(surf, hull, rect, border_radius=3)
    lengthwise = rect.w >= rect.h
    for i in range(6, (rect.w if lengthwise else rect.h) - 4, 5):  # ondulations perpendiculaires au grand côté
        a, b = ((rect.x + i, rect.y + 3), (rect.x + i, rect.bottom - 3)) if lengthwise else ((rect.x + 3, rect.y + i), (rect.right - 3, rect.y + i))
        pygame.draw.line(surf, _shade(hull, 0.78), a, b, 1)
        pygame.draw.line(surf, _shade(hull, 1.18), (a[0] + 1, a[1]), (b[0] + 1, b[1]), 1)
    frame = COLORS["crate_dark"]
    pygame.draw.rect(surf, frame, rect, 3, border_radius=3)
    pygame.draw.line(surf, _shade(hull, 1.35), (rect.x + 3, rect.y + 2), (rect.right - 3, rect.y + 2), 1)
    # Bande de couleur au milieu du grand côté.
    band = pygame.Rect(0, 0, rect.w - 14, 6) if lengthwise else pygame.Rect(0, 0, 6, rect.h - 14)
    band.center = rect.center
    pygame.draw.rect(surf, stripe, band)
    pygame.draw.rect(surf, frame, band, 1)
    # Extrémité « porte » : une plaque sombre avec son liseré.
    door = pygame.Rect(rect.right - 9, rect.y + 4, 5, rect.h - 8) if lengthwise else pygame.Rect(rect.x + 4, rect.bottom - 9, rect.w - 8, 5)
    pygame.draw.rect(surf, _shade(hull, 0.6), door)
    pygame.draw.rect(surf, COLORS["crate_light"], door.inflate(-3, -3), 1)
    for cx, cy in (rect.left, rect.top), (rect.right - 4, rect.top), (rect.left, rect.bottom - 4), (rect.right - 4, rect.bottom - 4):  # pièces d'angle
        pygame.draw.rect(surf, frame, (cx, cy, 4, 4))


# --- Vaisseaux ---------------------------------------------------------------
SHIP_SHADOW = (3, 4)  # décalage (px) de l'ombre portée : toujours vers le bas à droite, quelle que soit l'orientation
SHIP_SHADOW_ALPHA = 80
LIGHT_BLINK_PERIOD = 1.4  # secondes : clignotement des feux de position
GLOW_RADII = (5, 6, 7, 8)  # tailles de la lueur des moteurs qui pulse


@lru_cache(maxsize=48)
def ship_sprite(w: int, h: int, facing: str, tile_size: int) -> pygame.Surface:
    """Vaisseau vu de dessus dans un rectangle de w × h tuiles, nez vers `facing` (N, E, S ou O), avec son ombre portée."""
    width, height = w * tile_size, h * tile_size
    sideways = facing in ("E", "O")
    cw, ch = (height, width) if sideways else (width, height)  # on dessine toujours nez en haut, puis on tourne
    canvas = pygame.Surface((cw, ch), pygame.SRCALPHA)
    if w * h <= FIGHTER_MAX_TILES:
        _draw_fighter(canvas)
    else:
        _draw_shuttle(canvas)
    angle = {"N": 0, "S": 180, "E": -90, "O": 90}[facing]
    hull = pygame.transform.rotate(canvas, angle) if angle else canvas
    sprite = pygame.Surface(hull.get_size(), pygame.SRCALPHA)
    shadow = pygame.mask.from_surface(hull).to_surface(setcolor=(0, 0, 0, SHIP_SHADOW_ALPHA), unsetcolor=(0, 0, 0, 0))
    sprite.blit(shadow, SHIP_SHADOW)  # l'ombre part toujours du même côté, quel que soit le sens du nez
    sprite.blit(hull, (0, 0))
    return sprite


def _outline(surf, color, points) -> None:
    pygame.draw.polygon(surf, color, points)
    pygame.draw.polygon(surf, COLORS["player_outline"], points, 2)


def _line(surf, color, a, b, width: int = 1) -> None:
    pygame.draw.line(surf, color, (round(a[0]), round(a[1])), (round(b[0]), round(b[1])), width)


def _engine_points(w: float, h: float, fighter: bool) -> list[tuple[float, float]]:
    """Tuyères (repère du vaisseau nez en haut) : là où brille la lueur des moteurs."""
    if fighter:
        return [(w / 2, h * 0.5 + h * 0.26 - 2)]
    return [(w / 2 + dx * w, h - 6) for dx in (-0.09, 0.0, 0.09)]


def _nav_lights(w: float, h: float, fighter: bool) -> list[tuple[float, float, tuple[int, int, int]]]:
    """Feux de position (repère nez en haut) : rouge à bâbord, vert à tribord, comme sur un vrai appareil."""
    if fighter:
        return [(w * 0.5, h * 0.5 - h * 0.2, COLORS["ship_accent"])]
    return [(w / 2 - (w * 0.5 - 7), h * 0.8, (255, 70, 70)), (w / 2 + (w * 0.5 - 7), h * 0.8, (90, 235, 130))]


def _draw_fighter(surf: pygame.Surface) -> None:
    """Chasseur : nacelle sphérique armée entre deux grands panneaux hexagonaux à rayons, reliés par des mâts."""
    w, h = surf.get_size()
    hull, dark, panel = COLORS["ship_hull"], COLORS["ship_hull_dark"], COLORS["ship_panel"]
    outline = COLORS["player_outline"]
    cx = w / 2
    pw, ph = round(w * 0.24), h - 8
    for side in (0, 1):  # panneaux latéraux hexagonaux
        x0 = 3 if side == 0 else w - pw - 3
        y0 = 4
        hexagon = [(x0 + pw / 2, y0), (x0 + pw, y0 + ph * 0.25), (x0 + pw, y0 + ph * 0.75), (x0 + pw / 2, y0 + ph), (x0, y0 + ph * 0.75), (x0, y0 + ph * 0.25)]
        _outline(surf, dark, hexagon)  # cadre
        hub = (x0 + pw / 2, y0 + ph / 2)
        inner = [(hub[0] + (px - hub[0]) * 0.72, hub[1] + (py - hub[1]) * 0.8) for px, py in hexagon]
        pygame.draw.polygon(surf, panel, inner)  # cellule solaire
        for k in range(1, 5):  # rayons de la cellule
            _line(surf, _shade(dark, 0.7), (x0 + 3, y0 + k * ph / 5), (x0 + pw - 3, y0 + k * ph / 5))
        for vertex in hexagon:  # les six rayons du cadre
            _line(surf, _shade(dark, 0.55), hub, vertex)
        pygame.draw.circle(surf, dark, (round(hub[0]), round(hub[1])), 4)  # moyeu où s'attache le mât
        pygame.draw.circle(surf, outline, (round(hub[0]), round(hub[1])), 4, 1)
        _line(surf, _shade(hull, 1.05), (x0 + 3, y0 + ph * 0.28), (x0 + pw - 3, y0 + ph * 0.28))  # reflet sur le cadre
        strut_y = h // 2 - 3
        x_a, x_b = (hub[0] + 3, cx - 8) if side == 0 else (cx + 8, hub[0] - 3)
        strut = pygame.Rect(round(min(x_a, x_b)), strut_y, round(abs(x_b - x_a)), 6)
        pygame.draw.rect(surf, dark, strut)
        pygame.draw.rect(surf, outline, strut, 1)
        _line(surf, _shade(hull, 0.9), (strut.x + 1, strut.y + 1), (strut.right - 1, strut.y + 1))
        for rx in (strut.x + 4, strut.right - 5):  # rivets
            pygame.draw.circle(surf, _shade(hull, 1.1), (rx, strut.centery), 1)
    pod = pygame.Rect(0, 0, round(w * 0.34), round(h * 0.52))
    pod.center = (round(cx), h // 2)
    pygame.draw.ellipse(surf, _shade(hull, 0.78), pod)  # ombre propre de la nacelle (côté droit, plus sombre)
    lit = pod.inflate(-round(pod.w * 0.14), 0)
    lit.x = pod.x
    pygame.draw.ellipse(surf, hull, lit)
    pygame.draw.ellipse(surf, outline, pod, 2)
    for k in (-1, 1):  # canons laser sous la proue
        _line(surf, COLORS["guard_gun"], (cx + k * 5, pod.y + 5), (cx + k * 5, pod.y - 3), 2)
        pygame.draw.circle(surf, outline, (round(cx + k * 5), pod.y - 3), 1)
    ring = pod.inflate(-round(pod.w * 0.22), -round(pod.h * 0.22))
    pygame.draw.ellipse(surf, dark, ring)  # cadre de la verrière
    glass = ring.inflate(-6, -6)
    pygame.draw.ellipse(surf, _shade(COLORS["ship_glass"], 0.7), glass)
    upper = glass.copy()
    upper.h = glass.h // 2
    pygame.draw.ellipse(surf, COLORS["ship_glass"], upper.inflate(-2, 0))
    for k in (-1, 0, 1):  # meneaux
        _line(surf, _shade(COLORS["ship_glass"], 0.45), (glass.centerx + k * glass.w // 4, glass.y + 1), (glass.centerx + k * glass.w // 4, glass.bottom - 1))
    _line(surf, _shade(COLORS["ship_glass"], 0.45), (glass.x + 1, glass.centery), (glass.right - 1, glass.centery))
    pygame.draw.ellipse(surf, _shade(COLORS["ship_glass"], 1.5), glass.inflate(-glass.w // 2, -glass.h // 2).move(-glass.w // 8, -glass.h // 8))  # reflet
    ex, ey = _engine_points(w, h, True)[0]
    grille = pygame.Rect(0, 0, 12, 5)
    grille.center = (round(ex), round(ey))
    pygame.draw.rect(surf, outline, grille.inflate(2, 2), border_radius=2)
    pygame.draw.rect(surf, COLORS["ship_engine"], grille.inflate(-4, -2))  # tuyère
    for k in (-3, 0, 3):
        _line(surf, outline, (grille.centerx + k, grille.y), (grille.centerx + k, grille.bottom - 1))
    pygame.draw.circle(surf, COLORS["ship_accent"], (round(cx), pod.y + 9), 2)  # voyant de la nacelle


def _draw_shuttle(surf: pygame.Surface) -> None:
    """Navette : fuselage effilé et ombré, ailes en flèche armées, dôme radar, verrière, trois tuyères à capot."""
    w, h = surf.get_size()
    hull, dark, panel = COLORS["ship_hull"], COLORS["ship_hull_dark"], COLORS["ship_panel"]
    outline = COLORS["player_outline"]
    cx = w / 2
    # Ailes en flèche (derrière le fuselage) : bord d'attaque éclairé, nervures, canon et feu de bout d'aile.
    for sign in (-1, 1):
        root, tip = cx + sign * w * 0.12, cx + sign * (w * 0.5 - 3)
        wing = [(root, h * 0.34), (tip, h * 0.68), (tip, h * 0.9), (root, h * 0.84)]
        _outline(surf, dark if sign < 0 else _shade(dark, 0.88), wing)
        lead = [wing[0], wing[1], (tip, h * 0.68 + h * 0.07), (root, h * 0.34 + h * 0.08)]
        pygame.draw.polygon(surf, _shade(hull, 0.92), lead)  # bord d'attaque
        for k in (1, 2, 3):  # nervures vers l'arrière
            _line(surf, _shade(dark, 0.7), (root + (tip - root) * 0.08, h * (0.4 + 0.12 * k)), (tip - (tip - root) * 0.06, h * (0.72 + 0.045 * k)))
        _line(surf, panel, (cx + sign * w * 0.2, h * 0.5), (cx + sign * (w * 0.46), h * 0.76))
        barrel_x = cx + sign * (w * 0.5 - 8)
        _line(surf, outline, (barrel_x, h * 0.74), (barrel_x, h * 0.58), 4)  # canon laser de bout d'aile
        _line(surf, COLORS["guard_gun"], (barrel_x, h * 0.74), (barrel_x, h * 0.59), 2)
        pygame.draw.polygon(surf, COLORS["ship_accent"], [(tip - sign * 5, h * 0.8), (tip, h * 0.8), (tip, h * 0.87), (tip - sign * 5, h * 0.87)])  # liseré de couleur
    # Fuselage, ombré : le côté gauche est éclairé, le droit plus sombre.
    body = [(cx, 3), (cx + w * 0.17, h * 0.22), (cx + w * 0.2, h * 0.7), (cx + w * 0.15, h - 5), (cx - w * 0.15, h - 5), (cx - w * 0.2, h * 0.7), (cx - w * 0.17, h * 0.22)]
    pygame.draw.polygon(surf, _shade(hull, 1.06), body)
    right_half = [(cx, 3), (cx + w * 0.17, h * 0.22), (cx + w * 0.2, h * 0.7), (cx + w * 0.15, h - 5), (cx, h - 5)]
    pygame.draw.polygon(surf, _shade(hull, 0.86), right_half)
    pygame.draw.polygon(surf, outline, body, 2)
    _line(surf, dark, (cx, h * 0.3), (cx, h * 0.86), 3)  # arête dorsale
    _line(surf, _shade(hull, 1.2), (cx - 1, h * 0.32), (cx - 1, h * 0.84))
    for y in (0.4, 0.5, 0.6, 0.7, 0.8):  # joints de panneaux
        half = w * (0.17 + 0.03 * min(1.0, max(0.0, (y - 0.22) / 0.48)))
        _line(surf, _shade(dark, 0.8), (cx - half + 2, h * y), (cx + half - 2, h * y))
    for y in (0.36, 0.52, 0.68, 0.82):  # rivets le long des flancs
        for sign in (-1, 1):
            pygame.draw.circle(surf, _shade(hull, 0.7), (round(cx + sign * w * 0.15), round(h * y)), 1)
    chevron = [(cx - w * 0.1, h * 0.46), (cx, h * 0.52), (cx + w * 0.1, h * 0.46), (cx + w * 0.1, h * 0.5), (cx, h * 0.56), (cx - w * 0.1, h * 0.5)]
    pygame.draw.polygon(surf, COLORS["ship_accent"], chevron)  # marquage
    hatch = pygame.Rect(0, 0, round(w * 0.1), round(h * 0.08))
    hatch.center = (round(cx), round(h * 0.68))
    pygame.draw.rect(surf, _shade(dark, 0.8), hatch, border_radius=2)
    pygame.draw.rect(surf, outline, hatch, 1, border_radius=2)  # trappe d'accès
    dish = (round(cx), round(h * 0.4))
    pygame.draw.circle(surf, dark, dish, max(4, round(w * 0.045)))  # dôme radar
    pygame.draw.circle(surf, outline, dish, max(4, round(w * 0.045)), 1)
    pygame.draw.circle(surf, _shade(hull, 1.2), (dish[0] - 1, dish[1] - 1), 1)
    for sign in (-1, 1):  # grilles d'aération à l'arrière
        for k in range(3):
            _line(surf, outline, (cx + sign * w * 0.1 - 3, h * (0.9 - 0.02 * k)), (cx + sign * w * 0.1 + 3, h * (0.9 - 0.02 * k)))
    # Verrière : vitre sombre en bas, claire en haut, meneaux et reflet.
    glass = [(cx, h * 0.07), (cx + w * 0.1, h * 0.2), (cx + w * 0.08, h * 0.3), (cx - w * 0.08, h * 0.3), (cx - w * 0.1, h * 0.2)]
    pygame.draw.polygon(surf, COLORS["ship_glass"], glass)
    pygame.draw.polygon(surf, _shade(COLORS["ship_glass"], 0.7), [(cx - w * 0.08, h * 0.3), (cx + w * 0.08, h * 0.3), (cx + w * 0.09, h * 0.24), (cx - w * 0.09, h * 0.24)])
    pygame.draw.polygon(surf, outline, glass, 1)
    _line(surf, _shade(COLORS["ship_glass"], 0.5), (cx, h * 0.07), (cx, h * 0.3))
    _line(surf, _shade(COLORS["ship_glass"], 0.5), (cx - w * 0.09, h * 0.2), (cx + w * 0.09, h * 0.2))
    _line(surf, _shade(COLORS["ship_glass"], 1.6), (cx - w * 0.04, h * 0.12), (cx - w * 0.06, h * 0.22), 2)
    # Tuyères : capot sombre, anneau, cœur clair.
    for ex, _ey in _engine_points(w, h, False):
        housing = pygame.Rect(0, 0, max(8, round(w * 0.07)), 9)
        housing.midbottom = (round(ex), h - 2)
        pygame.draw.rect(surf, outline, housing.inflate(2, 2), border_radius=2)
        pygame.draw.rect(surf, dark, housing, border_radius=2)
        core = housing.inflate(-4, -4)
        core.bottom = housing.bottom - 1
        pygame.draw.rect(surf, COLORS["ship_engine"], core, border_radius=1)


def ship_hardpoints(w: int, h: int, facing: str, tile_size: int) -> dict[str, list]:
    """Où sont les tuyères et les feux de position d'un vaisseau, en pixels dans son rectangle (selon son orientation)."""
    return _hardpoints(w, h, facing, tile_size)


@lru_cache(maxsize=48)
def _hardpoints(w: int, h: int, facing: str, tile_size: int) -> dict[str, list]:
    width, height = w * tile_size, h * tile_size
    sideways = facing in ("E", "O")
    cw, ch = (height, width) if sideways else (width, height)
    fighter = w * h <= FIGHTER_MAX_TILES

    def to_rect(x: float, y: float) -> tuple[int, int]:  # du repère « nez en haut » au rectangle du vaisseau
        if facing == "N":
            return round(x), round(y)
        if facing == "S":
            return round(cw - x), round(ch - y)
        if facing == "E":
            return round(ch - y), round(x)
        return round(y), round(cw - x)

    return {
        "engines": [to_rect(x, y) for x, y in _engine_points(cw, ch, fighter)],
        "lights": [(*to_rect(x, y), color) for x, y, color in _nav_lights(cw, ch, fighter)],
    }


@lru_cache(maxsize=16)
def _glow(radius: int) -> pygame.Surface:
    """Halo des moteurs : un disque dont la luminosité décroît du centre vers le bord, à ajouter à l'image (BLEND_RGB_ADD)."""
    surf = pygame.Surface((2 * radius, 2 * radius))
    base = COLORS["ship_engine"]
    for k in range(radius, 0, -1):
        level = (1 - k / radius) ** 1.4
        pygame.draw.circle(surf, tuple(round(c * level * 0.9) for c in base), (radius, radius), k)
    return surf


def draw_ship_lights(surface: pygame.Surface, rect: pygame.Rect, prop: Prop, tile_size: int, time: float, boost: float = 0.0) -> None:
    """Animation d'un vaisseau posé : les moteurs veillent (lueur qui pulse, plus forte si `boost` : le vaisseau est prêt à partir),
    les feux de position clignotent."""
    points = ship_hardpoints(prop.w, prop.h, prop.facing, tile_size)
    phase = (prop.x * 0.7 + prop.y * 1.3) % math.tau  # deux vaisseaux ne pulsent pas ensemble
    for i, (x, y) in enumerate(points["engines"]):
        beat = 0.5 + 0.5 * math.sin(time * (3.0 + 4.0 * boost) + phase + i * 0.9)
        glow = _glow(GLOW_RADII[min(len(GLOW_RADII) - 1, int((beat * 0.7 + 0.3 * boost) * len(GLOW_RADII)))] + round(3 * boost))
        surface.blit(glow, (rect.x + x - glow.get_width() // 2, rect.y + y - glow.get_height() // 2), special_flags=pygame.BLEND_RGB_ADD)
    on = (time + phase) % LIGHT_BLINK_PERIOD < LIGHT_BLINK_PERIOD * 0.4
    for x, y, color in points["lights"]:
        center = (rect.x + x, rect.y + y)
        pygame.draw.circle(surface, color if on else _shade(color, 0.25), center, 2)
        if on:
            pygame.draw.circle(surface, (255, 255, 255), center, 1)


# --- Champ de force ----------------------------------------------------------
@lru_cache(maxsize=32)
def _field_base(length: int, thickness: int, vertical: bool) -> pygame.Surface:
    """Fond du champ de force : plaque de pont, nappe d'énergie translucide, pylônes aux deux extrémités."""
    size = (thickness, length) if vertical else (length, thickness)
    surf = pygame.Surface(size, pygame.SRCALPHA)
    w, h = size
    surf.fill((*COLORS["field_deck"], 255))
    mid = w // 2 if vertical else h // 2
    glow, core, edge = COLORS["field_glow"], COLORS["field_core"], COLORS["player_outline"]
    for half, alpha in ((13, 38), (9, 70), (5, 120), (2, 255)):  # nappe : du halo large au cœur très net
        color = (*(core if half == 2 else glow), alpha)
        pygame.draw.rect(surf, color, (mid - half, 0, 2 * half, h) if vertical else (0, mid - half, w, 2 * half))
    for offset in (1, (w if vertical else h) - 2):  # filets sombres sur les bords de la plaque
        if vertical:
            pygame.draw.line(surf, edge, (offset, 0), (offset, h), 1)
        else:
            pygame.draw.line(surf, edge, (0, offset), (w, offset), 1)
    pylon_size = min(thickness, 22)
    for first in (True, False):  # pylônes émetteurs
        if vertical:
            pylon = pygame.Rect(w // 2 - pylon_size // 2, 1 if first else h - pylon_size - 1, pylon_size, pylon_size)
        else:
            pylon = pygame.Rect(1 if first else w - pylon_size - 1, h // 2 - pylon_size // 2, pylon_size, pylon_size)
        pygame.draw.rect(surf, COLORS["door_metal"], pylon, border_radius=4)
        pygame.draw.rect(surf, edge, pylon, 2, border_radius=4)
        pygame.draw.circle(surf, core, pylon.center, 4)
        pygame.draw.circle(surf, (255, 255, 255), pylon.center, 2)
    return surf


def draw_force_field(surface: pygame.Surface, rect: pygame.Rect, time: float) -> None:
    """Champ de force animé : nappe d'énergie, impulsions qui la parcourent, scintillement."""
    vertical = rect.h > rect.w
    length = rect.h if vertical else rect.w
    base = _field_base(length, rect.w if vertical else rect.h, vertical)
    surface.blit(base, rect)
    core = COLORS["field_core"]
    shimmer = 0.78 + 0.22 * math.sin(time * 11 + rect.x * 0.05 + rect.y * 0.05)
    mid = rect.centerx if vertical else rect.centery
    # Impulsions lumineuses qui glissent le long de la nappe.
    count = max(1, length // FIELD_SCAN_SPACING)
    for i in range(count + 1):
        p = (time * FIELD_SCAN_SPEED + i * FIELD_SCAN_SPACING) % (length + FIELD_SCAN_SPACING) - FIELD_SCAN_SPACING / 2
        if not 8 <= p <= length - 8:
            continue
        reach = 10
        color = _shade(core, shimmer)
        if vertical:
            pygame.draw.line(surface, color, (mid - reach, rect.y + p), (mid + reach, rect.y + p), 2)
        else:
            pygame.draw.line(surface, color, (rect.x + p, mid - reach), (rect.x + p, mid + reach), 2)


# --- Champs de force commutables ----------------------------------------------
EMITTER_LONG, EMITTER_SHORT = 24, 12  # dimensions d'un émetteur : côté qui barre le passage, côté épaisseur
PULSE_REACH = 10
FIELD_PULSE_MARGIN = 6  # une impulsion ne s'affiche pas tout contre un émetteur


@lru_cache(maxsize=64)
def _gate_band(length: int, thickness: int, vertical: bool, color: tuple[int, int, int]) -> pygame.Surface:
    """Nappe d'énergie translucide (halo large, cœur net) dans la teinte du groupe, sur fond transparent."""
    surf = pygame.Surface((thickness, length) if vertical else (length, thickness), pygame.SRCALPHA)
    w, h = surf.get_size()
    mid = w // 2 if vertical else h // 2
    core = tuple(min(255, c + 90) for c in color)
    for half, alpha, tint in ((FIELD_GATE_BAND, 40, color), (FIELD_GATE_BAND * 2 // 3, 80, color), (FIELD_GATE_BAND // 3, 140, color), (2, 255, core)):
        rect = (mid - half, 0, 2 * half, h) if vertical else (0, mid - half, w, 2 * half)
        pygame.draw.rect(surf, (*tint, alpha), rect)
    return surf


def _draw_emitter(surface: pygame.Surface, center: tuple[int, int], vertical: bool, color, lit: bool) -> None:
    """Pylône à une extrémité du champ : à cheval sur le mur voisin, avec un voyant."""
    size = (EMITTER_LONG, EMITTER_SHORT) if vertical else (EMITTER_SHORT, EMITTER_LONG)
    block = pygame.Rect(0, 0, *size)
    block.center = center
    pygame.draw.rect(surface, COLORS["door_metal"], block, border_radius=3)
    pygame.draw.rect(surface, COLORS["player_outline"], block, 2, border_radius=3)
    lamp = tuple(min(255, c + 60) for c in color) if lit else _shade(color, 0.28)
    pygame.draw.circle(surface, lamp, center, 3)
    if lit:
        pygame.draw.circle(surface, (255, 255, 255), center, 1)


def draw_gate(surface: pygame.Surface, rect: pygame.Rect, vertical: bool, color: tuple[int, int, int], state: str, time: float = 0.0) -> None:
    """Dessine une ligne de champ commutable. `state` : « active » (bande), « inactive » (émetteurs éteints), « pending » (clignote)."""
    length = rect.h if vertical else rect.w
    thickness = rect.w if vertical else rect.h
    blink_on = int(time * FIELD_PENDING_BLINK * 2) % 2 == 0
    band_on = state == "active" or (state == "pending" and blink_on)
    if band_on:
        band = _gate_band(length, thickness, vertical, tuple(color))
        shimmer_alpha = 235 + round(20 * math.sin(time * 9 + rect.x * 0.07 + rect.y * 0.07))
        band.set_alpha(shimmer_alpha if state == "active" else 170)
        surface.blit(band, rect)
        mid = rect.centerx if vertical else rect.centery
        shimmer = 0.8 + 0.2 * math.sin(time * 11 + rect.x * 0.05 + rect.y * 0.05)
        pulse_color = _shade(tuple(min(255, c + 110) for c in color), shimmer)
        spacing = min(FIELD_SCAN_SPACING, max(length, 2 * FIELD_PULSE_MARGIN))  # une ligne courte reste animée
        for i in range(length // spacing + 1):  # impulsions qui parcourent la bande
            p = (time * FIELD_SCAN_SPEED + i * spacing) % (length + spacing) - spacing / 2
            if FIELD_PULSE_MARGIN <= p <= length - FIELD_PULSE_MARGIN:
                a, b = ((mid - PULSE_REACH, rect.y + p), (mid + PULSE_REACH, rect.y + p)) if vertical else ((rect.x + p, mid - PULSE_REACH), (rect.x + p, mid + PULSE_REACH))
                pygame.draw.line(surface, pulse_color, a, b, 2)
    else:  # champ ouvert : seul un pointillé très discret rappelle où il barrait le passage
        dim = _shade(color, 0.3)
        for p in range(8, length - 4, 10):
            pygame.draw.circle(surface, dim, (rect.centerx, rect.y + p) if vertical else (rect.x + p, rect.centery), 1)
    lit = state == "active" or (state == "pending" and blink_on)
    ends = ((rect.centerx, rect.top), (rect.centerx, rect.bottom)) if vertical else ((rect.left, rect.centery), (rect.right, rect.centery))
    for end in ends:
        _draw_emitter(surface, end, vertical, color, lit)


TRACTOR_COLOR = (90, 210, 255)
CLAMP_REACH = 11  # px : de combien une attache s'écarte de la coque en s'ouvrant
CLAMP_LENGTH = 12


def draw_tractor_beam(surface: pygame.Surface, rect: pygame.Rect, prop: Prop, time: float, hold: float) -> None:
    """Rayon tracteur qui retient un vaisseau : des anneaux qui se resserrent sur lui, sous la coque. S'éteint avec `hold` (0 -> 1)."""
    strength = 1.0 - hold
    if strength <= 0.02:
        return
    margin = 26
    overlay = pygame.Surface((rect.w + 2 * margin, rect.h + 2 * margin), pygame.SRCALPHA)
    base = overlay.get_rect().inflate(-2 * 8, -2 * 8)
    pygame.draw.ellipse(overlay, (*TRACTOR_COLOR, round(46 * strength)), base)
    phase = (prop.x * 0.31 + prop.y * 0.17) % 1.0
    for i in range(3):  # des anneaux qui convergent vers le vaisseau
        p = (time * 0.7 + phase + i / 3) % 1.0
        ring = base.inflate(round(2 * margin * (1 - p) * 0.8), round(2 * margin * (1 - p) * 0.8))
        pygame.draw.ellipse(overlay, (*TRACTOR_COLOR, round(190 * strength * (0.25 + 0.75 * p) * (1 - 0.3 * p))), ring, 2)
    surface.blit(overlay, (rect.x - margin, rect.y - margin))


def draw_clamps(surface: pygame.Surface, rect: pygame.Rect, prop: Prop, hold: float) -> None:
    """Quatre attaches qui serrent la coque (deux de chaque côté) et s'écartent quand le vaisseau est libéré, voyant rouge puis vert."""
    open_amount = min(1.0, hold)
    lamp = (255, 70, 70) if hold < 0.5 else (90, 235, 130)
    for fy in (0.25, 0.75):
        y = rect.y + round(rect.h * fy)
        for side in (-1, 1):
            edge = rect.x + 4 if side < 0 else rect.right - 4  # sur la coque
            tip = edge + side * round(CLAMP_REACH * open_amount)  # la pince recule vers l'extérieur en s'ouvrant
            base = edge + side * CLAMP_LENGTH
            arm = pygame.Rect(min(tip, base), y - 3, abs(base - tip), 6)
            pygame.draw.rect(surface, COLORS["player_outline"], arm.inflate(2, 2))
            pygame.draw.rect(surface, COLORS["door_metal"], arm)
            jaw = pygame.Rect(tip - 2 if side < 0 else tip - 1, y - 5, 3, 10)  # mâchoire
            pygame.draw.rect(surface, COLORS["hazard_yellow"], jaw)
            pygame.draw.rect(surface, COLORS["player_outline"], jaw, 1)
            pygame.draw.circle(surface, lamp, (base - side * 3, y), 1)


def draw_boarding_marker(surface: pygame.Surface, rect: pygame.Rect, time: float) -> None:
    """Flèche verte qui rebondit au-dessus du vaisseau à voler, quand il est libre de partir."""
    bounce = round(3 * math.sin(time * 4.0))
    x, y = rect.centerx, rect.y - 12 + bounce
    pts = [(x - 7, y - 6), (x + 7, y - 6), (x, y + 4)]
    pygame.draw.polygon(surface, COLORS["player_outline"], [(px, py + (1 if py > y else 0)) for px, py in pts], 0)
    pygame.draw.polygon(surface, COLORS["status_calm"], [(x - 5, y - 5), (x + 5, y - 5), (x, y + 2)])


def draw_prop(surface: pygame.Surface, prop: Prop, screen_rect: pygame.Rect, tile_size: int, time: float = 0.0, hold: float | None = None, target: bool = False) -> None:
    """Dessine un prop dans `screen_rect` (son rectangle à l'écran). `hold` (vaisseaux, objectif « voler un vaisseau ») :
    0 = rayon tracteur et attaches actifs, 1 = libéré ; None : le vaisseau n'est pas retenu. `target` : le vaisseau à voler."""
    if prop.kind == FIELD_KIND:
        draw_force_field(surface, screen_rect, time)
    elif prop.kind == SHIP_KIND:
        if hold is not None:
            draw_tractor_beam(surface, screen_rect, prop, time, hold)
        surface.blit(ship_sprite(prop.w, prop.h, prop.facing, tile_size), screen_rect)
        if hold is not None:
            draw_clamps(surface, screen_rect, prop, hold)
        draw_ship_lights(surface, screen_rect, prop, tile_size, time, boost=hold or 0.0)
        if hold is not None and target and hold >= 0.9:
            draw_boarding_marker(surface, screen_rect, time)
    elif prop.kind == BOX_KIND:
        surface.blit(box_sprite(prop.w, prop.h, _variant(prop, len(CONTAINER_PALETTE)), tile_size), screen_rect)
