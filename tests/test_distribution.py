"""Distribution (N1 à N3, L3, L4) : icône et métadonnées, signature, installateurs, linter, version web et commandes tactiles."""

import importlib.util
import struct
import sys
from pathlib import Path

import pygame
import pytest

from game.core import touch
from game.core.input import read_input
from game.settings import TOUCH_BUTTON_RADIUS, TOUCH_STICK_RADIUS, VERSION

REPO = Path(__file__).resolve().parent.parent
PACKAGING = REPO / "packaging"


def load(name, path):
    if str(PACKAGING) not in sys.path:
        sys.path.insert(0, str(PACKAGING))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def build():
    return load("star_build2", PACKAGING / "build.py")


@pytest.fixture(scope="module")
def meta():
    return load("star_metadata", PACKAGING / "metadata.py")


@pytest.fixture(scope="module")
def sign():
    return load("star_signing", PACKAGING / "signing.py")


@pytest.fixture(scope="module")
def icons():
    return load("star_icons", PACKAGING / "icons.py")


# --- N1 : icône et métadonnées -----------------------------------------------------------------------------------------------------
def test_the_icon_files_are_shipped():
    for name in ("star_infiltration.ico", "star_infiltration.icns", "icon_256.png", "icon_1024.png"):
        assert (PACKAGING / "icons" / name).stat().st_size > 500, name
    assert (REPO / "assets" / "icon.png").exists()


def test_the_ico_lists_png_images_of_the_right_sizes(icons):
    data = (PACKAGING / "icons" / "star_infiltration.ico").read_bytes()
    reserved, kind, count = struct.unpack_from("<HHH", data)
    assert (reserved, kind) == (0, 1) and count == len(icons.ICO_SIZES)
    sizes = []
    for i in range(count):
        width, _, _, _, _, bits, length, offset = struct.unpack_from("<BBBBHHII", data, 6 + 16 * i)
        sizes.append(width or 256)
        assert data[offset : offset + 8] == b"\x89PNG\r\n\x1a\n" and offset + length <= len(data)
    assert sizes == sorted(icons.ICO_SIZES)


def test_the_icns_has_the_expected_elements(icons):
    data = (PACKAGING / "icons" / "star_infiltration.icns").read_bytes()
    assert data[:4] == b"icns" and struct.unpack(">I", data[4:8])[0] == len(data)
    kinds, position = [], 8
    while position < len(data):
        kind, length = data[position : position + 4], struct.unpack(">I", data[position + 4 : position + 8])[0]
        assert data[position + 8 : position + 16] == b"\x89PNG\r\n\x1a\n"
        kinds.append(kind)
        position += length
    assert kinds == [icons.ICNS_TYPES[s] for s in sorted(icons.ICNS_TYPES)] and position == len(data)


def test_the_icon_writers_are_pure(icons):
    fake = {16: b"\x89PNG-a", 256: b"\x89PNG-b"}
    ico = icons.build_ico(fake)
    assert struct.unpack_from("<H", ico, 4)[0] == 2 and ico.endswith(b"\x89PNG-b")
    assert icons.build_icns({99: b"x"}) == b"icns" + struct.pack(">I", 8)  # taille inconnue : ignorée


def test_the_rendered_icon_is_not_blank(icons):
    pygame.init()
    surface = icons.render(64)
    assert surface.get_size() == (64, 64) and len({tuple(surface.get_at((x, y))) for x in range(0, 64, 4) for y in range(0, 64, 4)}) > 6


def test_the_window_icon_is_set_by_the_game(game):
    assert pygame.image.load(str(REPO / "assets" / "icon.png")).get_size() == (256, 256)


def test_numeric_versions(meta):
    assert meta.numeric_version("1.2.3") == (1, 2, 3, 0)
    assert meta.numeric_version("2.0") == (2, 0, 0, 0)
    assert meta.numeric_version("1.4.0-beta") == (1, 4, 0, 0)


