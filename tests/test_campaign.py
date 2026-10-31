import json

import pytest

from game.campaign import (
    AVAILABLE,
    BEATEN,
    COMPLETED,
    HIDDEN,
    LOCKED,
    OBTAINED,
    REACHABLE,
    Campaign,
    Mission,
    load_campaign,
    mission_status,
    rank_ladder,
)
from game.progress import MissionRecord, MissionStats, Progress, compute_result
from game.settings import CAMPAIGN_FILE, MAPS_DIR, PLAYER_SPEED
from game.world.level_check import route_distances
from game.world.tilemap import Tilemap


def mission(i):
    return Mission(f"m{i}", f"Mission {i}", MAPS_DIR / "training.txt", 100.0, "Résumé", f"ÉPISODE {i}", ("Un paragraphe.",))


def campaign(count=3):
    return Campaign([mission(i) for i in range(1, count + 1)])


def done(progress, mission_id):
    progress.record(mission_id, compute_result(MissionStats(50, 0, 0), 100))


# --- La campagne livrée -------------------------------------------------------------------------
def test_the_shipped_campaign_loads_with_its_missions_in_order():
    c = load_campaign()
    assert [m.id for m in c.missions] == ["training", "outpost", "blackout", "endor", "uniform", "radar", "prison", "hangar", "theft", "hq", "cruiser", "destroyer"]
    assert [m.title for m in c.missions] == [
        "Entraînement", "Avant-poste de Tatooine", "Coupure de courant", "Le bunker d'Endor",
        "Le vestiaire impérial", "Le poste radar d'Endor", "Le centre de détention", "Le hangar de la flotte", "Vol de la navette", "Le quartier général", "Le croiseur impérial", "Le Destroyer",
    ]
    assert [m.episode for m in c.missions] == ["ÉPISODE I", "ÉPISODE II", "ÉPISODE III", "ÉPISODE IV", "ÉPISODE V", "ÉPISODE VI", "ÉPISODE VII", "ÉPISODE VIII", "ÉPISODE IX", "ÉPISODE X", "ÉPISODE XI", "ÉPISODE XII"]
    assert [m.objective for m in c.missions] == ["steal_plans", "steal_plans", "cut_power", "steal_plans", "steal_uniform", "cut_power", "free_prisoner", "steal_plans", "steal_ship", "steal_plans", "steal_plans", "cut_power"]


def test_every_mission_has_what_the_crawl_and_the_map_need():
    for m in load_campaign().missions:
        assert m.map_path.exists() and m.par_time > 0 and m.summary and len(m.intro) >= 2
        assert all(p.strip() for p in m.intro)


def test_the_first_mission_opens_with_the_prologue_line_and_later_ones_do_not_need_it():
    first, second, *_ = load_campaign().missions
    assert first.prologue and "galaxie" in first.prologue
    assert second.prologue is None


def test_reference_times_are_achievable_but_not_trivial():
    """Le temps de référence laisse de la marge à un joueur qui court, sans être ridiculement large."""
    for m in load_campaign().missions:
        d = route_distances(Tilemap.from_file(m.map_path))
        fastest = (d["to_goal"] + d["escape"]) / PLAYER_SPEED["run"]
        walking = (d["to_goal"] + d["escape"]) / PLAYER_SPEED["walk"]
        assert m.par_time >= 1.5 * fastest, f"{m.id} : référence trop serrée"
        assert m.par_time <= 8 * walking, f"{m.id} : référence trop large"


def test_the_campaign_file_is_plain_json_with_a_missions_list():
    data = json.loads(CAMPAIGN_FILE.read_text(encoding="utf-8"))
    assert list(data) == ["missions"]


# --- Déblocage ----------------------------------------------------------------------------------------
def test_only_the_first_mission_is_open_at_the_start():
    c, progress = campaign(), Progress()
    assert [c.is_unlocked(m, progress) for m in c.missions] == [True, False, False]


def test_finishing_a_mission_unlocks_the_next_one_only():
    c, progress = campaign(), Progress()
    done(progress, "m1")
    assert [c.is_unlocked(m, progress) for m in c.missions] == [True, True, False]
    done(progress, "m2")
    assert [c.is_unlocked(m, progress) for m in c.missions] == [True, True, True]


def test_a_mission_stays_unlocked_even_if_an_earlier_record_is_missing():
    """On ne bloque que sur la mission juste avant (une progression partielle ne reverrouille rien d'autre)."""
    c, progress = campaign(), Progress()
    done(progress, "m2")
    assert c.is_unlocked(c.missions[2], progress) and not c.is_unlocked(c.missions[1], progress)


def test_current_is_the_first_open_unfinished_mission():
    c, progress = campaign(), Progress()
    assert c.current(progress).id == "m1"
    done(progress, "m1")
    assert c.current(progress).id == "m2"
    done(progress, "m2")
    done(progress, "m3")
    assert c.current(progress).id == "m3"  # tout est fini : on retombe sur la dernière


def test_status_of_each_mission():
    c, progress = campaign(), Progress()
    assert [mission_status(c, m, progress) for m in c.missions] == [AVAILABLE, LOCKED, LOCKED]
    done(progress, "m1")
    assert [mission_status(c, m, progress) for m in c.missions] == [COMPLETED, AVAILABLE, LOCKED]


def test_navigation_helpers():
    c = campaign()
    assert c.get("m2").title == "Mission 2" and c.index_of(c.missions[2]) == 2
    assert c.next_after(c.missions[0]).id == "m2" and c.next_after(c.missions[-1]) is None


