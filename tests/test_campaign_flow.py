"""Carte de la campagne, générique, résultats, et les enchaînements entre eux."""

import pygame
import pytest

from game.campaign import Campaign, Mission
from game.core.input import InputState
from game.progress import MissionStats, compute_result
from game.scenes import navigation, play_scene
from game.scenes.campaign_scene import NODE_RADIUS, CampaignScene, node_positions
from game.scenes.crawl_scene import CrawlScene
from game.scenes.main_menu import MainMenuScene
from game.scenes.results_scene import ResultsScene
from game.settings import CRAWL_LOGO_TIME, CRAWL_SKIP_HOLD, CRAWL_SPEED, CRAWL_THEME, MAPS_DIR
from game.ui.crawl import CRAWL, LOGO, PROLOGUE

KEY = lambda key: pygame.event.Event(pygame.KEYDOWN, key=key)  # noqa: E731
KEYUP = lambda key: pygame.event.Event(pygame.KEYUP, key=key)  # noqa: E731


def stack(game):
    return [type(s).__name__ for s in game.scenes._stack]


def win(progress, mission_id, time=50.0, alerts=0, decoys=0, par=100.0):
    return progress.record(mission_id, compute_result(MissionStats(time, alerts, decoys), par))


@pytest.fixture
def campaign_scene(game):
    game.scenes.push(MainMenuScene(game))
    scene = CampaignScene(game)
    game.scenes.push(scene)
    return scene


# --- Positions des nœuds ---------------------------------------------------------------------------
def test_a_short_campaign_is_centered():
    positions = node_positions(2, 1280, 0)
    assert (positions[0][0] + positions[1][0]) / 2 == pytest.approx(640, abs=1)
    assert positions[0][0] < positions[1][0]


def test_a_single_mission_sits_in_the_middle():
    assert node_positions(1, 1280, 0)[0][0] == 640


def test_a_long_campaign_scrolls_to_keep_the_selection_in_view():
    for selected in range(12):
        positions = node_positions(12, 1280, selected)
        x = positions[selected][0]
        assert 100 <= x <= 1180
    assert node_positions(12, 1280, 0)[0][0] < node_positions(12, 1280, 0)[-1][0]  # toujours dans l'ordre
    assert node_positions(12, 1280, 11)[-1][0] <= 1280 - 100  # la dernière ne sort pas à droite
    assert node_positions(12, 1280, 0)[0][0] >= 100  # la première ne sort pas à gauche


def test_the_path_has_a_gentle_wave_inside_the_screen():
    ys = [y for _, y in node_positions(8, 1280, 0)]
    assert len(set(ys)) > 3 and max(ys) - min(ys) < 120


# --- Carte de la campagne -----------------------------------------------------------------------------
def test_a_new_game_selects_the_first_mission(campaign_scene):
    assert campaign_scene.index == 0 and campaign_scene.mission.id == "training"


def test_the_map_opens_on_the_mission_to_play_next(game):
    win(game.progress, "training")
    game.scenes.push(MainMenuScene(game))
    assert CampaignScene(game).mission.id == "outpost"


def test_a_given_mission_is_selected_first(game):
    win(game.progress, "training")
    assert CampaignScene(game, game.campaign.get("training")).index == 0


def test_arrows_and_zqsd_move_the_selection_and_stop_at_the_ends(campaign_scene):
    last = len(campaign_scene.campaign.missions) - 1
    campaign_scene.handle_event(KEY(pygame.K_LEFT))
    assert campaign_scene.index == 0
    campaign_scene.handle_event(KEY(pygame.K_RIGHT))
    assert campaign_scene.index == 1
    for _ in range(last + 3):
        campaign_scene.handle_event(KEY(pygame.K_RIGHT))
    assert campaign_scene.index == last  # dernière mission : on ne va pas plus loin
    campaign_scene.handle_event(KEY(pygame.K_q))
    assert campaign_scene.index == last - 1
    campaign_scene.handle_event(KEY(pygame.K_d))
    assert campaign_scene.index == last


def test_selecting_makes_a_sound_only_when_it_changes(campaign_scene, monkeypatch):
    sounds = []
    monkeypatch.setattr(campaign_scene.game.audio, "play", lambda name, *a, **k: sounds.append(name))
    campaign_scene.handle_event(KEY(pygame.K_LEFT))  # déjà à gauche
    campaign_scene.handle_event(KEY(pygame.K_RIGHT))
    assert sounds == ["ui_move"]