def test_windows_properties_carry_the_version_and_publisher(meta):
    text = meta.windows_version_info("1.2.3")
    assert "filevers=(1, 2, 3, 0)" in text and "'ProductVersion', '1.2.3'" in text
    assert meta.AUTHOR in text and meta.COPYRIGHT in text and "StarInfiltration.exe" in text
    compile(text.split("\n", 1)[1], "version_info", "eval")  # un fichier de ressource PyInstaller est une expression Python


def test_the_mac_plist_has_what_the_finder_shows(meta):
    plist = meta.mac_info_plist("1.2.3")
    assert plist["CFBundleShortVersionString"] == "1.2.3" and plist["LSApplicationCategoryType"].endswith("games")
    assert plist["NSHumanReadableCopyright"] == meta.COPYRIGHT and plist["NSHighResolutionCapable"] is True


def test_the_desktop_entry_and_apprun(meta):
    entry = meta.desktop_entry()
    assert "Name=Star Infiltration" in entry and "Categories=Game;" in entry and f"Icon={meta.SLUG}" in entry
    assert meta.apprun_script().startswith("#!/bin/sh") and "usr/bin/StarInfiltration/StarInfiltration" in meta.apprun_script()


def test_the_spec_uses_the_icons_and_metadata():
    spec = (PACKAGING / "star_infiltration.spec").read_text(encoding="utf-8")
    for needle in ("star_infiltration.ico", "star_infiltration.icns", "windows_version_info", "mac_info_plist", "hiddenimports"):
        assert needle in spec


# --- N2 : signature -----------------------------------------------------------------------------------------------------------------------
def test_nothing_is_signed_without_credentials(sign):
    assert not sign.macos_signing_enabled({}) and not sign.notarization_enabled({}) and not sign.windows_signing_enabled({})
    assert not sign.notarization_enabled({"CODESIGN_IDENTITY": "x"})  # signer ne suffit pas pour notariser
    assert not sign.windows_signing_enabled({"WINDOWS_CERT_FILE": "a.pfx"})  # il faut aussi le mot de passe


def test_macos_signing_uses_the_hardened_runtime(sign):
    command = sign.macos_sign_command("Jeu.app", "Developer ID Application: X (ABC)", "e.plist")
    assert command[0] == "codesign" and "--options" in command and command[command.index("--options") + 1] == "runtime"
    assert "--timestamp" in command and command[-1] == "Jeu.app" and command[command.index("--entitlements") + 1] == "e.plist"
    assert "--entitlements" not in sign.macos_sign_command("Jeu.dmg", "x")


def test_notarization_prefers_the_keychain_profile(sign):
    profile = sign.notarize_command("Jeu.dmg", {"NOTARY_PROFILE": "p", "APPLE_ID": "a"})
    assert profile[:4] == ["xcrun", "notarytool", "submit", "Jeu.dmg"] and "--wait" in profile and profile[-2:] == ["--keychain-profile", "p"]
    apple = {"APPLE_ID": "a@b.c", "APPLE_TEAM_ID": "T", "APPLE_APP_PASSWORD": "pw"}
    assert sign.notarization_enabled({"CODESIGN_IDENTITY": "x", **apple})
    assert "--apple-id" in sign.notarize_command("Jeu.dmg", apple) and sign.staple_command("Jeu.dmg")[-1] == "Jeu.dmg"


def test_windows_signing_command(sign):
    env = {"WINDOWS_CERT_FILE": "c.pfx", "WINDOWS_CERT_PASSWORD": "pw"}
    command = sign.windows_sign_command("a.exe", env)
    assert command[:2] == ["signtool", "sign"] and "SHA256" in command and command[-1] == "a.exe" and sign.TIMESTAMP_URL in command
    assert "http://ts.example" in sign.windows_sign_command("a.exe", {**env, "WINDOWS_TIMESTAMP_URL": "http://ts.example"})


