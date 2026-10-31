# -*- mode: python ; coding: utf-8 -*-
# PyInstaller : `pyinstaller packaging/star_infiltration.spec` (ou `python packaging/build.py exe`).
# L'icône, la version et les propriétés viennent de `packaging/metadata.py` et `packaging/icons/` ; la signature est faite par `build.py`.
# Produit un dossier `dist/StarInfiltration/` (et, sous macOS, `StarInfiltration.app`) qui n'a pas besoin de Python.
import re
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent  # noqa: F821 (SPECPATH est fourni par PyInstaller)
sys.path.insert(0, str(Path(SPECPATH)))  # noqa: F821 : `metadata` est à côté de ce fichier
import metadata  # noqa: E402

NAME = metadata.EXE_NAME
VERSION = re.search(r'^VERSION\s*=\s*"([^"]+)"', (ROOT / "game" / "settings.py").read_text(encoding="utf-8"), re.M).group(1)
ICONS = ROOT / "packaging" / "icons"
# Propriétés du fichier (Windows) : un fichier de ressource généré depuis `metadata.py`, avec la version du jeu.
VERSION_FILE = ROOT / "build" / "pyinstaller" / "version_info.txt"
VERSION_FILE.parent.mkdir(parents=True, exist_ok=True)
VERSION_FILE.write_text(metadata.windows_version_info(VERSION), encoding="utf-8")

a = Analysis(  # noqa: F821
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[(str(ROOT / "assets"), "assets")],  # cartes, campagne, sons : retrouvés via `settings.resource_root()`
    hiddenimports=["pygame._sdl2.controller"],  # la manette (import tardif dans `game/core/gamepad.py`)
    excludes=["tests", "pytest", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=NAME,
    console=False,  # pas de fenêtre de terminal ; `--version` et `--check` n'affichent rien sous Windows mais renvoient leur code
    disable_windowed_traceback=False,
    icon=str(ICONS / "star_infiltration.ico"),  # Windows ; ignoré ailleurs (le .app a son .icns, voir BUNDLE)
    version=str(VERSION_FILE),  # Windows : propriétés du fichier (éditeur, version, copyright)
)
coll = COLLECT(exe, a.binaries, a.datas, name=NAME)  # noqa: F821
app = BUNDLE(  # noqa: F821 : ignoré hors macOS
    coll,
    name=f"{NAME}.app",
    icon=str(ICONS / "star_infiltration.icns"),
    bundle_identifier=metadata.BUNDLE_ID,
    version=VERSION,
    info_plist=metadata.mac_info_plist(VERSION),
)
