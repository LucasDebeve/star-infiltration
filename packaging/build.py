"""Empaquetage de Star Infiltration : `python packaging/build.py <cible>`.

Cibles :
    exe   exécutable sans Python (PyInstaller) pour le système sur lequel on lance la commande : Windows, macOS ou Linux
          (on ne compile pas pour un autre système : voir `.github/workflows/build.yml`, qui lance chaque système à tour de rôle)
    web   version navigateur (pygbag / WebAssembly), sans les gros sons (voir `--full`)
    zip   archive portable des sources, avec lanceurs `run.sh` et `run.bat`
    dmg   image disque macOS (`.dmg`) avec glisser-déposer vers Applications (macOS ; construit l'exécutable au besoin)
    installer   installateur Windows `-setup.exe` (Inno Setup, `iscc` dans le PATH ; Windows)
    appimage    `.AppImage` Linux (`appimagetool` dans le PATH ou `APPIMAGETOOL`)
    all   zip, exe et web
Signature (macOS, Windows) : automatique quand les variables d'environnement de `packaging/signing.py` sont définies.
Les résultats sont déposés dans `dist/`. Les fonctions pures (noms, liste des fichiers) sont testées ; les commandes extérieures
(PyInstaller, pygbag) ne sont lancées que par `main`.
"""
from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGING = ROOT / "packaging"
if str(PACKAGING) not in sys.path:  # `metadata` et `signing` sont à côté de ce fichier, qu'on le lance ou qu'on l'importe
    sys.path.insert(0, str(PACKAGING))
import metadata  # noqa: E402
import signing  # noqa: E402

NAME = "star-infiltration"
SOURCE_ITEMS = ("game", "assets", "main.py", "requirements.txt", "README.md")
LAUNCHERS = ("run.sh", "run.bat")
IGNORED_NAMES = {"__pycache__", ".DS_Store", "Thumbs.db", ".gitkeep"}
IGNORED_SUFFIXES = {".pyc", ".pyo"}
WEB_MAX_SOUND_BYTES = 4_000_000  # la version web écarte les sons plus gros (la musique du générique pèse 15 Mo)


def read_version(root: Path = ROOT) -> str:
    """La version du jeu, lue dans `game/settings.py` sans importer pygame."""
    match = re.search(r'^VERSION\s*=\s*"([^"]+)"', (root / "game" / "settings.py").read_text(encoding="utf-8"), re.M)
    if not match:
        raise SystemExit("VERSION introuvable dans game/settings.py")
    return match.group(1)