def test_build_signs_only_with_credentials(build, tmp_path):
    ran = []
    app = tmp_path / "Jeu.app"
    assert build.sign_macos(app, {}, ran.append) is False and ran == []
    assert build.sign_macos(app, {"CODESIGN_IDENTITY": "id"}, ran.append) is True
    assert [c[0] for c in ran] == ["codesign", "codesign"] and "--entitlements" in ran[0]
    ran.clear()
    assert build.sign_macos(tmp_path / "Jeu.dmg", {"CODESIGN_IDENTITY": "id"}, ran.append) and "--entitlements" not in ran[0]


def test_build_notarizes_then_staples(build, tmp_path):
    ran = []
    env = {"CODESIGN_IDENTITY": "id", "NOTARY_PROFILE": "p"}
    assert build.notarize_macos(tmp_path / "Jeu.dmg", {}, ran.append) is False
    assert build.notarize_macos(tmp_path / "Jeu.dmg", env, ran.append) is True
    assert [c[1] for c in ran] == ["notarytool", "stapler"]


def test_build_signs_windows_exe_only_with_a_certificate(build, tmp_path):
    ran = []
    assert build.sign_windows(tmp_path / "a.exe", {}, ran.append) is False and ran == []
    assert build.sign_windows(tmp_path / "a.exe", {"WINDOWS_CERT_FILE": "c", "WINDOWS_CERT_PASSWORD": "p"}, ran.append) is True and ran[0][0] == "signtool"


def test_the_entitlements_file_is_a_valid_plist():
    import plistlib

    entitlements = plistlib.loads((PACKAGING / "entitlements.plist").read_bytes())
    assert entitlements["com.apple.security.cs.disable-library-validation"] is True


# --- N3 : installateurs -----------------------------------------------------------------------------------------------------------------
def test_installer_names(build):
    assert build.installer_name("dmg", "1.0.0", "macos-arm64") == "star-infiltration-1.0.0-macos-arm64.dmg"
    assert build.installer_name("installer", "1.0.0", "windows-x64") == "star-infiltration-1.0.0-windows-x64-setup.exe"
    assert build.installer_name("appimage", "1.0.0", "linux-x64") == "star-infiltration-1.0.0-linux-x64.AppImage"


def test_the_inno_script_installs_the_game_with_shortcuts(meta):
    script = meta.inno_script("1.2.3", r"C:\dist\StarInfiltration", r"C:\out", "setup-name", r"C:\i.ico")
    assert "AppVersion=1.2.3" in script and r'Source: "C:\dist\StarInfiltration\*"' in script
    assert "OutputBaseFilename=setup-name" in script and "AppId={{fr.lucas.starinfiltration}" in script
    assert "{autopf}" in script and "[Icons]" in script and "{cm:LaunchProgram,Star Infiltration}" in script


def test_the_appdir_is_laid_out_for_appimagetool(build, meta, tmp_path):
    built = tmp_path / "built"
    built.mkdir()
    (built / meta.EXE_NAME).write_text("bin")
    icon = tmp_path / "i.png"
    icon.write_bytes(b"png")
    appdir = build.stage_appdir(tmp_path / "AppDir", built, icon)
    assert (appdir / "usr" / "bin" / meta.EXE_NAME / meta.EXE_NAME).read_text() == "bin"
    assert (appdir / "AppRun").stat().st_mode & 0o111 and (appdir / f"{meta.SLUG}.desktop").exists() and (appdir / f"{meta.SLUG}.png").exists()


def test_installers_refuse_the_wrong_system(build, monkeypatch, tmp_path):
    monkeypatch.setattr(build.platform, "system", lambda: "Plan9")
    for builder in (build.build_dmg, build.build_installer, build.build_appimage):
        with pytest.raises(SystemExit):
            builder(tmp_path)


def test_the_new_build_targets_exist(build):
    source = (PACKAGING / "build.py").read_text(encoding="utf-8")
    for target in ('"dmg"', '"installer"', '"appimage"', "--strict"):
        assert target in source


