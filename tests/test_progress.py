import json

import pytest

from game.core.preferences import default_path
from game.progress import (
    MissionRecord,
    MissionStats,
    Progress,
    compute_result,
    format_score,
    format_time,
    progress_path,
    rank_for,
    rank_index,
    rank_minimum,
    rank_name,
)
from game.settings import RANKS, SCORE_ALERT_MAX, SCORE_DECOY_MAX, SCORE_TIME_MAX

PAR = 100.0


def result(time=0.0, alerts=0, decoys=0, par=PAR):
    return compute_result(MissionStats(time, alerts, decoys), par)


# --- Score ---------------------------------------------------------------------------------
def test_a_perfect_run_scores_the_maximum():
    r = result(time=PAR - 30)
    assert (r.time_points, r.alert_points, r.decoy_points) == (SCORE_TIME_MAX, SCORE_ALERT_MAX, SCORE_DECOY_MAX)
    assert r.score == 10000 and r.rank == "S"


def test_finishing_exactly_on_the_reference_time_still_gives_full_time_points():
    assert result(time=PAR).time_points == SCORE_TIME_MAX


@pytest.mark.parametrize("over, expected", [(1, 3975), (10, 3750), (40, 3000), (160, 0), (1000, 0)])
def test_each_second_over_the_reference_costs_points_down_to_zero(over, expected):
    assert result(time=PAR + over).time_points == expected


@pytest.mark.parametrize("alerts, expected", [(0, 4000), (1, 2000), (2, 0), (5, 0)])
def test_each_alert_costs_points_down_to_zero(alerts, expected):
    assert result(alerts=alerts).alert_points == expected


@pytest.mark.parametrize("decoys, expected", [(0, 2000), (1, 1500), (4, 0), (9, 0)])
def test_each_decoy_costs_points_down_to_zero(decoys, expected):
    assert result(decoys=decoys).decoy_points == expected


def test_the_score_is_the_sum_of_its_three_parts():
    r = result(time=PAR + 20, alerts=1, decoys=2)
    assert r.score == r.time_points + r.alert_points + r.decoy_points == 3500 + 2000 + 1000


def test_the_worst_completed_run_still_scores_zero_not_negative():
    r = result(time=10_000, alerts=9, decoys=99)
    assert r.score == 0 and r.rank == "D"


def test_one_alert_costs_the_top_rank():
    assert result(alerts=1).rank != "S"
    assert result(alerts=1).rank == "A"  # 4000 + 2000 + 2000 = 8000, pile le seuil du rang A
    assert result(alerts=1, decoys=1).rank == "B"  # 7500


def test_a_single_decoy_is_still_enough_for_the_top_rank():
    assert result(decoys=1).rank == "S" and result(decoys=2).rank == "A"


def test_the_stats_are_kept_in_the_result():
    stats = MissionStats(12.5, 1, 3)
    assert compute_result(stats, PAR).stats == stats


# --- Rangs --------------------------------------------------------------------------------------
@pytest.mark.parametrize("score, rank", [(10000, "S"), (9500, "S"), (9499, "A"), (8000, "A"), (7999, "B"), (6000, "B"), (5999, "C"), (3500, "C"), (3499, "D"), (0, "D")])
def test_rank_boundaries(score, rank):
    assert rank_for(score) == rank


def test_ranks_are_ordered_best_first_with_decreasing_thresholds():
    minimums = [minimum for _, _, minimum in RANKS]
    assert minimums == sorted(minimums, reverse=True) and minimums[-1] == 0
    assert [letter for letter, _, _ in RANKS] == ["S", "A", "B", "C", "D"]


def test_rank_helpers():
    assert rank_name("S") == "Fantôme" and rank_name("?") == ""
    assert rank_minimum("A") == 8000 and rank_minimum("?") == 0
    assert rank_index("S") < rank_index("A") < rank_index("D") < rank_index("?")


def test_the_top_rank_is_reachable_without_perfection():
    """Un joueur très bon (un leurre, dans le temps, sans alerte) atteint le rang S : il n'est pas réservé au parfait."""
    assert rank_for(SCORE_TIME_MAX + SCORE_ALERT_MAX + 1500) == "S"


def test_formatting():
    assert format_time(72.34) == "1:12.3" and format_time(5) == "0:05.0" and format_time(-3) == "0:00.0"
    assert format_score(9500) == "9 500" and format_score(120) == "120" and format_score(1234567) == "1 234 567"


# --- Enregistrement des résultats ------------------------------------------------------------------
def test_a_first_completion_creates_the_record():
    progress = Progress()
    update = progress.record("m1", result(time=80, decoys=1))
    assert update.first_completion and update.previous is None
    assert progress.is_completed("m1") and not progress.is_completed("m2")
    assert progress.record_of("m1") == MissionRecord(9500, "S", 80, 1)