def platform_tag(system: str | None = None, machine: str | None = None) -> str:
    """Étiquette du système pour nommer les exécutables : windows-x64, macos-arm64, linux-x64..."""
    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()
    name = {"darwin": "macos", "windows": "windows", "linux": "linux"}.get(system, system)
    arch = {"x86_64": "x64", "amd64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(machine, machine)
    return f"{name}-{arch}"


def artifact_name(kind: str, version: str, tag: str | None = None) -> str:
    """Nom (sans extension) d'un livrable : `star-infiltration-1.0.0-macos-arm64`, `-web`, `-source`."""
    suffix = {"exe": tag or platform_tag(), "web": "web", "zip": "source"}[kind]
    return f"{NAME}-{version}-{suffix}"


def installer_name(kind: str, version: str, tag: str | None = None) -> str:
    """Nom complet (avec extension) d'un installateur : `...-macos-arm64.dmg`, `...-windows-x64-setup.exe`, `...-linux-x64.AppImage`."""
    suffix = {"dmg": ("", ".dmg"), "installer": ("-setup", ".exe"), "appimage": ("", ".AppImage")}[kind]
    return f"{NAME}-{version}-{tag or platform_tag()}{suffix[0]}{suffix[1]}"


def _keep(path: Path) -> bool:
    return not (IGNORED_NAMES & set(path.parts)) and path.suffix not in IGNORED_SUFFIXES


def source_files(root: Path = ROOT, lite: bool = False) -> list[Path]:
    """Fichiers à livrer, en chemins relatifs à `root`, triés. `lite` : sans les gros sons (version web)."""
    files: list[Path] = []
    for item in SOURCE_ITEMS:
        path = root / item
        if path.is_file():
            files.append(path.relative_to(root))
        elif path.is_dir():
            files += [f.relative_to(root) for f in sorted(path.rglob("*")) if f.is_file() and _keep(f.relative_to(root))]
    if lite:
        files = [f for f in files if not (f.parts[:2] == ("assets", "sounds") and (root / f).stat().st_size > WEB_MAX_SOUND_BYTES)]
    return sorted(files)


# --- Cibles ----------------------------------------------------------------------------------------------------
def build_zip(out_dir: Path, root: Path = ROOT) -> Path:
    """Archive portable : le jeu, ses lanceurs, et de quoi l'installer (`requirements.txt`)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    version = read_version(root)
    base = artifact_name("zip", version)
    target = out_dir / f"{base}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for rel in source_files(root):
            archive.write(root / rel, f"{base}/{rel.as_posix()}")
        for launcher in LAUNCHERS:
            info = zipfile.ZipInfo(f"{base}/{launcher}")
            info.external_attr = (0o755 if launcher.endswith(".sh") else 0o644) << 16  # le lanceur Unix reste exécutable
            archive.writestr(info, (root / "packaging" / "launchers" / launcher).read_bytes(), zipfile.ZIP_DEFLATED)
    return target


def run_command(command: list[str], **kwargs) -> None:
    """Lance une commande extérieure (isolée pour les tests) ; l'échec arrête la construction."""
    print("$", " ".join(command))
    subprocess.run(command, check=True, **kwargs)


def sign_macos(path: Path, env=os.environ, run=run_command) -> bool:
    """Signe un `.app` ou un `.dmg` si `CODESIGN_IDENTITY` est défini. Renvoie vrai s'il l'a signé."""
    if not signing.macos_signing_enabled(env):
        print(f"(non signé : CODESIGN_IDENTITY n'est pas défini) {path.name}")
        return False
    entitlements = PACKAGING / "entitlements.plist"
    run(signing.macos_sign_command(str(path), env["CODESIGN_IDENTITY"], str(entitlements) if path.suffix == ".app" else None))
    run(signing.macos_verify_command(str(path)))
    return True


def notarize_macos(dmg: Path, env=os.environ, run=run_command) -> bool:
    """Soumet le `.dmg` à Apple, attend le verdict, puis agrafe le ticket : le jeu s'ouvre sans avertissement, même hors ligne."""
    if not signing.notarization_enabled(env):
        print(f"(non notarisé : identifiants Apple absents) {dmg.name}")
        return False
    run(signing.notarize_command(str(dmg), env))
    run(signing.staple_command(str(dmg)))
    return True


def sign_windows(path: Path, env=os.environ, run=run_command) -> bool:
    """Signe un `.exe` avec `signtool` si le certificat est défini."""
    if not signing.windows_signing_enabled(env):
        print(f"(non signé : certificat Windows absent) {path.name}")
        return False
    run(signing.windows_sign_command(str(path), env))
    return True


def pyinstaller_dist(root: Path = ROOT) -> Path:
    return root / "build" / "pyinstaller" / "dist"


def run_pyinstaller(root: Path = ROOT) -> Path:
    """Construit le dossier `StarInfiltration` (et le `.app` sous macOS) ; renvoie le dossier `dist` de PyInstaller."""
    work = root / "build" / "pyinstaller"
    run_command(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", str(work / "dist"), "--workpath", str(work / "work"),
         str(root / "packaging" / "star_infiltration.spec")],
        cwd=root,
    )
    return work / "dist"


def build_exe(out_dir: Path, root: Path = ROOT) -> Path:
    """PyInstaller (dossier + archive). Il faut `pip install -r requirements-build.txt`. Signé quand les identifiants sont là."""
    out_dir.mkdir(parents=True, exist_ok=True)
    dist = run_pyinstaller(root)
    if platform.system() == "Darwin":
        sign_macos(dist / f"{metadata.EXE_NAME}.app")
    elif platform.system() == "Windows":
        sign_windows(dist / metadata.EXE_NAME / f"{metadata.EXE_NAME}.exe")
    base = out_dir / artifact_name("exe", read_version(root))
    return Path(shutil.make_archive(str(base), "zip", root_dir=dist, base_dir=metadata.EXE_NAME))


