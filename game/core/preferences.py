"""Préférences du joueur (volumes, éclairage, plein écran, difficulté), sauvegardées en JSON.

Le fichier est tolérant : absent, illisible ou partiellement faux, le jeu retombe sur les valeurs par défaut
au lieu de planter. `STAR_INFILTRATION_HOME` permet de rediriger le dossier (tests, installation portable).
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from game.settings import DEFAULT_DIFFICULTY, DEFAULT_VOLUMES, DIFFICULTIES

HOME_ENV = "STAR_INFILTRATION_HOME"
FILE_NAME = "preferences.json"


def default_path() -> Path:
    home = os.environ.get(HOME_ENV)
    base = Path(home) if home else Path.home() / ".star-infiltration"
    return base / FILE_NAME


def _volume(value, default: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return round(max(0.0, min(1.0, float(value))), 2)


@dataclass
class Preferences:
    master: float = DEFAULT_VOLUMES["master"]
    music: float = DEFAULT_VOLUMES["music"]
    sfx: float = DEFAULT_VOLUMES["sfx"]
    lighting: bool = True
    screen_shake: bool = True  # secousses de la caméra (alerte, coupure de courant...) : désactivables
    fullscreen: bool = False
    gamepad: bool = True  # utiliser une manette si on en branche une
    keys: dict = field(default_factory=dict)  # touches remappées (voir `bindings.py`) : action -> noms de touches
    difficulty: str = DEFAULT_DIFFICULTY
    path: Path | None = field(default=None, repr=False, compare=False)  # où sauvegarder (non écrit dans le fichier)

    @classmethod
    def load(cls, path: Path | None = None) -> Preferences:
        path = Path(path) if path else default_path()
        prefs = cls(path=path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return prefs
        if not isinstance(data, dict):
            return prefs
        for name in ("master", "music", "sfx"):
            setattr(prefs, name, _volume(data.get(name), getattr(prefs, name)))
        for name in ("lighting", "fullscreen", "screen_shake", "gamepad"):
            if isinstance(data.get(name), bool):
                setattr(prefs, name, data[name])
        if isinstance(data.get("keys"), dict):
            prefs.keys = {k: v for k, v in data["keys"].items() if isinstance(k, str)}
        if data.get("difficulty") in DIFFICULTIES:
            prefs.difficulty = data["difficulty"]
        return prefs

    def save(self) -> bool:
        """Écrit le fichier (de façon atomique). Renvoie faux si le disque refuse : on ne plante jamais pour ça."""
        path = self.path or default_path()
        payload = {k: v for k, v in asdict(self).items() if k != "path"}
        tmp = path.with_suffix(".tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            os.replace(tmp, path)
        except OSError:
            return False
        return True