def test_a_locked_mission_cannot_be_launched_and_says_why(campaign_scene, monkeypatch):
    sounds = []
    monkeypatch.setattr(campaign_scene.game.audio, "play", lambda name, *a, **k: sounds.append(name))
    campaign_scene.handle_event(KEY(pygame.K_RIGHT))
    campaign_scene.handle_event(KEY(pygame.K_RETURN))
    assert stack(campaign_scene.game)[-1] == "CampaignScene"  # rien ne se lance
    assert "Entraînement" in campaign_scene.message and campaign_scene.message_left > 0
    assert "door_denied" in sounds


def test_the_message_fades_away(campaign_scene):
    campaign_scene.handle_event(KEY(pygame.K_RIGHT))
    campaign_scene.handle_event(KEY(pygame.K_RETURN))
    for _ in range(300):
        campaign_scene.update(1 / 60)
    assert campaign_scene.message_left == 0


def test_an_open_mission_starts_with_its_crawl(campaign_scene):
    campaign_scene.handle_event(KEY(pygame.K_RETURN))
    top = campaign_scene.game.scenes.current
    assert isinstance(top, CrawlScene) and top.mission.id == "training"
    assert stack(campaign_scene.game) == ["MainMenuScene", "CampaignScene", "CrawlScene"]


def test_a_finished_mission_can_be_replayed_and_the_next_one_launched(campaign_scene):
    win(campaign_scene.game.progress, "training")
    campaign_scene.handle_event(KEY(pygame.K_RIGHT))
    campaign_scene.handle_event(KEY(pygame.K_RETURN))
    assert campaign_scene.game.scenes.current.mission.id == "outpost"  # la suivante, maintenant débloquée
    campaign_scene.game.scenes.pop()
    campaign_scene.handle_event(KEY(pygame.K_LEFT))
    campaign_scene.handle_event(KEY(pygame.K_RETURN))
    assert campaign_scene.game.scenes.current.mission.id == "training"  # et la terminée peut être rejouée


def test_escape_returns_to_the_main_menu(campaign_scene):
    campaign_scene.handle_event(KEY(pygame.K_ESCAPE))
    assert stack(campaign_scene.game) == ["MainMenuScene"]


def test_clicking_a_node_selects_it_and_a_second_click_launches(campaign_scene):
    positions = node_positions(len(campaign_scene.campaign.missions), 1280, campaign_scene.index)
    campaign_scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=positions[1], button=1))
    assert campaign_scene.index == 1 and stack(campaign_scene.game)[-1] == "CampaignScene"
    win(campaign_scene.game.progress, "training")
    positions = node_positions(len(campaign_scene.campaign.missions), 1280, campaign_scene.index)
    campaign_scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=positions[1], button=1))
    assert stack(campaign_scene.game)[-1] == "CrawlScene"


def test_clicking_elsewhere_or_with_another_button_does_nothing(campaign_scene):
    campaign_scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(5, 5), button=1))
    campaign_scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=node_positions(len(campaign_scene.campaign.missions), 1280, 0)[1], button=3))
    assert campaign_scene.index == 0 and stack(campaign_scene.game)[-1] == "CampaignScene"


def test_the_map_draws_in_every_progress_state(game):
    game.scenes.push(MainMenuScene(game))
    scene = CampaignScene(game)
    game.scenes.push(scene)
    for state in ("neuf", "une terminée", "tout terminé"):
        if state == "une terminée":
            win(game.progress, "training", time=30, decoys=1)
        elif state == "tout terminé":
            win(game.progress, "outpost", time=900, alerts=2)
        for index in range(2):
            scene.index = index
            for _ in range(3):
                game.step(1 / 60)
    scene.message, scene.message_left = "Un message", 2.0
    game.step(1 / 60)


def test_a_long_campaign_draws_and_navigates(game):
    missions = [Mission(f"m{i}", f"Mission {i}", MAPS_DIR / "training.txt", 100.0, "Résumé assez long pour tenir sur plusieurs lignes dans le panneau de détail.", f"ÉPISODE {i}", ("x",)) for i in range(1, 13)]
    game.campaign = Campaign(missions)
    for m in missions[:5]:
        win(game.progress, m.id, time=120)
    game.scenes.push(MainMenuScene(game))
    scene = CampaignScene(game)
    game.scenes.push(scene)
    assert scene.index == 5  # on reprend où l'on en était
    for _ in range(11):
        scene.handle_event(KEY(pygame.K_RIGHT))
        game.step(1 / 60)
    assert scene.index == 11