def build_dmg(out_dir: Path, root: Path = ROOT, run=run_command) -> Path:
    """Image disque : le `.app` et un raccourci vers /Applications. Signée puis notarisée si les identifiants sont là."""
    if platform.system() != "Darwin":
        raise SystemExit("Le .dmg se construit sous macOS (hdiutil).")
    out_dir.mkdir(parents=True, exist_ok=True)
    dist = pyinstaller_dist(root)
    app = dist / f"{metadata.EXE_NAME}.app"
    if not app.exists():
        dist = run_pyinstaller(root)
        app = dist / f"{metadata.EXE_NAME}.app"
        sign_macos(app)
    stage = root / "build" / "dmg"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    shutil.copytree(app, stage / app.name, symlinks=True)
    (stage / "Applications").symlink_to("/Applications")
    target = out_dir / installer_name("dmg", read_version(root))
    target.unlink(missing_ok=True)
    run(["hdiutil", "create", "-volname", metadata.APP_NAME, "-srcfolder", str(stage), "-ov", "-format", "UDZO", str(target)])
    if sign_macos(target):
        notarize_macos(target)
    return target


def build_installer(out_dir: Path, root: Path = ROOT, run=run_command) -> Path:
    """Installateur Windows (Inno Setup) : programme dans « Program Files » ou le dossier de l'utilisateur, raccourcis, désinstallation."""
    if platform.system() != "Windows":
        raise SystemExit("L'installateur Windows se construit sous Windows (Inno Setup : `iscc`).")
    out_dir.mkdir(parents=True, exist_ok=True)
    dist = pyinstaller_dist(root)
    source = dist / metadata.EXE_NAME
    if not source.exists():
        source = run_pyinstaller(root) / metadata.EXE_NAME
        sign_windows(source / f"{metadata.EXE_NAME}.exe")
    target = out_dir / installer_name("installer", read_version(root))
    script = root / "build" / "installer" / "star_infiltration.iss"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        metadata.inno_script(read_version(root), str(source), str(out_dir), target.stem, str(root / "packaging" / "icons" / "star_infiltration.ico")),
        encoding="utf-8",
    )
    run(["iscc", "/Qp", str(script)])
    sign_windows(target)
    return target


def stage_appdir(appdir: Path, built: Path, icon: Path) -> Path:
    """Arborescence d'une AppImage : `AppRun`, `.desktop`, icône à la racine, et l'exécutable PyInstaller dans `usr/bin/`."""
    if appdir.exists():
        shutil.rmtree(appdir)
    (appdir / "usr" / "bin").mkdir(parents=True)
    shutil.copytree(built, appdir / "usr" / "bin" / metadata.EXE_NAME)
    apprun = appdir / "AppRun"
    apprun.write_text(metadata.apprun_script(), encoding="utf-8")
    apprun.chmod(0o755)
    (appdir / f"{metadata.SLUG}.desktop").write_text(metadata.desktop_entry(), encoding="utf-8")
    shutil.copy2(icon, appdir / f"{metadata.SLUG}.png")
    return appdir


def build_appimage(out_dir: Path, root: Path = ROOT, run=run_command) -> Path:
    """AppImage Linux : un seul fichier exécutable, sans installation. Il faut `appimagetool` (PATH, ou variable APPIMAGETOOL)."""
    if platform.system() != "Linux":
        raise SystemExit("L'AppImage se construit sous Linux.")
    tool = os.environ.get("APPIMAGETOOL") or shutil.which("appimagetool")
    if not tool:
        raise SystemExit("appimagetool est introuvable (https://github.com/AppImage/appimagetool/releases) : mettez-le dans le PATH ou définissez APPIMAGETOOL.")
    out_dir.mkdir(parents=True, exist_ok=True)
    dist = pyinstaller_dist(root)
    if not (dist / metadata.EXE_NAME).exists():
        dist = run_pyinstaller(root)
    appdir = stage_appdir(root / "build" / "AppDir", dist / metadata.EXE_NAME, root / "packaging" / "icons" / "icon_256.png")
    target = out_dir / installer_name("appimage", read_version(root))
    run([tool, "--appimage-extract-and-run", str(appdir), str(target)], env={**os.environ, "ARCH": {"x64": "x86_64", "arm64": "aarch64"}.get(platform_tag().split("-")[1], "x86_64")})
    return target


