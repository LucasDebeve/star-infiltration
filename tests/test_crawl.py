import pygame
import pytest

from game.settings import (
    COLORS,
    CRAWL_END_PAUSE,
    CRAWL_LOGO_TIME,
    CRAWL_PROLOGUE_TIME,
    CRAWL_SKIP_HOLD,
    CRAWL_STOP_SCALE,
)
from game.ui.crawl import (
    CRAWL,
    DONE,
    END,
    FOCAL,
    HORIZON,
    LOGO,
    PROLOGUE,
    T_MIN,
    TEXT_WIDTH,
    CrawlTimeline,
    HoldToSkip,
    PerspectiveCrawl,
    draw_logo,
    draw_prologue,
    justify_positions,
    plane_distance,
    render_crawl_text,
    scroll_distance,
    wrap_words,
)

CHAR = lambda s: 10 * len(s)  # noqa: E731  une police fictive : 10 px par caractère


# --- Mise en page -------------------------------------------------------------------------------
def test_words_are_wrapped_to_the_width():
    lines = wrap_words("un deux trois quatre cinq", CHAR, 140)
    assert lines == [["un", "deux", "trois"], ["quatre", "cinq"]]
    assert all(CHAR(" ".join(line)) <= 140 for line in lines)


def test_a_word_longer_than_the_width_stays_on_its_own_line():
    assert wrap_words("a anticonstitutionnellement b", CHAR, 50) == [["a"], ["anticonstitutionnellement"], ["b"]]


def test_empty_text_has_no_lines_and_spaces_are_collapsed():
    assert wrap_words("", CHAR, 100) == [] and wrap_words("  a   b  ", CHAR, 100) == [["a", "b"]]


def test_justified_lines_touch_both_edges():
    words = ["un", "deux", "trois"]
    placed = justify_positions(words, CHAR, 200, justify=True)
    assert placed[0] == ("un", 0)
    assert placed[-1][1] + CHAR("trois") == 200  # le dernier mot finit pile au bord droit
    gaps = [placed[i + 1][1] - placed[i][1] - CHAR(placed[i][0]) for i in range(2)]
    assert abs(gaps[0] - gaps[1]) <= 1  # espaces égaux, à un pixel d'arrondi près


def test_the_last_line_of_a_paragraph_is_not_stretched():
    placed = justify_positions(["un", "deux"], CHAR, 400, justify=False)
    assert placed == [("un", 0), ("deux", CHAR("un "))]


def test_a_single_word_is_never_stretched():
    assert justify_positions(["seul"], CHAR, 400, justify=True) == [("seul", 0)]
    assert justify_positions([], CHAR, 400, justify=True) == []


@pytest.fixture(scope="module")
def fonts():
    pygame.font.init()
    return {"body": pygame.font.Font(None, 40), "episode": pygame.font.Font(None, 46), "title": pygame.font.Font(None, 62)}


def yellow_pixels(surface):
    mask = pygame.mask.from_threshold(surface, COLORS["crawl_yellow"], (40, 40, 60, 255))
    return mask.count()


def test_the_flat_text_is_yellow_on_a_transparent_background(fonts):
    text = render_crawl_text("ÉPISODE I", "Titre", ["Un premier paragraphe assez long pour tenir sur plusieurs lignes dans la colonne."], fonts)
    assert text.get_width() == TEXT_WIDTH and text.get_height() > 150
    assert text.get_at((0, 0)).a == 0 and yellow_pixels(text) > 500


def test_more_paragraphs_make_a_taller_text(fonts):
    one = render_crawl_text("É", "T", ["Un paragraphe."], fonts)
    three = render_crawl_text("É", "T", ["Un paragraphe."] * 3, fonts)
    assert three.get_height() > one.get_height() + 100


def test_the_title_is_written_in_capitals_and_centered(fonts):
    text = render_crawl_text("ÉPISODE I", "Le titre", ["x"], fonts)
    title_rows = [y for y in range(60, 110) if any(text.get_at((x, y)).a for x in range(0, TEXT_WIDTH, 3))]
    xs = [x for y in title_rows for x in range(TEXT_WIDTH) if text.get_at((x, y)).a]
    assert title_rows and abs((min(xs) + max(xs)) / 2 - TEXT_WIDTH / 2) < 12


