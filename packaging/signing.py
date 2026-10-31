"""Signature et notarisation des livrables (N2) : on construit les commandes (pur, testé), `build.py` les lance.

Rien n'est signé sans identifiants : sans variables d'environnement, les fonctions `*_enabled` répondent faux et la construction produit
des livrables non signés (avec un avertissement du système au premier lancement). En CI, les identifiants viennent des secrets du dépôt.

macOS : `CODESIGN_IDENTITY` (« Developer ID Application: Nom (ÉQUIPE) ») signe le `.app` et le `.dmg` (runtime durci, avec
`packaging/entitlements.plist`) ; `NOTARY_PROFILE` (profil `xcrun notarytool store-credentials`), ou le trio `APPLE_ID` +
`APPLE_TEAM_ID` + `APPLE_APP_PASSWORD`, soumet le `.dmg` à Apple puis agrafe le ticket.
Windows : `WINDOWS_CERT_FILE` (un `.pfx`) et `WINDOWS_CERT_PASSWORD` signent l'exécutable et l'installateur avec `signtool`
(horodatage `WINDOWS_TIMESTAMP_URL`, DigiCert par défaut).
"""
from __future__ import annotations

TIMESTAMP_URL = "http://timestamp.digicert.com"


def macos_signing_enabled(env) -> bool:
    return bool(env.get("CODESIGN_IDENTITY"))


def notarization_enabled(env) -> bool:
    return macos_signing_enabled(env) and bool(env.get("NOTARY_PROFILE") or all(env.get(k) for k in ("APPLE_ID", "APPLE_TEAM_ID", "APPLE_APP_PASSWORD")))


def windows_signing_enabled(env) -> bool:
    return bool(env.get("WINDOWS_CERT_FILE") and env.get("WINDOWS_CERT_PASSWORD"))


def macos_sign_command(path: str, identity: str, entitlements: str | None = None) -> list[str]:
    """`codesign` d'un `.app` (ou d'un `.dmg`) : signature récursive, runtime durci et horodatage (exigés par la notarisation)."""
    command = ["codesign", "--force", "--deep", "--timestamp", "--options", "runtime", "--sign", identity]
    if entitlements:
        command += ["--entitlements", entitlements]
    return command + [path]


def macos_verify_command(path: str) -> list[str]:
    return ["codesign", "--verify", "--deep", "--strict", "--verbose=2", path]


def notarize_command(archive: str, env) -> list[str]:
    """`notarytool submit --wait` : attend le verdict d'Apple. Le profil du trousseau prime sur l'identifiant Apple."""
    base = ["xcrun", "notarytool", "submit", archive, "--wait"]
    if env.get("NOTARY_PROFILE"):
        return base + ["--keychain-profile", env["NOTARY_PROFILE"]]
    return base + ["--apple-id", env["APPLE_ID"], "--team-id", env["APPLE_TEAM_ID"], "--password", env["APPLE_APP_PASSWORD"]]


def staple_command(archive: str) -> list[str]:
    return ["xcrun", "stapler", "staple", archive]


def windows_sign_command(path: str, env) -> list[str]:
    """`signtool sign` d'un `.exe` : SHA-256, horodatage RFC 3161."""
    return [
        "signtool", "sign", "/fd", "SHA256", "/f", env["WINDOWS_CERT_FILE"], "/p", env["WINDOWS_CERT_PASSWORD"],
        "/tr", env.get("WINDOWS_TIMESTAMP_URL") or TIMESTAMP_URL, "/td", "SHA256", path,
    ]