def test_the_map_keeps_the_ambient_music(campaign_scene):
    campaign_scene.on_enter()
    assert campaign_scene.game.audio._music_channels and campaign_scene.game.audio.tension_target == 0


def test_node_radius_is_clickable_size():
    assert 30 <= NODE_RADIUS <= 50


# --- Générique ---------------------------------------------------------------------------------------------
@pytest.fixture
def crawl(game):
    game.scenes.push(MainMenuScene(game))
    game.scenes.push(CampaignScene(game))
    scene = CrawlScene(game, game.campaign.get("outpost"))  # sans accroche : démarre sur le titre
    game.scenes.push(scene)
    return scene


def advance(scene, seconds, step=1 / 60):
    for _ in range(round(seconds / step)):
        scene.game.step(step)


def test_the_crawl_mutes_the_ambient_music_and_restores_it_when_it_ends(crawl):
    audio = crawl.game.audio
    assert audio.music_muted
    crawl.game.scenes.pop()
    assert not audio.music_muted and not audio.theme_playing


def test_the_theme_starts_with_the_title_not_before(game, monkeypatch):
    calls = []
    monkeypatch.setattr(game.audio, "play_theme", lambda name: calls.append(name))
    game.scenes.push(MainMenuScene(game))
    scene = CrawlScene(game, game.campaign.get("training"))  # a une accroche
    game.scenes.push(scene)
    assert scene.timeline.phase == PROLOGUE
    advance(scene, 2)
    assert calls == [] and scene.timeline.phase == PROLOGUE  # silence pendant l'accroche
    advance(scene, 5)
    assert scene.timeline.phase == LOGO and calls == [CRAWL_THEME]
    advance(scene, 3)
    assert calls == [CRAWL_THEME]  # une seule fois


def test_without_a_prologue_the_theme_starts_at_once(game, monkeypatch):
    calls = []
    monkeypatch.setattr(game.audio, "play_theme", lambda name: calls.append(name))
    game.scenes.push(MainMenuScene(game))
    game.scenes.push(CrawlScene(game, game.campaign.get("outpost")))
    game.step(1 / 60)
    assert calls == [CRAWL_THEME]


def test_the_crawl_does_not_wait_for_the_end_of_the_music(crawl):
    duration = CRAWL_LOGO_TIME + crawl.timeline.distance / crawl.timeline.speed
    assert crawl.timeline.speed == CRAWL_SPEED
    assert duration < 75  # assez long pour lire, bien plus court que le générique complet (~89 s) et son prologue
    music = crawl.game.audio.sound_length(CRAWL_THEME)
    if music:
        assert duration < music


def test_without_the_music_file_the_crawl_still_runs(game):
    from game.core.audio import Audio

    game.audio = Audio(game.prefs, sounds_dir=MAPS_DIR)  # aucun .wav dans ce dossier
    game.scenes.push(MainMenuScene(game))
    scene = CrawlScene(game, game.campaign.get("outpost"))
    game.scenes.push(scene)
    advance(scene, 3)  # ne plante pas, sans musique


def test_holding_a_key_for_a_second_skips_straight_to_the_mission(crawl):
    game = crawl.game
    crawl.handle_event(KEY(pygame.K_SPACE))
    advance(crawl, CRAWL_SKIP_HOLD + 0.2)
    top = game.scenes.current
    assert isinstance(top, play_scene.PlayScene) and top.mission.id == "outpost"
    assert top.map_path == game.campaign.get("outpost").map_path
    assert stack(game) == ["MainMenuScene", "CampaignScene", "PlayScene"]  # le générique a été remplacé


@pytest.mark.parametrize("key", [pygame.K_RETURN, pygame.K_ESCAPE])
def test_enter_and_escape_skip_too(crawl, key):
    crawl.handle_event(KEY(key))
    advance(crawl, CRAWL_SKIP_HOLD + 0.2)
    assert isinstance(crawl.game.scenes.current, play_scene.PlayScene)


def test_a_short_press_does_not_skip(crawl):
    crawl.handle_event(KEY(pygame.K_SPACE))
    advance(crawl, CRAWL_SKIP_HOLD / 2)
    crawl.handle_event(KEYUP(pygame.K_SPACE))
    advance(crawl, 2)
    assert isinstance(crawl.game.scenes.current, CrawlScene)


