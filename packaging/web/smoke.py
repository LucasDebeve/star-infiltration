"""Vérifie la version web dans un vrai navigateur (Chromium, via Playwright) : `python packaging/web/smoke.py <dossier> [capture.png]`.

`<dossier>` est le contenu de l'archive web (celui qui contient `index.html`). Le script le sert en local, l'ouvre, clique (le
navigateur exige un geste de l'utilisateur avant de lancer le son), laisse le jeu démarrer, puis échoue si la console du navigateur
montre une erreur Python (`Traceback`, `Error`) ou si la page reste vide. Il enregistre une capture. pygbag charge son moteur depuis
Internet : à lancer avec une connexion. Prérequis : `pip install playwright && playwright install chromium`.
"""

from __future__ import annotations

import functools
import http.server
import sys
import threading
from pathlib import Path

WAIT_MS = 25_000  # le temps de télécharger le moteur Python/WebAssembly et de lancer le menu
MAX_WAIT_MS = 120_000  # on sonde la capture jusqu'à ce délai : un runner lent met plus longtemps à charger le moteur
POLL_MS = 5_000
BAD_MARKERS = ("Traceback", "Uncaught", "ModuleNotFoundError", "ImportError", "pygame.error", "Error:")
IGNORED = ("favicon", "net::ERR_BLOCKED_BY_CLIENT", "AudioContext")  # bruit sans conséquence


def console_problems(messages: list[str]) -> list[str]:
    """Les messages de la console qui trahissent une erreur du jeu (pur : testé sans navigateur)."""
    return [m for m in messages if any(marker in m for marker in BAD_MARKERS) and not any(ignored in m for ignored in IGNORED)]


def is_blank(pixels: set[tuple[int, int, int]] | list, threshold: int = 8) -> bool:
    """Vrai si la capture n'a (presque) qu'une couleur : la page n'a rien dessiné."""
    return len(set(pixels)) < threshold


def pixels_of(image) -> list:
    """Les pixels d'une image Pillow (`getdata` est déprécié depuis Pillow 12, `get_flattened_data` le remplace)."""
    getter = getattr(image, "get_flattened_data", None) or image.getdata
    return list(getter())


def shot_is_blank(path: Path) -> bool:
    from PIL import Image

    return is_blank(pixels_of(Image.open(path).convert("RGB").resize((64, 36))))


def serve(directory: Path) -> tuple[http.server.ThreadingHTTPServer, int]:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    directory = Path(argv[0])
    shot = Path(argv[1]) if len(argv) > 1 else Path("web-smoke.png")
    if not (directory / "index.html").exists():
        print(f"PROBLÈME : {directory}/index.html est introuvable")
        return 1
    from playwright.sync_api import sync_playwright

    server, port = serve(directory)
    messages: list[str] = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            page.on("console", lambda m: messages.append(m.text))
            page.on("pageerror", lambda e: messages.append(f"Uncaught {e}"))
            page.on("requestfailed", lambda r: print("requête échouée :", r.url, r.failure))
            page.goto(f"http://127.0.0.1:{port}/index.html")
            page.wait_for_selector("canvas", timeout=WAIT_MS)
            page.mouse.click(640, 360)  # geste utilisateur : sans lui, pygbag attend « Ready to start »
            page.wait_for_timeout(WAIT_MS)
            page.screenshot(path=str(shot))
            waited = WAIT_MS
            while shot_is_blank(shot) and waited < MAX_WAIT_MS:  # moteur encore en téléchargement : on réessaie
                page.wait_for_timeout(POLL_MS)
                waited += POLL_MS
                page.screenshot(path=str(shot))
            browser.close()
    finally:
        server.shutdown()
    problems = console_problems(messages)
    if shot_is_blank(shot):
        problems.append("la capture est vide : le jeu n'a rien dessiné")
        print("Console du navigateur :", *messages[-30:], sep="\n  ")
    for problem in problems:
        print("PROBLÈME :", problem)
    print("Version web : " + ("OK." if not problems else f"{len(problems)} problème(s)."), f"Capture : {shot}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
