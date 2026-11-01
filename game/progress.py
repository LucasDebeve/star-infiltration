"""Statistiques d'une mission, score, rang, et progression sauvegardée (missions terminées, meilleurs scores).

Logique pure et sans fenêtre. Le fichier de progression est tolérant comme celui des préférences : absent, illisible
ou partiellement faux, on repart de ce qui est valide au lieu de planter.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from game.core.preferences import default_path as _preferences_path
from game.settings import (
    RANKS,
    SCORE_ALERT_MAX,
    SCORE_ALERT_PENALTY,
    SCORE_DECOY_MAX,
    SCORE_DECOY_PENALTY,
    SCORE_TIME_MAX,
    SCORE_TIME_PENALTY,
)

FILE_NAME = "progress.json"
RANK_LETTERS = tuple(letter for letter, _, _ in RANKS)  # du meilleur au moins bon


@dataclass(frozen=True)
class MissionStats:
    time: float = 0.0  # secondes de jeu (hors pause)
    alerts: int = 0  # alertes générales déclenchées
    decoys: int = 0  # leurres lancés


@dataclass(frozen=True)
class MissionResult:
    stats: MissionStats
    time_points: int
    alert_points: int
    decoy_points: int
    score: int
    rank: str


def rank_for(score: int) -> str:
    """Lettre du rang pour un score (le premier seuil atteint, du meilleur au moins bon)."""
    for letter, _, minimum in RANKS:
        if score >= minimum:
            return letter
    return RANKS[-1][0]


def rank_name(letter: str) -> str:
    return next((name for rank, name, _ in RANKS if rank == letter), "")


def rank_minimum(letter: str) -> int:
    return next((minimum for rank, _, minimum in RANKS if rank == letter), 0)


def format_time(seconds: float) -> str:
    """« 1:12.3 » : minutes, secondes et dixième."""
    seconds = max(0.0, seconds)
    return f"{int(seconds // 60)}:{seconds % 60:04.1f}"


def format_score(score: int) -> str:
    """9500 -> « 9 500 »."""
    return f"{score:,}".replace(",", " ")


def rank_index(letter: str) -> int:
    """Position dans la liste (0 = meilleur) ; un rang inconnu est le pire."""
    return RANK_LETTERS.index(letter) if letter in RANK_LETTERS else len(RANK_LETTERS)


def compute_result(stats: MissionStats, par_time: float) -> MissionResult:
    """Score et rang d'une mission terminée.

    Le temps de référence `par_time` donne le plein de points ; l'alerte et les leurres rapportent le plein de points
    quand on s'en passe. Terminer sans alerte et dans le temps, avec au plus un leurre, donne le rang S.
    """
    time_points = max(0, SCORE_TIME_MAX - round(SCORE_TIME_PENALTY * max(0.0, stats.time - par_time)))
    alert_points = max(0, SCORE_ALERT_MAX - SCORE_ALERT_PENALTY * stats.alerts)
    decoy_points = max(0, SCORE_DECOY_MAX - SCORE_DECOY_PENALTY * stats.decoys)
    score = time_points + alert_points + decoy_points
    return MissionResult(stats, time_points, alert_points, decoy_points, score, rank_for(score))


@dataclass
class MissionRecord:
    best_score: int
    best_rank: str
    best_time: float
    completions: int = 1


@dataclass(frozen=True)
class RecordUpdate:
    """Ce que l'enregistrement d'un résultat a changé (pour l'écran de fin de mission)."""

    first_completion: bool
    new_best_score: bool
    new_best_time: bool
    rank_improved: bool
    previous: MissionRecord | None


def progress_path() -> Path:
    return _preferences_path().with_name(FILE_NAME)


@dataclass
class Progress:
    records: dict[str, MissionRecord] = field(default_factory=dict)
    path: Path | None = field(default=None, repr=False, compare=False)

    @classmethod
    def load(cls, path: Path | None = None) -> Progress:
        path = Path(path) if path else progress_path()
        progress = cls(path=path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return progress
        missions = data.get("missions") if isinstance(data, dict) else None
        if not isinstance(missions, dict):
            return progress
        for mission_id, raw in missions.items():
            record = _read_record(raw)
            if record is not None:
                progress.records[str(mission_id)] = record
        return progress

    def save(self) -> bool:
        """Écrit le fichier de façon atomique. Faux si le disque refuse : on ne plante jamais pour ça."""
        path = self.path or progress_path()
        payload = {"missions": {mid: vars(record) for mid, record in self.records.items()}}
        tmp = path.with_suffix(".tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            os.replace(tmp, path)
        except OSError:
            return False
        return True

    def is_completed(self, mission_id: str) -> bool:
        return mission_id in self.records

    def record_of(self, mission_id: str) -> MissionRecord | None:
        return self.records.get(mission_id)

    def record(self, mission_id: str, result: MissionResult) -> RecordUpdate:
        """Enregistre un résultat : on garde le meilleur score (et son rang) et le meilleur temps, séparément."""
        previous = self.records.get(mission_id)
        if previous is None:
            self.records[mission_id] = MissionRecord(result.score, result.rank, result.stats.time)
            return RecordUpdate(True, True, True, True, None)
        new_best_score = result.score > previous.best_score
        new_best_time = result.stats.time < previous.best_time
        rank_improved = rank_index(result.rank) < rank_index(previous.best_rank)
        updated = MissionRecord(
            max(previous.best_score, result.score),
            result.rank if rank_improved else previous.best_rank,
            min(previous.best_time, result.stats.time),
            previous.completions + 1,
        )
        self.records[mission_id] = updated
        return RecordUpdate(False, new_best_score, new_best_time, rank_improved, previous)

    def reset(self) -> None:
        self.records.clear()


def _read_record(raw) -> MissionRecord | None:
    if not isinstance(raw, dict):
        return None
    score, rank, time, count = raw.get("best_score"), raw.get("best_rank"), raw.get("best_time"), raw.get("completions", 1)
    numeric = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)  # noqa: E731
    if not (numeric(score) and numeric(time) and numeric(count)) or score < 0 or time < 0:
        return None
    if rank not in RANK_LETTERS:
        rank = rank_for(int(score))  # rang absent ou inconnu : on le déduit du score
    return MissionRecord(int(score), rank, float(time), max(1, int(count)))