def test_other_keys_do_not_skip(crawl):
    crawl.handle_event(KEY(pygame.K_a))
    advance(crawl, CRAWL_SKIP_HOLD * 2)
    assert isinstance(crawl.game.scenes.current, CrawlScene)


def test_the_skip_gauge_is_visible_only_while_holding(crawl):
    crawl.draw(crawl.game.screen)
    assert not crawl.skip.active
    crawl.handle_event(KEY(pygame.K_SPACE))
    crawl.update(0.4)
    crawl.draw(crawl.game.screen)
    assert crawl.skip.active and 0.3 < crawl.skip.progress < 0.5


def test_the_crawl_ends_by_itself_and_starts_the_mission(game):
    game.scenes.push(MainMenuScene(game))
    scene = CrawlScene(game, game.campaign.get("outpost"))
    game.scenes.push(scene)
    scene.timeline.skip()  # comme si le texte était arrivé au bout
    game.step(1 / 60)
    assert isinstance(game.scenes.current, play_scene.PlayScene)


def test_the_mission_only_starts_once(crawl):
    crawl.timeline.skip()
    crawl.update(1 / 60)
    crawl.update(1 / 60)  # une seconde mise à jour après la fin ne relance rien
    assert stack(crawl.game).count("PlayScene") == 1


def test_every_phase_draws(crawl):
    for phase_time in (0.5, CRAWL_LOGO_TIME - 0.2, CRAWL_LOGO_TIME + 3, 40):
        crawl.timeline.time = 0
        crawl.timeline.phase = LOGO if phase_time < CRAWL_LOGO_TIME else CRAWL
        crawl.timeline.time = phase_time if crawl.timeline.phase == LOGO else phase_time - CRAWL_LOGO_TIME
        crawl.draw(crawl.game.screen)


def test_the_prologue_phase_draws(game):
    game.scenes.push(MainMenuScene(game))
    scene = CrawlScene(game, game.campaign.get("training"))
    game.scenes.push(scene)
    for _ in range(120):
        game.step(1 / 60)


def test_leaving_the_crawl_in_any_way_stops_its_music(crawl):
    crawl.update(1 / 60)
    crawl.game.scenes.clear()  # par exemple en fermant tout
    assert not crawl.game.audio.theme_playing and not crawl.game.audio.music_muted


# --- Statistiques dans la partie ------------------------------------------------------------------------------
@pytest.fixture
def playing(game, monkeypatch):
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState())
    mission = game.campaign.get("training")
    game.scenes.push(MainMenuScene(game))
    scene = play_scene.PlayScene(game, mission.map_path, mission)
    game.scenes.push(scene)
    scene.guards.clear()
    return scene


def test_play_time_counts_only_while_playing(playing):
    for _ in range(60):
        playing.update(1 / 60)
    assert playing.stats.time == pytest.approx(1.0, abs=0.02)


def test_play_time_excludes_the_pause(playing):
    game = playing.game
    for _ in range(30):
        game.step(1 / 60)
    playing.handle_event(KEY(pygame.K_ESCAPE))
    for _ in range(300):
        game.step(1 / 60)  # cinq secondes dans le menu pause
    game.scenes.pop()
    for _ in range(30):
        game.step(1 / 60)
    assert playing.stats.time == pytest.approx(1.0, abs=0.1)


def test_play_time_stops_once_the_mission_is_over(playing):
    playing.caught = True
    for _ in range(60):
        playing.update(1 / 60)
    assert playing.stats.time == 0


def test_decoys_and_alerts_are_counted(playing):
    from game.items import Item, ItemKind

    playing.inventory.add(Item(ItemKind.DECOY), 2)
    for _ in range(2):
        playing._throw_decoy(playing.player.pos + pygame.Vector2(60, 0))
    playing.game.events.emit("alert_raised", pos=pygame.Vector2(0, 0))
    assert (playing.stats.decoys, playing.stats.alerts) == (2, 1)


def test_a_failed_throw_is_not_counted(playing):
    playing._throw_decoy(playing.player.pos + pygame.Vector2(60, 0))  # aucun leurre en poche
    assert playing.stats.decoys == 0


def test_restarting_resets_the_statistics(playing):
    playing.mission_time, playing.alert_count, playing.decoys_thrown = 99.0, 2, 3
    playing.restart()
    assert playing.stats == MissionStats(0.0, 0, 0)


