"""Métadonnées de l'application et fichiers texte des installateurs : tout est pur (chaînes en entrée, chaînes en sortie), donc testé.

Une seule source : ici. Le `.spec` PyInstaller, le script Inno Setup, le `.desktop` Linux et l'`Info.plist` macOS en dérivent.
"""
from __future__ import annotations

APP_NAME = "Star Infiltration"
EXE_NAME = "StarInfiltration"  # nom du dossier / de l'exécutable produit par PyInstaller
SLUG = "star-infiltration"
BUNDLE_ID = "fr.lucas.starinfiltration"
AUTHOR = "Lucas Debeve"
COPYRIGHT = "© 2026 Lucas Debève"
DESCRIPTION = "Jeu d'infiltration en vue de dessus : un agent rebelle, un croiseur impérial, une seule chance."
CATEGORY_MAC = "public.app-category.action-games"
CATEGORY_LINUX = "Game;ActionGame;"
MIN_MACOS = "11.0"


def numeric_version(version: str) -> tuple[int, int, int, int]:
    """`1.2.3` (ou `1.2.3-beta`) -> (1, 2, 3, 0) : les ressources Windows veulent quatre entiers."""
    parts = []
    for chunk in version.split("-")[0].split(".")[:4]:
        parts.append(int("".join(c for c in chunk if c.isdigit()) or 0))
    return tuple(parts + [0] * (4 - len(parts)))  # type: ignore[return-value]


def windows_version_info(version: str) -> str:
    """Contenu du fichier de ressource de version que PyInstaller attache à l'`.exe` (propriétés du fichier sous Windows)."""
    a, b, c, d = numeric_version(version)
    return f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(filevers=({a}, {b}, {c}, {d}), prodvers=({a}, {b}, {c}, {d}), mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040c04b0', [
      StringStruct('CompanyName', '{AUTHOR}'),
      StringStruct('FileDescription', '{APP_NAME}'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('InternalName', '{EXE_NAME}'),
      StringStruct('LegalCopyright', '{COPYRIGHT}'),
      StringStruct('OriginalFilename', '{EXE_NAME}.exe'),
      StringStruct('ProductName', '{APP_NAME}'),
      StringStruct('ProductVersion', '{version}')])]),
    VarFileInfo([VarStruct('Translation', [1036, 1200])])
  ]
)
"""


def mac_info_plist(version: str) -> dict:
    """Clés de l'`Info.plist` du `.app` : nom, version, catégorie dans le Finder, copyright, système minimal."""
    return {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleShortVersionString": version,
        "CFBundleVersion": version,
        "NSHumanReadableCopyright": COPYRIGHT,
        "LSApplicationCategoryType": CATEGORY_MAC,
        "LSMinimumSystemVersion": MIN_MACOS,
        "NSHighResolutionCapable": True,
    }


def desktop_entry(exec_name: str = EXE_NAME, icon: str = SLUG) -> str:
    """Fichier `.desktop` (menu des applications Linux, AppImage)."""
    return f"""[Desktop Entry]
Type=Application
Name={APP_NAME}
GenericName=Jeu d'infiltration
Comment={DESCRIPTION}
Exec={exec_name}
Icon={icon}
Terminal=false
Categories={CATEGORY_LINUX}
"""


def apprun_script(exec_name: str = EXE_NAME) -> str:
    """Script `AppRun` d'une AppImage : lance l'exécutable livré à l'intérieur de l'image."""
    return f"""#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/{exec_name}/{exec_name}" "$@"
"""


def inno_script(version: str, source_dir: str, out_dir: str, out_name: str, icon: str) -> str:
    """Script Inno Setup (`iscc`) de l'installateur Windows : dossier de programme, raccourcis, désinstallation, icône."""
    return f"""; Généré par packaging/build.py : ne pas modifier à la main.
[Setup]
AppId={{{{{BUNDLE_ID}}}
AppName={APP_NAME}
AppVersion={version}
AppPublisher={AUTHOR}
AppCopyright={COPYRIGHT}
DefaultDirName={{autopf}}\\{APP_NAME}
DefaultGroupName={APP_NAME}
UninstallDisplayIcon={{app}}\\{EXE_NAME}.exe
SetupIconFile={icon}
OutputDir={out_dir}
OutputBaseFilename={out_name}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{{cm:CreateDesktopIcon}}"; GroupDescription: "{{cm:AdditionalIcons}}"; Flags: unchecked

[Files]
Source: "{source_dir}\\*"; DestDir: "{{app}}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{{group}}\\{APP_NAME}"; Filename: "{{app}}\\{EXE_NAME}.exe"
Name: "{{autodesktop}}\\{APP_NAME}"; Filename: "{{app}}\\{EXE_NAME}.exe"; Tasks: desktopicon

[Run]
Filename: "{{app}}\\{EXE_NAME}.exe"; Description: "{{cm:LaunchProgram,{APP_NAME}}}"; Flags: nowait postinstall skipifsilent
"""