def test_paragraphs_are_justified_so_a_block_has_straight_edges(fonts):
    para = "Un deux trois quatre cinq six sept huit neuf dix onze douze treize quatorze quinze seize dix-sept dix-huit."
    text = render_crawl_text("É", "T", [para], fonts)
    # Première ligne du paragraphe (juste sous le titre) : elle commence à gauche et finit au bord droit.
    body_rows = [y for y in range(text.get_height()) if any(text.get_at((x, y)).a for x in (2, 4, TEXT_WIDTH - 4, TEXT_WIDTH - 6))]
    assert body_rows  # il y a des pixels contre les deux bords : le bloc est justifié


# --- Projection ---------------------------------------------------------------------------------------
def test_plane_distance_is_zero_at_the_bottom_and_grows_toward_the_horizon():
    assert plane_distance(1.0) == 0
    values = [plane_distance(t) for t in (1.0, 0.8, 0.5, 0.3, T_MIN)]
    assert values == sorted(values) and plane_distance(T_MIN) == pytest.approx(FOCAL * (1 / T_MIN - 1))


def test_the_scroll_stops_while_the_last_line_is_still_in_the_distance():
    assert scroll_distance(800) == pytest.approx(800 + plane_distance(CRAWL_STOP_SCALE))
    assert scroll_distance(800) < 800 + plane_distance(T_MIN)  # on n'attend pas qu'elle disparaisse à l'horizon
    assert T_MIN < CRAWL_STOP_SCALE < 1.0


@pytest.fixture(scope="module")
def flat(fonts):
    return render_crawl_text("ÉPISODE I", "Titre", ["Un paragraphe de texte suffisamment long pour remplir plusieurs lignes dans la colonne de lecture."] * 2, fonts)


def extent(surface, y):
    xs = [x for x in range(surface.get_width()) if surface.get_at((x, y))[:3] != (0, 0, 0)]
    return (min(xs), max(xs)) if xs else None


def test_nothing_is_drawn_before_the_text_enters_and_after_it_is_gone(flat):
    crawl = PerspectiveCrawl((1280, 720))
    for scroll in (-50, flat.get_height() + plane_distance(T_MIN) + 50):
        surface = pygame.Surface((1280, 720))
        crawl.draw(surface, flat, scroll)
        assert pygame.mask.from_threshold(surface, (0, 0, 0), (1, 1, 1, 255)).count() == 1280 * 720


def test_the_last_line_is_still_visible_when_the_scroll_stops(flat):
    crawl = PerspectiveCrawl((1280, 720))
    surface = pygame.Surface((1280, 720))
    crawl.draw(surface, flat, scroll_distance(flat.get_height()))
    assert pygame.mask.from_threshold(surface, (0, 0, 0), (1, 1, 1, 255)).count() < 1280 * 720  # encore un peu de texte au loin


def test_the_text_narrows_toward_the_horizon(flat):
    crawl = PerspectiveCrawl((1280, 720))
    surface = pygame.Surface((1280, 720))
    crawl.draw(surface, flat, 500)
    widths = []
    for y in range(300, 700, 40):  # on mesure la largeur occupée à diverses hauteurs
        row = [extent(surface, yy) for yy in range(y, y + 40) if extent(surface, yy)]
        if row:
            widths.append(max(hi - lo for lo, hi in row))
    assert len(widths) >= 4 and widths[0] < widths[-1]  # plus haut = plus étroit
    assert widths[-1] <= TEXT_WIDTH + 2


def test_text_stays_centered_and_inside_the_view(flat):
    crawl = PerspectiveCrawl((1280, 720))
    surface = pygame.Surface((1280, 720))
    crawl.draw(surface, flat, 700)
    pixels = [(x, y) for y in range(HORIZON, 720, 6) for x in range(0, 1280, 2) if surface.get_at((x, y))[:3] != (0, 0, 0)]
    assert pixels
    assert abs((min(x for x, _ in pixels) + max(x for x, _ in pixels)) / 2 - 640) < 20
    assert min(y for _, y in pixels) >= HORIZON