def stage_web(stage: Path, root: Path = ROOT, full: bool = False) -> Path:
    """Prépare le dossier que pygbag empaquette : les sources, et `main.py` de la version web à la place de celui du bureau."""
    if stage.exists():
        shutil.rmtree(stage)
    for rel in source_files(root, lite=not full):
        if rel.name == "main.py" and len(rel.parts) == 1:
            continue
        target = stage / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, target)
    shutil.copy2(root / "packaging" / "web" / "main.py", stage / "main.py")
    return stage


def convert_sounds_to_ogg(stage: Path, ffmpeg: str | None = None, run=subprocess.run) -> list[Path]:
    """Convertit en .ogg les sons du paquet web (pygbag refuse les .wav : les navigateurs les lisent mal) et supprime les .wav.
    Sans ffmpeg, ne touche à rien et renvoie une liste vide : `build_web` laisse alors pygbag passer outre, avec un avertissement."""
    ffmpeg = ffmpeg or shutil.which("ffmpeg")
    if not ffmpeg:
        return []
    converted = []
    for wav in sorted((stage / "assets" / "sounds").glob("*.wav")):
        ogg = wav.with_suffix(".ogg")
        run([ffmpeg, "-y", "-loglevel", "error", "-i", str(wav), "-c:a", "libvorbis", "-q:a", "4", str(ogg)], check=True)
        wav.unlink()
        converted.append(ogg)
    return converted


def build_web(out_dir: Path, root: Path = ROOT, full: bool = False, strict: bool = False) -> Path:
    """pygbag : produit `build/web/archives/` (un dossier à déposer tel quel sur un hébergement statique)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stage = stage_web(root / "build" / "web" / NAME, root, full)
    command = [sys.executable, "-m", "pygbag", "--build", str(stage)]
    converted = convert_sounds_to_ogg(stage)
    if not converted and strict:
        raise SystemExit("ffmpeg est introuvable : la version web exige des sons .ogg (--strict). Installez ffmpeg.")
    if not converted:
        print("ATTENTION : ffmpeg est introuvable, les sons restent en .wav (pygbag est forcé de passer outre) : "
              "installez ffmpeg pour une version web dont le son fonctionne dans tous les navigateurs.")
        command.insert(-1, "--disable-sound-format-error")
    subprocess.run(command, check=True, cwd=root)
    built = stage / "build" / "web"
    base = out_dir / artifact_name("web", read_version(root))
    return Path(shutil.make_archive(str(base), "zip", root_dir=built))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Empaquette Star Infiltration.")
    parser.add_argument("target", choices=("exe", "web", "zip", "dmg", "installer", "appimage", "all"))
    parser.add_argument("--out", type=Path, default=ROOT / "dist", help="dossier des livrables (dist/ par défaut)")
    parser.add_argument("--strict", action="store_true", help="web : échoue si ffmpeg est absent (au lieu de garder des .wav) ; la CI s'en sert")
    parser.add_argument("--full", action="store_true", help="version web avec tous les sons, même les plus gros")
    args = parser.parse_args(argv)
    builders = {
        "zip": lambda: build_zip(args.out), "exe": lambda: build_exe(args.out), "web": lambda: build_web(args.out, full=args.full, strict=args.strict),
        "dmg": lambda: build_dmg(args.out), "installer": lambda: build_installer(args.out), "appimage": lambda: build_appimage(args.out),
    }
    for target in ("zip", "exe", "web") if args.target == "all" else (args.target,):
        print(f"== {target} ==")
        print("->", builders[target]())
    return 0


if __name__ == "__main__":
    sys.exit(main())
