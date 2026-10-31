"""Icône de l'application : dessinée par le code (pas d'image source à tenir à jour), écrite en PNG, ICO (Windows) et ICNS (macOS).

`python packaging/icons.py` régénère `packaging/icons/` et `assets/icon.png` (l'icône de la fenêtre). Les écrivains de formats sont
purs (octets en entrée, octets en sortie) : ICO et ICNS n'embarquent que des PNG, sans dépendance à Pillow.
"""
from __future__ import annotations

import math
import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "packaging" / "icons"
PNG_SIZES = (16, 32, 48, 64, 128, 256, 512, 1024)
ICO_SIZES = (16, 32, 48, 64, 128, 256)
ICNS_TYPES = {16: b"icp4", 32: b"icp5", 64: b"icp6", 128: b"ic07", 256: b"ic08", 512: b"ic09", 1024: b"ic10"}  # types ICNS qui contiennent un PNG
MASTER = 1024


def render_master() -> pygame.Surface:
    """L'icône en grand : un cône de vision rouge qui balaie l'obscurité, et l'agent (point cyan) qui passe dans l'ombre, près d'une étoile."""
    size = MASTER
    surface = pygame.Surface((size, size), pygame.SRCALPHA)
    center = size / 2
    # Fond : carré arrondi dégradé du bleu nuit au noir.
    background = pygame.Surface((size, size), pygame.SRCALPHA)
    for y in range(size):
        t = y / size
        pygame.draw.line(background, (int(18 + 10 * (1 - t)), int(24 + 16 * (1 - t)), int(44 + 26 * (1 - t)), 255), (0, y), (size, y))
    mask = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), (0, 0, size, size), border_radius=int(size * 0.22))
    background.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    surface.blit(background, (0, 0))
    # Étoiles lointaines (positions fixes : l'icône est toujours la même).
    for i in range(46):
        x = (i * 397 + 113) % size
        y = (i * 241 + 59) % size
        if math.hypot(x - center, y - center) < size * 0.46:
            pygame.draw.circle(surface, (170, 190, 230, 120 + (i * 37) % 100), (x, y), 2 + i % 3)
    # Cône de vision d'un garde (en haut à gauche vers le bas droite).
    cone = pygame.Surface((size, size), pygame.SRCALPHA)
    apex = pygame.Vector2(size * 0.24, size * 0.22)
    for step in range(14):
        reach = size * (1.02 - step * 0.05)
        alpha = 20 + step * 7
        points = [apex]
        for k in range(21):
            angle = math.radians(18 + k * 2.2)
            points.append(apex + pygame.Vector2(math.cos(angle), math.sin(angle)) * reach)
        pygame.draw.polygon(cone, (230, 70, 80, alpha), points)
    clip = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.rect(clip, (255, 255, 255, 255), (0, 0, size, size), border_radius=int(size * 0.22))
    cone.blit(clip, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    surface.blit(cone, (0, 0))
    # Le garde, au sommet du cône.
    pygame.draw.circle(surface, (40, 44, 58, 255), apex, size * 0.07)
    pygame.draw.circle(surface, (230, 70, 80, 255), apex, size * 0.07, int(size * 0.012))
    # L'agent : un disque cyan avec un halo, et l'étoile à quatre branches de la rébellion à côté.
    agent = pygame.Vector2(size * 0.66, size * 0.7)
    for radius, alpha in ((0.17, 28), (0.13, 40), (0.1, 60)):  # pygame.draw écrase les pixels : chaque halo est posé par un blit
        halo = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(halo, (90, 220, 240, alpha), agent, size * radius)
        surface.blit(halo, (0, 0))
    pygame.draw.circle(surface, (120, 232, 245, 255), agent, size * 0.075)
    pygame.draw.circle(surface, (20, 60, 80, 255), agent, size * 0.075, int(size * 0.014))
    sparkle = pygame.Vector2(size * 0.8, size * 0.24)
    arm, waist = size * 0.13, size * 0.028
    points = []
    for k in range(8):
        angle = math.radians(k * 45 - 90)
        r = arm if k % 2 == 0 else waist
        points.append(sparkle + pygame.Vector2(math.cos(angle), math.sin(angle)) * r)
    pygame.draw.polygon(surface, (250, 238, 190, 255), points)
    return surface


def render(size: int, master: pygame.Surface | None = None) -> pygame.Surface:
    master = master or render_master()
    return pygame.transform.smoothscale(master, (size, size)) if size != master.get_width() else master.copy()


def png_bytes(surface: pygame.Surface) -> bytes:
    import io

    buffer = io.BytesIO()
    pygame.image.save(surface, buffer, "icon.png")
    return buffer.getvalue()


def build_ico(images: dict[int, bytes]) -> bytes:
    """Fichier .ico de PNG (`taille -> octets du PNG`) : en-tête, répertoire, puis les images (256 s'écrit 0)."""
    sizes = sorted(images)
    header = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    directory, data = b"", b""
    for size in sizes:
        png = images[size]
        directory += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(png), offset + len(data))
        data += png
    return header + directory + data


def build_icns(images: dict[int, bytes]) -> bytes:
    """Fichier .icns : suite d'éléments `type + longueur + PNG`. Les tailles sans type ICNS connu sont ignorées."""
    body = b""
    for size in sorted(images):
        kind = ICNS_TYPES.get(size)
        if kind is not None:
            body += kind + struct.pack(">I", len(images[size]) + 8) + images[size]
    return b"icns" + struct.pack(">I", len(body) + 8) + body


def generate(out_dir: Path = OUT, window_icon: Path | None = ROOT / "assets" / "icon.png") -> list[Path]:
    pygame.init()
    master = render_master()
    pngs = {size: png_bytes(render(size, master)) for size in PNG_SIZES}
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for size, data in pngs.items():
        path = out_dir / f"icon_{size}.png"
        path.write_bytes(data)
        written.append(path)
    (out_dir / "star_infiltration.ico").write_bytes(build_ico({s: pngs[s] for s in ICO_SIZES}))
    (out_dir / "star_infiltration.icns").write_bytes(build_icns(pngs))
    written += [out_dir / "star_infiltration.ico", out_dir / "star_infiltration.icns"]
    if window_icon is not None:
        window_icon.write_bytes(pngs[256])
        written.append(window_icon)
    return written


if __name__ == "__main__":
    for path in generate():
        print(path.relative_to(ROOT))
    sys.exit(0)
