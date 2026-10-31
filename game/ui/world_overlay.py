"""Calque d'indicateurs dans le monde : cônes de vision et bulles d'alerte des gardes."""
from __future__ import annotations

import math

import pygame

from game.ai.guard import Guard, GuardState
from game.ai.perception import vision_points
from game.settings import CAMERA_FOV, CAMERA_RANGE, COLORS, GUARD_FOV, GUARD_VISION_RANGE, GUARD_VISION_RAYS

# (échelle, opacité) : trois cônes emboîtés, plus denses près du garde, pour un dégradé.
CONE_LAYERS = ((1.0, 34), (0.66, 46), (0.33, 62))
CONE_EDGE_ALPHA = 110

BUBBLE_RADIUS = 11
BUBBLE_OFFSET_Y = 32  # au-dessus du centre du garde
BUBBLE_RING_WIDTH = 3
BUBBLE_PULSE = 1.6  # amplitude (px) du battement de la bulle en poursuite
BUBBLE_PULSE_SPEED = 14.0  # rad/s
AWARENESS_VISIBLE_MIN = 0.02  # en dessous, la bulle d'un garde calme reste cachée


def lerp_color(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


class WorldOverlay:
    def __init__(self, size: tuple[int, int]) -> None:
        self._layer = pygame.Surface(size, pygame.SRCALPHA)
        self._font = pygame.font.Font(None, 26)
        self._small = pygame.font.Font(None, 18)
        self._glyphs: dict[str, pygame.Surface] = {}

    # --- Sous les entités : cônes de vision -----------------------------------
    def draw_under(self, surface: pygame.Surface, camera, tilemap, guards: list[Guard], cameras=()) -> None:
        reach = camera.visible_rect.inflate(2 * GUARD_VISION_RANGE, 2 * GUARD_VISION_RANGE)
        visible = [g for g in guards if reach.collidepoint(g.pos)]
        cam_reach = camera.visible_rect.inflate(2 * CAMERA_RANGE, 2 * CAMERA_RANGE)
        watching = [c for c in cameras if c.active and cam_reach.collidepoint(c.pos)]
        if not visible and not watching:
            return
        if self._layer.get_size() != surface.get_size():
            self._layer = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        self._layer.fill((0, 0, 0, 0))

        for guard in visible:
            self._draw_cone(camera, tilemap, guard)
        for security_camera in watching:
            self._draw_camera_cone(camera, tilemap, security_camera)
        surface.blit(self._layer, (0, 0))

    def _draw_camera_cone(self, camera, tilemap, security_camera) -> None:
        """Le cône d'une caméra : bleuté tant qu'elle ne voit rien, il vire au rouge quand elle repère le joueur."""
        heat = 1.0 if security_camera.alarmed else security_camera.awareness
        r, g, b = lerp_color(COLORS["camera_cone"], COLORS["cone_chase"], heat)
        eye = camera.world_to_screen(security_camera.pos)
        rim = [
            camera.world_to_screen(p)
            for p in vision_points(tilemap, security_camera.pos, security_camera.angle, CAMERA_FOV, CAMERA_RANGE, GUARD_VISION_RAYS)
        ]
        for scale, alpha in CONE_LAYERS:
            shape = [eye] + [(eye[0] + (x - eye[0]) * scale, eye[1] + (y - eye[1]) * scale) for x, y in rim]
            pygame.draw.polygon(self._layer, (r, g, b, alpha), shape)
        pygame.draw.lines(self._layer, (r, g, b, CONE_EDGE_ALPHA), False, [eye, *rim, eye], 1)

    def _draw_cone(self, camera, tilemap, guard: Guard) -> None:
        heat = 1.0 if guard.state is GuardState.CHASE else guard.awareness
        r, g, b = lerp_color(COLORS[f"cone_{guard.state.value}"], COLORS["cone_chase"], heat)

        eye = camera.world_to_screen(guard.pos)
        rim = [
            camera.world_to_screen(p)
            for p in vision_points(tilemap, guard.pos, guard.angle, GUARD_FOV, GUARD_VISION_RANGE, GUARD_VISION_RAYS)
        ]
        for scale, alpha in CONE_LAYERS:
            shape = [eye] + [(eye[0] + (x - eye[0]) * scale, eye[1] + (y - eye[1]) * scale) for x, y in rim]
            pygame.draw.polygon(self._layer, (r, g, b, alpha), shape)
        pygame.draw.lines(self._layer, (r, g, b, CONE_EDGE_ALPHA), False, [eye, *rim, eye], 1)

    # --- Au-dessus des entités : bulles d'alerte -----------------------------
    def draw_over(self, surface: pygame.Surface, camera, guards: list[Guard], *, debug: bool = False) -> None:
        view = camera.visible_rect.inflate(BUBBLE_OFFSET_Y * 2, BUBBLE_OFFSET_Y * 2)
        for guard in guards:
            if not view.collidepoint(guard.pos):
                continue
            x, y = camera.world_to_screen(guard.pos)
            center = (x, y - BUBBLE_OFFSET_Y)
            self._draw_bubble(surface, center, guard)
            if debug:
                label = f"{guard.state.value} {guard.awareness:.0%}"
                text = self._small.render(label, True, COLORS["text"])
                surface.blit(text, text.get_rect(midbottom=(center[0], center[1] - BUBBLE_RADIUS - 3)))

    def _draw_bubble(self, surface: pygame.Surface, center: tuple[int, int], guard: Guard) -> None:
        if guard.state is GuardState.CHASE:
            glyph, fill, color = "!", 1.0, COLORS["cone_chase"]
            pulse = BUBBLE_PULSE * math.sin(pygame.time.get_ticks() / 1000 * BUBBLE_PULSE_SPEED)
        elif guard.state is GuardState.PATROL:
            if guard.awareness < AWARENESS_VISIBLE_MIN:
                return
            glyph, fill, pulse = "?", guard.awareness, 0.0
            color = lerp_color(COLORS["cone_patrol"], COLORS["cone_chase"], guard.awareness)
        else:  # enquête / fouille
            glyph, fill, pulse, color = "?", 1.0, 0.0, COLORS["cone_investigate"]

        radius = round(BUBBLE_RADIUS + pulse)
        pygame.draw.circle(surface, COLORS["alert_bubble"], center, radius)
        pygame.draw.circle(surface, lerp_color(COLORS["alert_bubble"], color, 0.25), center, radius, BUBBLE_RING_WIDTH)
        if fill >= 1.0:
            pygame.draw.circle(surface, color, center, radius, BUBBLE_RING_WIDTH)
        else:  # jauge qui se remplit dans le sens inverse des aiguilles d'une montre, depuis le haut
            rect = pygame.Rect(0, 0, 2 * radius, 2 * radius)
            rect.center = center
            start = math.pi / 2
            pygame.draw.arc(surface, color, rect, start, start + math.tau * fill, BUBBLE_RING_WIDTH)
        text = self._glyph(glyph)
        surface.blit(text, text.get_rect(center=center))

    def _glyph(self, char: str) -> pygame.Surface:
        if char not in self._glyphs:
            self._glyphs[char] = self._font.render(char, True, COLORS["alert_glyph"])
        return self._glyphs[char]