def test_a_better_run_improves_score_rank_and_time():
    progress = Progress()
    progress.record("m", result(time=120, alerts=1, decoys=2))  # rang C
    update = progress.record("m", result(time=80))  # parfait
    assert not update.first_completion and update.new_best_score and update.new_best_time and update.rank_improved
    record = progress.record_of("m")
    assert (record.best_rank, record.best_score, record.best_time, record.completions) == ("S", 10000, 80, 2)


def test_a_worse_run_never_lowers_the_record():
    progress = Progress()
    progress.record("m", result(time=80))
    before = progress.record_of("m")
    update = progress.record("m", result(time=300, alerts=3, decoys=5))
    assert not (update.new_best_score or update.new_best_time or update.rank_improved)
    after = progress.record_of("m")
    assert (after.best_score, after.best_rank, after.best_time) == (before.best_score, before.best_rank, before.best_time)
    assert after.completions == 2  # mais la tentative est comptée


def test_best_time_and_best_score_are_tracked_independently():
    progress = Progress()
    progress.record("m", result(time=60, alerts=1))  # rapide mais une alerte
    update = progress.record("m", result(time=150))  # lent mais sans alerte : meilleur score, moins bon temps
    assert update.new_best_score and not update.new_best_time
    record = progress.record_of("m")
    assert record.best_time == 60 and record.best_score > result(time=60, alerts=1).score


def test_an_equal_score_is_not_a_record():
    progress = Progress()
    progress.record("m", result(time=80))
    assert not progress.record("m", result(time=80)).new_best_score


def test_missions_are_recorded_separately():
    progress = Progress()
    progress.record("a", result(time=50))
    progress.record("b", result(time=500, alerts=2))
    assert progress.record_of("a").best_rank == "S" and progress.record_of("b").best_rank != "S"


def test_reset_forgets_everything():
    progress = Progress()
    progress.record("a", result())
    progress.reset()
    assert not progress.is_completed("a")


# --- Sauvegarde ----------------------------------------------------------------------------------------
def test_progress_round_trips_through_the_file(tmp_path):
    path = tmp_path / "p.json"
    progress = Progress.load(path)
    progress.record("a", result(time=70, decoys=1))
    progress.record("b", result(time=300, alerts=1))
    assert progress.save()
    again = Progress.load(path)
    assert again.records == progress.records and again.is_completed("a") and again.is_completed("b")


def test_no_file_means_a_fresh_start(tmp_path):
    assert Progress.load(tmp_path / "absent.json").records == {}


@pytest.mark.parametrize("content", ["", "pas du json", "[]", "null", '{"missions": 3}', '{"missions": [1, 2]}', '{"mis'])
def test_unreadable_files_mean_a_fresh_start(tmp_path, content):
    path = tmp_path / "p.json"
    path.write_text(content)
    assert Progress.load(path).records == {}


def test_bad_records_are_dropped_and_good_ones_kept(tmp_path):
    path = tmp_path / "p.json"
    path.write_text(json.dumps({"missions": {
        "ok": {"best_score": 9000, "best_rank": "A", "best_time": 70.5, "completions": 3},
        "négatif": {"best_score": -5, "best_rank": "A", "best_time": 10},
        "texte": {"best_score": "beaucoup", "best_rank": "A", "best_time": 10},
        "booléen": {"best_score": True, "best_rank": "A", "best_time": 10},
        "pas un objet": 42,
        "sans temps": {"best_score": 100, "best_rank": "D"},
    }}))
    progress = Progress.load(path)
    assert list(progress.records) == ["ok"]
    assert progress.record_of("ok") == MissionRecord(9000, "A", 70.5, 3)


def test_an_unknown_rank_is_recomputed_from_the_score(tmp_path):
    path = tmp_path / "p.json"
    path.write_text(json.dumps({"missions": {"m": {"best_score": 8200, "best_rank": "Z", "best_time": 50}}}))
    assert Progress.load(path).record_of("m").best_rank == "A"


def test_missing_completions_default_to_one_and_junk_to_one(tmp_path):
    path = tmp_path / "p.json"
    path.write_text(json.dumps({"missions": {"m": {"best_score": 100, "best_rank": "D", "best_time": 5, "completions": 0}}}))
    assert Progress.load(path).record_of("m").completions == 1


def test_saving_creates_missing_folders_and_is_atomic(tmp_path):
    path = tmp_path / "a" / "b" / "p.json"
    progress = Progress.load(path)
    progress.record("m", result())
    assert progress.save() and path.exists() and not list(path.parent.glob("*.tmp"))


def test_saving_never_raises_when_the_disk_refuses(tmp_path):
    blocker = tmp_path / "fichier"
    blocker.write_text("pas un dossier")
    progress = Progress.load(blocker / "p.json")
    progress.record("m", result())
    assert progress.save() is False


def test_the_file_sits_next_to_the_preferences():
    assert progress_path().parent == default_path().parent and progress_path().name == "progress.json"


def test_the_saved_file_does_not_contain_its_own_path(tmp_path):
    path = tmp_path / "p.json"
    progress = Progress.load(path)
    progress.record("m", result())
    progress.save()
    assert set(json.loads(path.read_text())) == {"missions"}
