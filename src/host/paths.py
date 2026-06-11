"""Well-known install and data paths on macOS."""

from __future__ import annotations

from pathlib import Path

from host import IS_DARWIN


def application_support() -> Path:
    return Path.home() / "Library" / "Application Support"


def steam_install_dir() -> Path | None:
    if not IS_DARWIN:
        return None
    root = application_support() / "Steam"
    return root if root.is_dir() else None


def epic_manifests_dir() -> Path | None:
    if not IS_DARWIN:
        return None
    root = application_support() / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
    return root if root.is_dir() else None


def ea_scan_roots() -> list[Path]:
    if not IS_DARWIN:
        return []
    roots: list[Path] = []
    for base in (
        application_support() / "Electronic Arts",
        application_support() / "Origin",
        application_support() / "EA Desktop",
    ):
        if base.is_dir():
            roots.append(base)
    return roots


def rockstar_scan_roots() -> list[Path]:
    if not IS_DARWIN:
        return []
    roots: list[Path] = []
    rg = application_support() / "Rockstar Games"
    if rg.is_dir():
        roots.append(rg)
    for app in Path("/Applications").glob("*.app"):
        name = app.name.casefold()
        if any(hint in name for hint in ("rockstar", "gta", "red dead")):
            roots.append(app)
    return roots


def steam_client_launcher() -> Path | None:
    """Path to the Steam macOS client binary, if installed."""
    candidates = (
        Path("/Applications/Steam.app/Contents/MacOS/steam_osx"),
        application_support() / "Steam" / "Steam.AppBundle" / "Steam" / "Contents" / "MacOS" / "steam_osx",
    )
    for path in candidates:
        if path.is_file():
            return path
    return None