# --- Écran de résultats -------------------------------------------------------------------------------------------
def finish(playing, time=60.0, alerts=0, decoys=1):
    playing.mission_time, playing.alert_count, playing.decoys_thrown = time, alerts, decoys
    playing.won = True
    playing.game.step(1 / 60)


def test_winning_a_campaign_mission_opens_the_results_and_records_them(playing):
    finish(playing)
    top = playing.game.scenes.current
    assert isinstance(top, ResultsScene) and top.result.rank == "S" and top.result.score == 9500
    record = playing.game.progress.record_of("training")
    assert record.best_score == 9500 and record.best_rank == "S" and record.best_time == pytest.approx(60.0, abs=0.1)


def test_the_progress_is_saved_to_disk_at_once(playing):
    from game.progress import Progress

    finish(playing)
    assert Progress.load().is_completed("training")  # un nouveau chargement (même dossier) le retrouve


def test_winning_unlocks_the_next_mission(playing):
    game = playing.game
    assert not game.campaign.is_unlocked(game.campaign.get("outpost"), game.progress)
    finish(playing)
    assert game.campaign.is_unlocked(game.campaign.get("outpost"), game.progress)


def test_the_results_open_only_once_per_win(playing):
    finish(playing)
    game = playing.game
    for _ in range(30):
        playing.update(1 / 60)  # même si la partie continuait d'être mise à jour
    assert stack(game).count("ResultsScene") == 1 and game.progress.record_of("training").completions == 1


def test_a_plain_map_without_a_mission_keeps_the_old_win_screen(game, monkeypatch):
    from tests.paths import SANDBOX

    monkeypatch.setattr(play_scene, "read_input", lambda: InputState())
    scene = play_scene.PlayScene(game, SANDBOX)
    game.scenes.push(scene)
    scene.won = True
    game.step(1 / 60)
    assert game.scenes.current is scene and game.progress.records == {}


def test_losing_records_nothing(playing):
    playing.caught = True
    playing.game.step(1 / 60)
    assert playing.game.progress.records == {} and stack(playing.game)[-1] == "PlayScene"


def test_the_results_show_each_statistic_with_its_points(playing):
    finish(playing, time=80.0, alerts=1, decoys=2)
    top = playing.game.scenes.current
    rows = {label: (value, points) for label, value, points in top.rows()}
    assert rows["Temps"][1] == 3875  # 80 s pour une référence de 75 s : 5 s en trop, 125 points perdus
    assert rows["Alertes déclenchées"] == ("1", 2000)
    assert rows["Leurres utilisés"] == ("2", 1000)
    assert "1:20.0" in rows["Temps"][0] and "1:15.0" in rows["Temps"][0]  # le temps et la référence


def test_badges_for_a_first_win_then_for_records(playing):
    finish(playing, time=60, alerts=1, decoys=3)
    assert playing.game.scenes.current.badges() == ["PREMIÈRE RÉUSSITE"]
    playing.game.scenes.pop()
    playing.restart()
    finish(playing, time=60, alerts=0, decoys=1)
    badges = playing.game.scenes.current.badges()
    assert "NOUVEAU RECORD" in badges and "NOUVEAU RANG" in badges and "PREMIÈRE RÉUSSITE" not in badges


def test_a_worse_second_run_earns_no_badge(playing):
    finish(playing, time=60, alerts=0, decoys=0)
    playing.game.scenes.pop()
    playing.restart()
    finish(playing, time=200, alerts=2, decoys=5)
    assert playing.game.scenes.current.badges() == []
    assert playing.game.progress.record_of("training").best_rank == "S"  # le meilleur rang est conservé


def test_the_menu_offers_the_next_mission_replay_map_and_main_menu(playing):
    top = (finish(playing), playing.game.scenes.current)[1]
    assert [i.label for i in top.menu.items] == ["Mission suivante", "Rejouer la mission", "Carte de la campagne", "Menu principal"]


def test_the_last_mission_has_no_next_mission_entry(game, monkeypatch):
    monkeypatch.setattr(play_scene, "read_input", lambda: InputState())
    last = game.campaign.get("destroyer")
    game.scenes.push(MainMenuScene(game))
    scene = play_scene.PlayScene(game, last.map_path, last)
    game.scenes.push(scene)
    scene.won = True
    game.step(1 / 60)
    assert [i.label for i in game.scenes.current.menu.items] == ["Rejouer la mission", "Carte de la campagne", "Menu principal"]