def test_the_distant_text_fades_out(flat):
    """Le même texte est plus pâle quand il est loin (haut de l'écran) que quand il est proche (bas)."""
    crawl = PerspectiveCrawl((1280, 720))

    def brightest_when_middle_line_is_at(y):
        t = (y - HORIZON) / (720 - HORIZON)
        surface = pygame.Surface((1280, 720))
        crawl.draw(surface, flat, flat.get_height() / 2 + plane_distance(t))  # la ligne du milieu tombe sur la rangée y
        return max(sum(surface.get_at((x, yy))[:3]) for yy in range(max(0, y - 25), min(720, y + 25)) for x in range(300, 980, 2))

    assert brightest_when_middle_line_is_at(crawl.top + 12) < 0.5 * brightest_when_middle_line_is_at(640)


def test_drawing_is_deterministic_and_scroll_moves_the_text(flat):
    crawl = PerspectiveCrawl((1280, 720))
    frames = []
    for scroll in (400, 400, 460):
        surface = pygame.Surface((1280, 720))
        crawl.draw(surface, flat, scroll)
        frames.append(pygame.image.tostring(surface, "RGB"))
    assert frames[0] == frames[1] != frames[2]


def test_other_screen_sizes_work(flat):
    for size in ((800, 600), (1920, 1080)):
        PerspectiveCrawl(size).draw(pygame.Surface(size), flat, 500)


def test_projection_rows_are_precomputed_from_the_horizon_down():
    crawl = PerspectiveCrawl((1280, 720))
    ys = [y for y, _, _ in crawl.rows]
    assert ys == sorted(ys) and ys[0] >= HORIZON and ys[-1] == 719
    assert [w for _, _, w in crawl.rows] == sorted(w for _, _, w in crawl.rows)  # plus large vers le bas
    assert crawl.rows[-1][1] == pytest.approx(plane_distance((719 - HORIZON) / (720 - HORIZON)))


# --- Déroulé ---------------------------------------------------------------------------------------------
def run(timeline, seconds, step=0.1):
    phases = [timeline.phase]
    for _ in range(round(seconds / step)):
        timeline.update(step)
        if timeline.phase != phases[-1]:
            phases.append(timeline.phase)
    return phases


def test_phases_follow_each_other_with_a_prologue():
    t = CrawlTimeline(distance=600, speed=60, has_prologue=True)
    assert run(t, 60) == [PROLOGUE, LOGO, CRAWL, END, DONE]


def test_without_a_prologue_it_starts_with_the_title():
    t = CrawlTimeline(distance=600, speed=60, has_prologue=False)
    assert t.phase == LOGO and run(t, 60) == [LOGO, CRAWL, END, DONE]


def test_the_total_duration_adds_up():
    t = CrawlTimeline(distance=600, speed=60, has_prologue=True)
    expected = CRAWL_PROLOGUE_TIME + CRAWL_LOGO_TIME + 600 / 60 + CRAWL_END_PAUSE
    run(t, expected - 0.5)
    assert not t.done
    run(t, 1.0)
    assert t.done
    assert t.elapsed == pytest.approx(expected, abs=0.11)  # il s'arrête dès que la dernière phase est finie


def test_scrolling_is_monotonic_capped_and_only_moves_during_the_crawl():
    t = CrawlTimeline(distance=600, speed=60, has_prologue=False)
    assert t.scroll == 0
    scrolls = []
    for _ in range(300):
        t.update(0.1)
        scrolls.append(t.scroll)
    assert scrolls == sorted(scrolls) and max(scrolls) == 600
    t.skip()
    assert t.scroll == 600  # une fois fini : tout le texte est passé


def test_the_text_does_not_move_during_the_title():
    t = CrawlTimeline(distance=600, speed=60, has_prologue=False)
    t.update(CRAWL_LOGO_TIME - 0.5)
    assert t.phase == LOGO and t.scroll == 0
    t.update(1.5)
    assert t.phase == CRAWL and 0 < t.scroll < 100


