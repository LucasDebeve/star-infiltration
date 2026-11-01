"""Empaquetage (E6) : chemins d'un exécutable figé, options de main.py, contrôle d'intégrité, outils de construction."""

import asyncio
import importlib.util
import os
import re
import zipfile
from pathlib import Path

import pytest

import main as entry
from game import selfcheck
from game.settings import ROOT_DIR, VERSION, resource_root

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def build():
    spec = importlib.util.spec_from_file_location("star_build", REPO / "packaging" / "build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- Chemins ---------------------------------------------------------------------------------------------------------
def test_resources_come_from_the_sources_by_default():
    assert resource_root(frozen_dir="", source_dir=Path("/x")) == Path("/x") and (ROOT_DIR / "assets" / "campaign.json").exists()


def test_a_frozen_executable_reads_its_resources_from_its_bundle():
    assert resource_root(frozen_dir="/tmp/_MEI123", source_dir=Path("/x")) == Path("/tmp/_MEI123")


def test_the_version_is_a_semantic_version():
    assert re.fullmatch(r"\d+\.\d+\.\d+", VERSION)


# --- main.py -----------------------------------------------------------------------------------------------------------------
def test_version_option_prints_and_quits(capsys):
    assert entry.main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == f"Star Infiltration {VERSION}"


def test_check_option_validates_the_shipped_game(capsys):
    assert entry.main(["--check"]) == 0
    assert "aucun problème" in capsys.readouterr().out


def test_check_option_reports_problems_with_a_failing_code(monkeypatch, capsys):
    monkeypatch.setattr(selfcheck, "run_checks", lambda: ["carte cassée"])
    assert entry.main(["--check"]) == 1
    out = capsys.readouterr().out
    assert "PROBLÈME : carte cassée" in out and "1 problème" in out


def test_portable_option_keeps_saves_next_to_the_game(monkeypatch):
    monkeypatch.delenv("STAR_INFILTRATION_HOME", raising=False)
    entry.main(["--version", "--portable"])  # --version quitte avant : rien n'est modifié
    assert "STAR_INFILTRATION_HOME" not in os.environ
    monkeypatch.setattr(selfcheck, "run_checks", lambda: [])
    entry.main(["--check", "--portable"])
    assert Path(os.environ["STAR_INFILTRATION_HOME"]) == entry.app_dir() / "data"


def test_portable_does_not_override_an_explicit_home(monkeypatch, tmp_path):
    monkeypatch.setenv("STAR_INFILTRATION_HOME", str(tmp_path))
    monkeypatch.setattr(selfcheck, "run_checks", lambda: [])
    entry.main(["--check", "--portable"])
    assert Path(os.environ["STAR_INFILTRATION_HOME"]) == tmp_path


def test_unknown_options_are_refused():
    with pytest.raises(SystemExit):
        entry.parse_args(["--piller"])


# --- Contrôle d'intégrité ---------------------------------------------------------------------------------------------------------
def test_the_shipped_game_passes_its_own_check():
    assert selfcheck.run_checks() == []


def test_a_missing_sound_is_reported(monkeypatch, tmp_path):
    monkeypatch.setattr(selfcheck, "SOUNDS_DIR", tmp_path)
    problems = selfcheck.run_checks()
    assert "son manquant : win.wav" in problems and "son manquant : amb_engine.wav" in problems


def test_the_optional_theme_music_is_not_required():
    assert "generique" in selfcheck.OPTIONAL_SOUNDS and "generique" not in selfcheck.REQUIRED_SOUNDS


def test_a_broken_campaign_is_reported_in_french(monkeypatch):
    import game.campaign as campaign

    monkeypatch.setattr(campaign, "load_campaign", lambda: (_ for _ in ()).throw(ValueError("Campagne : fichier illisible")))
    assert selfcheck.run_checks() == ["Campagne : fichier illisible"]


# --- Outils de construction (purs) -------------------------------------------------------------------------------------------------------
def test_the_build_script_reads_the_game_version(build):
    assert build.read_version() == VERSION


@pytest.mark.parametrize(
    "system,machine,tag",
    [("Darwin", "arm64", "macos-arm64"), ("Windows", "AMD64", "windows-x64"), ("Linux", "x86_64", "linux-x64"), ("Linux", "aarch64", "linux-arm64")],
)
def test_platform_tags(build, system, machine, tag):
    assert build.platform_tag(system, machine) == tag


def test_artifact_names(build):
    assert build.artifact_name("exe", "1.2.3", "macos-arm64") == "star-infiltration-1.2.3-macos-arm64"
    assert build.artifact_name("web", "1.2.3") == "star-infiltration-1.2.3-web"
    assert build.artifact_name("zip", "1.2.3") == "star-infiltration-1.2.3-source"


def test_the_source_list_has_the_game_and_nothing_else(build):
    files = {f.as_posix() for f in build.source_files()}
    assert {"main.py", "requirements.txt", "game/settings.py", "assets/campaign.json", "assets/maps/destroyer.txt", "assets/sounds/win.wav"} <= files
    assert not any(f.startswith(("tests/", "venv/", "dist/", "build/", ".git")) for f in files)
    assert not any("__pycache__" in f or f.endswith(".pyc") or f.endswith(".gitkeep") for f in files)


def test_the_source_list_is_sorted_and_free_of_duplicates(build):
    files = build.source_files()
    assert files == sorted(set(files))


def test_the_lite_list_drops_only_the_big_sounds(build):
    full, lite = {f.as_posix() for f in build.source_files()}, {f.as_posix() for f in build.source_files(lite=True)}
    dropped = full - lite
    assert dropped and all(f.startswith("assets/sounds/") for f in dropped)
    assert "assets/sounds/generique.wav" in dropped and "assets/sounds/win.wav" in lite and "assets/campaign.json" in lite
    assert all((REPO / f).stat().st_size > build.WEB_MAX_SOUND_BYTES for f in dropped)


def test_the_source_archive_is_complete_and_runnable(build, tmp_path):
    archive = build.build_zip(tmp_path)
    assert archive.name == f"star-infiltration-{VERSION}-source.zip"
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        base = f"star-infiltration-{VERSION}-source/"
        assert {base + "main.py", base + "run.sh", base + "run.bat", base + "assets/campaign.json", base + "requirements.txt"} <= set(names)
        assert not any("__pycache__" in n or n.endswith(".pyc") for n in names)
        assert (z.getinfo(base + "run.sh").external_attr >> 16) & 0o111  # le lanceur Unix est exécutable
        assert z.testzip() is None


def test_the_web_stage_swaps_the_entry_point_and_drops_big_sounds(build, tmp_path):
    stage = build.stage_web(tmp_path / "stage")
    main_text = (stage / "main.py").read_text(encoding="utf-8")
    assert "run_async" in main_text and "asyncio.run" in main_text
    assert (stage / "game" / "core" / "game.py").exists() and (stage / "assets" / "campaign.json").exists()
    assert not (stage / "assets" / "sounds" / "generique.wav").exists() and (stage / "assets" / "sounds" / "win.wav").exists()
    assert not (stage / "tests").exists()
    full = build.stage_web(tmp_path / "full", full=True)
    assert (full / "assets" / "sounds" / "generique.wav").exists()


def test_the_web_build_still_passes_the_integrity_check_without_the_theme_music(build, tmp_path, monkeypatch):
    stage = build.stage_web(tmp_path / "stage")
    monkeypatch.setattr(selfcheck, "SOUNDS_DIR", stage / "assets" / "sounds")
    assert not [p for p in selfcheck.run_checks() if "son manquant" in p]  # le générique est facultatif


def test_the_build_targets_are_the_documented_ones(build):
    with pytest.raises(SystemExit):
        build.main(["fusee"])


# --- Version web : boucle asynchrone ------------------------------------------------------------------------------------------------
def test_the_async_loop_hands_control_back_every_frame(game, monkeypatch):
    from game.core.scene import Scene

    class Counting(Scene):
        steps = 0

        def update(self, dt):
            Counting.steps += 1
            if Counting.steps == 5:
                self.game.quit()

    awaited = []
    real_sleep = asyncio.sleep

    async def spy(delay):
        awaited.append(delay)
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", spy)
    game.scenes.push(Counting(game))
    asyncio.run(game.run_async())
    assert Counting.steps == 5 and awaited == [0] * 5  # le navigateur reprend la main à chaque image
    import pygame

    pygame.display.init()  # run_async a quitté pygame, comme `run` : le fixture `game` s'y attend


# --- Fichiers de livraison ------------------------------------------------------------------------------------------------------------
def test_the_pyinstaller_spec_bundles_the_assets_and_the_gamepad():
    spec = (REPO / "packaging" / "star_infiltration.spec").read_text(encoding="utf-8")
    assert '"assets"' in spec and "pygame._sdl2.controller" in spec and "main.py" in spec and "BUNDLE" in spec and "excludes" in spec


def test_the_ci_builds_every_system_and_runs_the_tests_first():
    workflow = (REPO / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
    for needle in ("windows-latest", "macos-latest", "ubuntu-latest", "pytest", "main.py --check", "build.py exe", "build.py web", "build.py zip", "needs: test", "softprops/action-gh-release"):
        assert needle in workflow


def test_build_requirements_name_the_packagers():
    text = (REPO / "requirements-build.txt").read_text(encoding="utf-8")
    assert "pyinstaller" in text and "pygbag" in text and "-r requirements.txt" in text


def test_the_launchers_exist_and_start_the_game():
    sh, bat = (REPO / "packaging" / "launchers" / "run.sh").read_text(), (REPO / "packaging" / "launchers" / "run.bat").read_text()
    assert "main.py" in sh and "main.py" in bat and "requirements.txt" in sh and "requirements.txt" in bat


# --- Sons de la version web -------------------------------------------------------------------------------------------------------------
def test_the_audio_layer_falls_back_to_an_ogg_file(tmp_path, monkeypatch):
    from game.core.audio import Audio
    from game.core.preferences import Preferences

    (tmp_path / "ding.ogg").write_bytes(b"pas un vrai son")  # le contenu n'a pas d'importance : on vérifie le chemin choisi
    seen = []

    class FakeSound:
        def __init__(self, path):
            seen.append(Path(path).name)

    audio = Audio(Preferences(), sounds_dir=tmp_path)
    monkeypatch.setattr("pygame.mixer.Sound", FakeSound)
    audio._sound("ding")
    assert seen == ["ding.ogg"]
    (tmp_path / "ding2.wav").write_bytes(b"x")
    (tmp_path / "ding2.ogg").write_bytes(b"x")
    audio._sound("ding2")
    assert seen[-1] == "ding2.wav"  # le .wav reste prioritaire quand les deux existent


def test_the_integrity_check_accepts_ogg_sounds(monkeypatch, tmp_path):
    import shutil

    from game import selfcheck as check

    for name in sorted(set(check.REQUIRED_SOUNDS) | {s for s, _, _ in __import__("game.settings", fromlist=["x"]).AMBIENT_SOURCES.values()}):
        (tmp_path / f"{name}.ogg").write_bytes(b"x")
    monkeypatch.setattr(check, "SOUNDS_DIR", tmp_path)
    assert not [p for p in check.run_checks() if "son manquant" in p]
    shutil.rmtree(tmp_path)


def test_without_ffmpeg_the_web_sounds_are_left_alone(build, tmp_path):
    stage = build.stage_web(tmp_path / "s")
    before = sorted(p.name for p in (stage / "assets" / "sounds").iterdir())
    import shutil

    if shutil.which("ffmpeg") is None:
        assert build.convert_sounds_to_ogg(stage) == [] and sorted(p.name for p in (stage / "assets" / "sounds").iterdir()) == before


def test_with_ffmpeg_every_wav_becomes_an_ogg_and_disappears(build, tmp_path):
    stage = build.stage_web(tmp_path / "s")
    commands = []

    def fake_run(command, check):
        commands.append(command)
        Path(command[-1]).write_bytes(b"ogg")  # ffmpeg écrit le fichier de sortie

    converted = build.convert_sounds_to_ogg(stage, ffmpeg="/usr/bin/ffmpeg", run=fake_run)
    sounds = stage / "assets" / "sounds"
    assert converted and all(p.suffix == ".ogg" and p.exists() for p in converted) and not list(sounds.glob("*.wav"))
    assert all(c[0] == "/usr/bin/ffmpeg" and "libvorbis" in c for c in commands) and len(commands) == len(converted)


def test_the_web_entry_point_imports_pygame_so_pygbag_installs_it():
    """pygbag ne lit que les import de main.py : sans `import pygame` ici, le jeu plante dans le navigateur (pygame est un paquet vide)."""
    import ast

    tree = ast.parse((Path(__file__).resolve().parents[1] / "packaging" / "web" / "main.py").read_text(encoding="utf-8"))
    imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    assert "pygame" in imported