# --- L3 : linter ---------------------------------------------------------------------------------------------------------------------------
def test_ruff_is_configured_and_part_of_the_dev_requirements():
    config = (REPO / "ruff.toml").read_text(encoding="utf-8")
    assert "[lint]" in config and '"F"' in config and "line-length" in config
    assert "ruff" in (REPO / "requirements-dev.txt").read_text(encoding="utf-8")


def test_ruff_passes_on_the_project():
    import shutil
    import subprocess

    ruff = shutil.which("ruff")
    if ruff is None:
        pytest.skip("ruff n'est pas installé")
    result = subprocess.run([ruff, "check", "--no-cache", "."], cwd=REPO, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout[-2000:]


# --- L4 : version web --------------------------------------------------------------------------------------------------------------------
def workflow():
    return (REPO / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")


def test_the_ci_lints_installs_ffmpeg_and_checks_the_web_build_in_a_browser():
    text = workflow()
    assert "ruff check ." in text and "needs: lint" in text
    assert "apt-get install -y ffmpeg" in text and "build.py web --strict" in text
    assert "packaging/web/smoke.py" in text and "playwright install" in text


def test_the_ci_builds_every_installer_and_signs_with_secrets_only():
    text = workflow()
    for needle in ("build.py dmg", "build.py installer", "build.py appimage", "secrets.CODESIGN_IDENTITY", "secrets.WINDOWS_CERT_PFX", "dist/*.AppImage"):
        assert needle in text


def test_a_missing_ffmpeg_fails_a_strict_web_build(build, monkeypatch, tmp_path):
    monkeypatch.setattr(build.shutil, "which", lambda name: None)
    monkeypatch.setattr(build, "stage_web", lambda stage, root, full: tmp_path)
    with pytest.raises(SystemExit, match="ffmpeg"):
        build.build_web(tmp_path, strict=True)


def test_the_smoke_test_recognises_python_errors_in_the_console():
    smoke = load("star_smoke", PACKAGING / "web" / "smoke.py")
    messages = ["Ready", "Traceback (most recent call last):", "GET favicon.ico Error: 404", "pygame.error: no mixer"]
    assert smoke.console_problems(messages) == ["Traceback (most recent call last):", "pygame.error: no mixer"]
    assert smoke.is_blank([(0, 0, 0)] * 100) and not smoke.is_blank([(i, i, i) for i in range(20)])
    assert smoke.main([]) == 2


# --- Commandes tactiles ------------------------------------------------------------------------------------------------------------------
SIZE = (1280, 720)


def finger(kind, finger_id, px, py):
    return pygame.event.Event(kind, finger_id=finger_id, x=px / SIZE[0], y=py / SIZE[1], dx=0, dy=0, pressure=1.0, touch_id=1)


@pytest.fixture
def pad():
    return touch.TouchControls()


def center(name):
    return touch.layout(SIZE)[name][0]


def test_buttons_fit_on_screen_without_overlapping():
    spots = touch.layout(SIZE)
    assert set(spots) == set(touch.BUTTONS)
    for name, (position, radius) in spots.items():
        assert radius == TOUCH_BUTTON_RADIUS and radius <= position.x <= SIZE[0] - radius and radius <= position.y <= SIZE[1] - radius
    centres = [p for p, _ in spots.values()]
    assert all(a.distance_to(b) > 2 * TOUCH_BUTTON_RADIUS for i, a in enumerate(centres) for b in centres[i + 1 :])


def test_touch_controls_stay_hidden_until_a_finger_lands(pad):
    assert not pad.active and pad.move().length() == 0
    assert pad.process(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_a), SIZE) is None  # pas un événement de doigt
    pad.process(finger(pygame.FINGERDOWN, 1, 300, 300), SIZE)
    assert pad.active


def test_the_left_thumb_makes_a_virtual_stick(pad):
    pad.process(finger(pygame.FINGERDOWN, 1, 200, 400), SIZE)
    assert pad.move().length() == 0  # posé : au repos
    pad.process(finger(pygame.FINGERMOTION, 1, 200 + TOUCH_STICK_RADIUS / 2, 400), SIZE)
    assert tuple(pad.move()) == pytest.approx((0.5, 0))
    pad.process(finger(pygame.FINGERMOTION, 1, 200, 400 + TOUCH_STICK_RADIUS * 3), SIZE)
    assert tuple(pad.move()) == pytest.approx((0, 1))  # plafonné à 1
    pad.process(finger(pygame.FINGERUP, 1, 200, 800), SIZE)
    assert pad.move().length() == 0


def test_a_finger_on_the_right_half_does_not_make_a_stick(pad):
    pad.process(finger(pygame.FINGERDOWN, 1, 900, 200), SIZE)
    assert pad.move().length() == 0


def test_held_buttons_are_read_every_frame(pad):
    pad.process(finger(pygame.FINGERDOWN, 2, *center("run")), SIZE)
    pad.process(finger(pygame.FINGERDOWN, 3, *center("crouch")), SIZE)
    assert pad.run() and pad.crouch() and not pad.interact()
    pad.process(finger(pygame.FINGERUP, 2, 0, 0), SIZE)
    assert not pad.run() and pad.crouch()


def test_interact_presses_the_key_and_holds_it(pad):
    down = pad.process(finger(pygame.FINGERDOWN, 4, *center("interact")), SIZE)
    assert [(e.type, e.key) for e in down] == [(pygame.KEYDOWN, pygame.K_e)] and pad.interact()
    up = pad.process(finger(pygame.FINGERUP, 4, 0, 0), SIZE)
    assert [(e.type, e.key) for e in up] == [(pygame.KEYUP, pygame.K_e)] and not pad.interact()


def test_taps_become_the_keys_of_their_actions(pad):
    expected = {"throw": pygame.K_f, "disguise": pygame.K_u, "pause": pygame.K_ESCAPE, "restart": pygame.K_r}
    for finger_id, (name, key) in enumerate(expected.items(), start=10):
        events = pad.process(finger(pygame.FINGERDOWN, finger_id, *center(name)), SIZE)
        assert [(e.type, e.key) for e in events] == [(pygame.KEYDOWN, key)], name
        assert pad.process(finger(pygame.FINGERUP, finger_id, 0, 0), SIZE) == []


def test_the_game_reads_touch_input_like_any_other_device(game, pad, monkeypatch):
    monkeypatch.setattr(touch, "current", pad)
    pad.process(finger(pygame.FINGERDOWN, 1, 200, 400), SIZE)
    pad.process(finger(pygame.FINGERMOTION, 1, 200 + TOUCH_STICK_RADIUS, 400), SIZE)
    pad.process(finger(pygame.FINGERDOWN, 2, *center("run")), SIZE)
    state = read_input()
    assert state.move.x == pytest.approx(1.0) and state.run and not state.crouch


def test_the_overlay_draws_only_once_active(game, pad):
    font = pygame.font.Font(None, 22)
    surface = pygame.Surface(SIZE)
    pad.draw(surface, font)
    blank = pygame.image.tostring(surface, "RGB")
    pad.process(finger(pygame.FINGERDOWN, 1, 200, 400), SIZE)
    pad.draw(surface, font)
    assert pygame.image.tostring(surface, "RGB") != blank


def test_game_steps_translate_fingers_into_keys(game, monkeypatch):
    from game.core.input import InputState
    from game.scenes import play_scene

    monkeypatch.setattr(play_scene, "read_input", lambda: InputState())
    scene = play_scene.PlayScene(game, REPO / "assets" / "maps" / "training.txt")
    game.scenes.push(scene)
    pygame.event.clear()
    pygame.event.post(finger(pygame.FINGERDOWN, 7, *center("pause")))
    game.step(1 / 60)
    assert type(game.scenes.current).__name__ == "PauseScene" and touch.current.active


def test_the_version_is_still_read_from_the_settings(build):
    assert build.read_version() == VERSION