def test_phase_progress_goes_from_zero_to_one_and_resets():
    t = CrawlTimeline(distance=600, speed=60, has_prologue=True)
    assert t.phase_progress == 0
    t.update(CRAWL_PROLOGUE_TIME / 2)
    assert t.phase_progress == pytest.approx(0.5)
    t.update(CRAWL_PROLOGUE_TIME / 2 + 0.01)
    assert t.phase == LOGO and t.phase_progress < 0.05


def test_a_huge_time_step_still_ends_cleanly():
    t = CrawlTimeline(distance=600, speed=60, has_prologue=True)
    t.update(10_000)
    assert t.done


def test_skipping_ends_it_at_once_and_updates_after_the_end_do_nothing():
    t = CrawlTimeline(distance=600, speed=60, has_prologue=True)
    t.skip()
    assert t.done and t.phase == DONE
    elapsed = t.elapsed
    t.update(5)
    assert t.elapsed == elapsed


# --- Maintenir pour passer ------------------------------------------------------------------------------
def test_nothing_happens_without_a_key():
    skip = HoldToSkip()
    assert not skip.active and not skip.update(100) and skip.progress == 0


def test_only_the_skip_keys_count():
    skip = HoldToSkip()
    skip.press(pygame.K_a)
    assert not skip.active and not skip.update(100)


@pytest.mark.parametrize("key", [pygame.K_SPACE, pygame.K_RETURN, pygame.K_ESCAPE])
def test_holding_a_skip_key_long_enough_skips(key):
    skip = HoldToSkip()
    skip.press(key)
    assert skip.active
    results = [skip.update(0.1) for _ in range(int(CRAWL_SKIP_HOLD / 0.1) + 2)]
    assert results[0] is False and results[-1] is True


def test_a_quick_tap_does_not_skip():
    skip = HoldToSkip()
    skip.press(pygame.K_SPACE)
    assert not skip.update(CRAWL_SKIP_HOLD / 3)
    skip.release(pygame.K_SPACE)
    assert not skip.update(10)


def test_releasing_resets_the_gauge():
    skip = HoldToSkip()
    skip.press(pygame.K_SPACE)
    skip.update(CRAWL_SKIP_HOLD * 0.8)
    assert skip.progress == pytest.approx(0.8)
    skip.release(pygame.K_SPACE)
    skip.update(0.016)
    assert skip.progress == 0
    skip.press(pygame.K_SPACE)
    assert not skip.update(CRAWL_SKIP_HOLD * 0.5)  # il faut repartir de zéro


def test_the_gauge_keeps_going_while_any_skip_key_stays_down():
    skip = HoldToSkip()
    skip.press(pygame.K_SPACE)
    skip.press(pygame.K_RETURN)
    skip.update(0.5)
    skip.release(pygame.K_SPACE)  # il en reste une d'enfoncée
    assert skip.active and skip.update(0.6)


def test_hold_time_is_about_one_second():
    assert CRAWL_SKIP_HOLD == pytest.approx(1.0)


# --- Titre et accroche --------------------------------------------------------------------------------------
def test_the_logo_shrinks_away_and_fades():
    logo = pygame.Surface((400, 100), pygame.SRCALPHA)
    logo.fill((255, 232, 31, 255))

    def painted(progress):
        surface = pygame.Surface((1280, 720))
        draw_logo(surface, logo, progress)
        return pygame.mask.from_threshold(surface, (0, 0, 0), (1, 1, 1, 255)).count()

    empty = 1280 * 720
    sizes = [empty - painted(p) for p in (0.0, 0.3, 0.6, 0.9)]
    assert sizes == sorted(sizes, reverse=True) and sizes[0] > 0
    assert painted(1.0) == empty  # plus rien à la fin


def test_the_prologue_fades_in_and_out_and_is_visible_in_between():
    text = pygame.font.Font(None, 40).render("Il y a longtemps", True, COLORS["crawl_blue"])

    def brightness(progress):
        surface = pygame.Surface((1280, 720))
        draw_prologue(surface, text.copy(), progress, CRAWL_PROLOGUE_TIME)
        return sum(surface.get_at((x, 360))[2] for x in range(300, 980))

    assert brightness(0.0) == 0 and brightness(1.0) == 0
    assert brightness(0.5) > brightness(0.05) > 0 and brightness(0.5) > brightness(0.95)
