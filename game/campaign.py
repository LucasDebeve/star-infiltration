"""Campagne : la liste ordonnée des missions, leurs textes de générique, et le déblocage progressif.

Les missions viennent d'un fichier JSON (`assets/campaign.json`) : ajouter une mission, c'est ajouter une entrée,
sans toucher au code. Une mission se débloque en terminant la précédente (la première l'est dès le départ).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from game.objectives import DEFAULT_OBJECTIVE, OBJECTIVES
from game.progress import MissionRecord, Progress, rank_index
from game.settings import CAMPAIGN_FILE, MAPS_DIR, RANKS

ID_PATTERN = re.compile(r"^[a-z0-9_]+$")
MAX_DANGER = 5


@dataclass(frozen=True)
class Mission:
    id: str
    title: str
    map_path: Path
    par_time: float  # secondes : le temps qui donne le plein de points de temps
    summary: str  # une phrase, affichée sur la carte de la campagne
    episode: str  # « ÉPISODE I » dans le générique
    intro: tuple[str, ...]  # paragraphes du texte défilant
    prologue: str | None = None  # phrase d'accroche bleue avant le générique (facultative)
    danger: int = 1  # menace de 1 (tranquille) à 5 (la plus dure), affichée sur la carte de la campagne
    objective: str = DEFAULT_OBJECTIVE  # identifiant dans `game.objectives` (la carte doit en porter le point)


class Campaign:
    def __init__(self, missions: list[Mission]) -> None:
        if not missions:
            raise ValueError("Une campagne a besoin d'au moins une mission")
        self.missions = tuple(missions)

    def get(self, mission_id: str) -> Mission:
        return next(m for m in self.missions if m.id == mission_id)

    def index_of(self, mission: Mission) -> int:
        return self.missions.index(mission)

    def next_after(self, mission: Mission) -> Mission | None:
        i = self.index_of(mission)
        return self.missions[i + 1] if i + 1 < len(self.missions) else None

    def is_unlocked(self, mission: Mission, progress: Progress) -> bool:
        """La première mission est libre ; chacune des autres demande d'avoir terminé la précédente."""
        i = self.index_of(mission)
        return i == 0 or progress.is_completed(self.missions[i - 1].id)

    def current(self, progress: Progress) -> Mission:
        """La première mission débloquée et pas encore terminée (à défaut, la dernière)."""
        for mission in self.missions:
            if self.is_unlocked(mission, progress) and not progress.is_completed(mission.id):
                return mission
        return self.missions[-1]


LOCKED, AVAILABLE, COMPLETED = "locked", "available", "completed"
OBTAINED, REACHABLE, BEATEN, HIDDEN = "obtained", "reachable", "beaten", "hidden"


def mission_status(campaign: Campaign, mission: Mission, progress: Progress) -> str:
    """Verrouillée, disponible (débloquée, jamais terminée) ou terminée."""
    if progress.is_completed(mission.id):
        return COMPLETED
    return AVAILABLE if campaign.is_unlocked(mission, progress) else LOCKED


def rank_ladder(record: MissionRecord | None, status: str) -> list[tuple[str, str, int, str]]:
    """Les rangs d'une mission : (lettre, nom, score minimum, état).

    obtenu : le meilleur rang décroché ; accessible : un rang qu'on peut encore viser (tous, tant que la mission n'est
    pas terminée ; les meilleurs que le rang obtenu ensuite) ; dépassé : moins bon que le rang obtenu ;
    caché : mission verrouillée, on ne montre pas encore ce qu'on peut y gagner.
    """
    ladder = []
    for letter, name, minimum in RANKS:
        if status == LOCKED:
            state = HIDDEN
        elif record is None:
            state = REACHABLE
        elif letter == record.best_rank:
            state = OBTAINED
        else:
            state = REACHABLE if rank_index(letter) < rank_index(record.best_rank) else BEATEN
        ladder.append((letter, name, minimum, state))
    return ladder


def _fail(message: str) -> ValueError:
    return ValueError(f"Campagne : {message}")


def _text(raw: dict, key: str, where: str, *, required: bool = True) -> str | None:
    value = raw.get(key)
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip():
        raise _fail(f"{where} : le champ '{key}' doit être un texte non vide")
    return value.strip()


def load_campaign(path: Path = CAMPAIGN_FILE, maps_dir: Path = MAPS_DIR) -> Campaign:
    """Lit et vérifie la campagne. Erreurs (ValueError) en français, avec la mission concernée."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as error:
        raise _fail(f"fichier illisible ({error})") from None
    except ValueError as error:
        raise _fail(f"JSON invalide ({error})") from None
    entries = data.get("missions") if isinstance(data, dict) else None
    if not isinstance(entries, list) or not entries:
        raise _fail("il faut une liste 'missions' non vide")

    missions, seen = [], set()
    for number, raw in enumerate(entries, start=1):
        where = f"mission {number}"
        if not isinstance(raw, dict):
            raise _fail(f"{where} : une entrée doit être un objet")
        mission_id = _text(raw, "id", where)
        where = f"mission {number} ('{mission_id}')"
        if not ID_PATTERN.match(mission_id):
            raise _fail(f"{where} : l'identifiant doit contenir seulement a-z, 0-9 et _")
        if mission_id in seen:
            raise _fail(f"{where} : identifiant déjà utilisé")
        seen.add(mission_id)
        par = raw.get("par_time")
        if isinstance(par, bool) or not isinstance(par, (int, float)) or par <= 0:
            raise _fail(f"{where} : 'par_time' doit être un nombre de secondes positif")
        intro = raw.get("intro")
        if not isinstance(intro, list) or not intro or not all(isinstance(p, str) and p.strip() for p in intro):
            raise _fail(f"{where} : 'intro' doit être une liste de paragraphes non vides")
        objective = raw.get("objective", DEFAULT_OBJECTIVE)
        if objective not in OBJECTIVES:
            raise _fail(f"{where} : objectif inconnu '{objective}' (attendu : {', '.join(OBJECTIVES)})")
        if not OBJECTIVES[objective].playable:
            raise _fail(f"{where} : l'objectif '{objective}' n'est pas encore jouable")
        danger = raw.get("danger", 1)
        if isinstance(danger, bool) or not isinstance(danger, int) or not 1 <= danger <= MAX_DANGER:
            raise _fail(f"{where} : 'danger' doit être un entier de 1 à {MAX_DANGER}")
        map_path = Path(maps_dir) / _text(raw, "map", where)
        if not map_path.exists():
            raise _fail(f"{where} : la carte {map_path.name} est introuvable dans {Path(maps_dir)}")
        missions.append(
            Mission(
                id=mission_id,
                title=_text(raw, "title", where),
                map_path=map_path,
                par_time=float(par),
                summary=_text(raw, "summary", where),
                episode=_text(raw, "episode", where),
                intro=tuple(p.strip() for p in intro),
                prologue=_text(raw, "prologue", where, required=False),
                objective=objective,
                danger=danger,
            )
        )
    return Campaign(missions)