def test_a_campaign_needs_a_mission():
    with pytest.raises(ValueError):
        Campaign([])


# --- Échelle des rangs ---------------------------------------------------------------------------------
def states(ladder):
    return [state for _, _, _, state in ladder]


def test_a_locked_mission_hides_its_ranks():
    assert states(rank_ladder(None, LOCKED)) == [HIDDEN] * 5


def test_an_unfinished_open_mission_shows_every_rank_as_reachable():
    assert states(rank_ladder(None, AVAILABLE)) == [REACHABLE] * 5


def test_a_finished_mission_marks_the_obtained_rank_and_what_is_left_to_aim_for():
    record = MissionRecord(7000, "B", 80, 1)
    assert states(rank_ladder(record, COMPLETED)) == [REACHABLE, REACHABLE, OBTAINED, BEATEN, BEATEN]


def test_the_best_rank_leaves_nothing_to_aim_for():
    assert states(rank_ladder(MissionRecord(10000, "S", 50, 1), COMPLETED)) == [OBTAINED, BEATEN, BEATEN, BEATEN, BEATEN]


def test_the_ladder_lists_letter_name_and_threshold():
    ladder = rank_ladder(None, AVAILABLE)
    assert ladder[0][:3] == ("S", "Fantôme", 9500) and ladder[-1][:3] == ("D", "Survivant", 0)


# --- Lecture du fichier de campagne ----------------------------------------------------------------------
def valid():
    return {"id": "m", "title": "Titre", "map": "training.txt", "par_time": 60, "summary": "Résumé", "episode": "ÉPISODE I", "intro": ["Un paragraphe."]}


def write(tmp_path, missions):
    path = tmp_path / "campaign.json"
    path.write_text(json.dumps({"missions": missions}), encoding="utf-8")
    return path


def test_a_minimal_valid_campaign_loads(tmp_path):
    c = load_campaign(write(tmp_path, [valid()]))
    assert c.missions[0].prologue is None and c.missions[0].par_time == 60.0 and c.missions[0].map_path.name == "training.txt"


def test_text_is_stripped_and_a_prologue_is_kept(tmp_path):
    raw = {**valid(), "title": "  Titre  ", "prologue": "Il était une fois", "intro": ["  a  ", "b"]}
    m = load_campaign(write(tmp_path, [raw])).missions[0]
    assert m.title == "Titre" and m.prologue == "Il était une fois" and m.intro == ("a", "b")


@pytest.mark.parametrize(
    "change, message",
    [
        ({"id": None}, r"mission 1 : le champ 'id' doit être un texte non vide"),
        ({"id": "Mauvais Id"}, r"l'identifiant doit contenir seulement a-z, 0-9 et _"),
        ({"title": ""}, r"le champ 'title' doit être un texte non vide"),
        ({"summary": 3}, r"le champ 'summary' doit être un texte non vide"),
        ({"episode": "  "}, r"le champ 'episode' doit être un texte non vide"),
        ({"map": None}, r"le champ 'map' doit être un texte non vide"),
        ({"map": "inexistante.txt"}, r"la carte inexistante.txt est introuvable"),
        ({"par_time": 0}, r"'par_time' doit être un nombre de secondes positif"),
        ({"par_time": -5}, r"'par_time' doit être un nombre de secondes positif"),
        ({"par_time": "long"}, r"'par_time' doit être un nombre de secondes positif"),
        ({"par_time": True}, r"'par_time' doit être un nombre de secondes positif"),
        ({"intro": []}, r"'intro' doit être une liste de paragraphes non vides"),
        ({"intro": "un seul texte"}, r"'intro' doit être une liste de paragraphes non vides"),
        ({"intro": ["ok", ""]}, r"'intro' doit être une liste de paragraphes non vides"),
        ({"intro": ["ok", 4]}, r"'intro' doit être une liste de paragraphes non vides"),
        ({"prologue": ""}, r"le champ 'prologue' doit être un texte non vide"),
    ],
)
def test_invalid_missions_are_explained_in_french(tmp_path, change, message):
    with pytest.raises(ValueError, match=r"^Campagne : .*" + message):
        load_campaign(write(tmp_path, [{**valid(), **change}]))


def test_a_missing_field_is_reported(tmp_path):
    raw = valid()
    del raw["summary"]
    with pytest.raises(ValueError, match="'summary'"):
        load_campaign(write(tmp_path, [raw]))


def test_the_error_names_the_faulty_mission(tmp_path):
    with pytest.raises(ValueError, match=r"mission 2 \('seconde'\)"):
        load_campaign(write(tmp_path, [valid(), {**valid(), "id": "seconde", "par_time": 0}]))


def test_duplicate_ids_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="identifiant déjà utilisé"):
        load_campaign(write(tmp_path, [valid(), valid()]))


@pytest.mark.parametrize("content", ["pas du json", "[]", '{"missions": []}', '{"missions": "x"}', '{"autre": 1}', '{"missions": [3]}'])
def test_broken_files_are_reported_not_crashed_on(tmp_path, content):
    path = tmp_path / "campaign.json"
    path.write_text(content)
    with pytest.raises(ValueError, match="^Campagne"):
        load_campaign(path)


def test_a_missing_file_is_reported(tmp_path):
    with pytest.raises(ValueError, match="fichier illisible"):
        load_campaign(tmp_path / "absent.json")