def test_replay_returns_to_a_fresh_attempt_without_the_crawl(playing):
    finish(playing, time=60)
    game = playing.game
    results = game.scenes.current
    results.menu.select(1)
    results.handle_event(KEY(pygame.K_RETURN))
    assert game.scenes.current is playing and not playing.won and playing.stats == MissionStats(0.0, 0, 0)
    finish(playing, time=70)  # on peut gagner à nouveau : les résultats se rouvrent
    assert isinstance(game.scenes.current, ResultsScene) and game.progress.record_of("training").completions == 2


def test_next_mission_goes_through_the_crawl_of_the_following_one(playing):
    finish(playing)
    game = playing.game
    game.scenes.current.handle_event(KEY(pygame.K_RETURN))  # « Mission suivante » est en tête
    assert stack(game) == ["MainMenuScene", "CampaignScene", "CrawlScene"]
    assert game.scenes.current.mission.id == "outpost" and game.scenes._stack[1].mission.id == "outpost"


def test_the_campaign_entry_rebuilds_menu_and_map_on_the_played_mission(playing):
    finish(playing)
    game = playing.game
    results = game.scenes.current
    results.menu.select(2)
    results.handle_event(KEY(pygame.K_RETURN))
    assert stack(game) == ["MainMenuScene", "CampaignScene"] and game.scenes.current.mission.id == "training"


def test_the_main_menu_entry_clears_everything(playing):
    finish(playing)
    game = playing.game
    results = game.scenes.current
    results.menu.select(3)
    results.handle_event(KEY(pygame.K_RETURN))
    assert stack(game) == ["MainMenuScene"]


def test_escape_on_the_results_goes_back_to_the_map(playing):
    finish(playing)
    playing.game.scenes.current.handle_event(KEY(pygame.K_ESCAPE))
    assert stack(playing.game)[-1] == "CampaignScene"


def test_the_results_animate_and_draw_at_every_stage(playing):
    finish(playing)
    results = playing.game.scenes.current
    for _ in range(300):  # près de cinq secondes : lignes, score, rang, étiquettes
        playing.game.step(1 / 60)
    assert results.time > 4


def test_the_rank_sound_plays_once_when_it_appears(playing, monkeypatch):
    finish(playing)
    sounds = []
    monkeypatch.setattr(playing.game.audio, "play", lambda name, *a, **k: sounds.append(name))
    for _ in range(400):
        playing.game.step(1 / 60)
    assert sounds.count("hack_done") == 1


def test_a_second_win_shows_the_improvement_in_the_records(playing):
    finish(playing, time=140, alerts=1, decoys=3)
    first = playing.game.progress.record_of("training")
    playing.game.scenes.pop()
    playing.restart()
    finish(playing, time=70)
    second = playing.game.progress.record_of("training")
    assert second.best_score > first.best_score and second.best_time < first.best_time and second.completions == 2


# --- Navigation --------------------------------------------------------------------------------------------------------
def test_open_main_menu_clears_the_stack(game):
    game.scenes.push(MainMenuScene(game))
    game.scenes.push(CampaignScene(game))
    navigation.open_main_menu(game)
    assert stack(game) == ["MainMenuScene"]


def test_open_campaign_builds_menu_then_map(game):
    navigation.open_campaign(game, game.campaign.get("outpost"))
    assert stack(game) == ["MainMenuScene", "CampaignScene"] and game.scenes.current.mission.id == "outpost"


def test_launch_and_start_play(game):
    navigation.open_campaign(game)
    mission = game.campaign.get("training")
    navigation.launch_mission(game, mission)
    assert stack(game)[-1] == "CrawlScene"
    navigation.start_play(game, mission)
    assert stack(game) == ["MainMenuScene", "CampaignScene", "PlayScene"] and game.scenes.current.mission is mission


# --- Le jeu garde sa progression ------------------------------------------------------------------------------------------
def test_a_new_game_remembers_the_previous_progress(game):
    win(game.progress, "training", time=61, decoys=1)
    game.progress.save()
    from game.core.game import Game

    again = Game()
    assert again.progress.record_of("training").best_score == 9500
    assert again.campaign.is_unlocked(again.campaign.get("outpost"), again.progress)


def test_progress_and_preferences_use_separate_files(game):
    import os
    from pathlib import Path

    game.prefs.save()
    win(game.progress, "training")
    game.progress.save()
    names = sorted(p.name for p in Path(os.environ["STAR_INFILTRATION_HOME"]).glob("*.json"))
    assert names == ["preferences.json", "progress.json"]
