"""Contrôle d'intégrité du jeu livré (`python main.py --check`) : utile pour valider un exécutable ou un paquet sans ouvrir de fenêtre.

Vérifie que la campagne se charge, que chaque carte est jouable (`check_level`) et que les sons déclarés par le code sont présents.
Renvoie la liste des problèmes : vide, tout va bien.
"""
from __future__ import annotations

from game.settings import AMBIENT_SOURCES, SOUNDS_DIR

# Sons que le code joue par leur nom (les autres sont des musiques ou des ambiances déclarées ailleurs).
REQUIRED_SOUNDS = (
    "step_walk", "door_open", "door_denied", "pickup", "hack_tick", "hack_done", "decoy_throw", "decoy_beep", "suspect", "spotted",
    "alert", "reinforcements", "lockdown", "caught", "win", "ui_move", "ui_select", "ui_back", "music_ambient",
)
OPTIONAL_SOUNDS = ("generique",)  # absent : le générique défile en silence (et la version web l'écarte pour rester légère)


def run_checks() -> list[str]:
    from game.campaign import load_campaign
    from game.world.level_check import check_level
    from game.world.tilemap import Tilemap

    problems: list[str] = []
    try:
        campaign = load_campaign()
    except (ValueError, OSError) as error:
        return [str(error)]
    for mission in campaign.missions:
        try:
            tilemap = Tilemap.from_file(mission.map_path)
        except (ValueError, OSError) as error:
            problems.append(f"{mission.id} : {error}")
            continue
        problems += [f"{mission.id} : {p}" for p in check_level(tilemap)]
    names = set(REQUIRED_SOUNDS) | {sound for sound, _, _ in AMBIENT_SOURCES.values()}
    problems += [
        f"son manquant : {name}.wav" for name in sorted(names) if not any((SOUNDS_DIR / f"{name}{ext}").exists() for ext in (".wav", ".ogg"))
    ]
    return problems
