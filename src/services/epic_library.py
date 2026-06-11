"""
Discover Epic Games Store titles installed via the Epic launcher (macOS and Windows).

Reads manifest JSON from Epic's ProgramData (Windows) or Application Support (macOS).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from host import IS_DARWIN
from host.launch import launch_via_open
from host.paths import epic_manifests_dir as _epic_manifests_dir_mac

__all__ = ["list_installed_epic_games"]


def _epic_manifests_dir() -> Path | None:
    if IS_DARWIN:
        return _epic_manifests_dir_mac()
    root = Path(os.environ.get("ProgramData", r"C:\ProgramData"))
    manifest_dir = root / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
    return manifest_dir if manifest_dir.is_dir() else None


def _try_load_manifest_json(path: Path) -> dict[str, Any] | None:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "utf-16-le"):
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


def _find_local_header(install_dir: Path) -> Path | None:
    """Best-effort cover in install folder (varies wildly by engine)."""
    candidates = (
        "Engine/Content/Slate/Brushes/GameLogo.png",
        "Engine/Content/Slate/Brushes/GameLogo.jpg",
        "Splash/Splash.bmp",
        "Splash/EdSplash.png",
    )
    for rel in candidates:
        p = install_dir / rel
        if p.is_file():
            return p
    for pat in ("**/Splash.bmp", "**/GameLogo.png", "**/GameLogo.jpg"):
        for p in install_dir.glob(pat):
            if p.is_file():
                return p
    return None


_SKIP_APPNAME_SUFFIXES: tuple[str, ...] = (
    "Editor",
    "EditorWin64",
    "EditorWin32",
    "EditorMac",
)


def _should_skip_manifest(data: dict[str, Any]) -> bool:
    app_name = str(data.get("AppName") or "").strip()
    if not app_name:
        return True
    skip_names = {"launcher", "ue_prereq", "eossdk", "eosoverlay", "easyanticheat", "battleeye"}
    if app_name.casefold() in skip_names:
        return True
    loc = str(data.get("InstallLocation") or "").strip()
    if not loc or not Path(loc).is_dir():
        return True
    low = app_name.casefold()
    if "unreal" in low and "editor" in low:
        return True
    for suf in _SKIP_APPNAME_SUFFIXES:
        if app_name.endswith(suf):
            return True
    return False


def list_installed_epic_games(*, fast: bool = False) -> list[dict[str, Any]]:
    manifest_dir = _epic_manifests_dir()
    if manifest_dir is None:
        return []

    by_key: dict[str, dict[str, Any]] = {}
    for item in sorted(manifest_dir.glob("*.item")):
        data = _try_load_manifest_json(item)
        if not data or _should_skip_manifest(data):
            continue

        ns = str(data.get("CatalogNamespace") or "unknown").strip() or "unknown"
        cid = str(data.get("CatalogItemId") or "").strip() or item.stem
        library_key = f"epic:{ns}:{cid}"

        display = str(data.get("DisplayName") or "").strip()
        app_name = str(data.get("AppName") or "").strip()
        title = display or app_name or "Epic Game"
        install = Path(str(data.get("InstallLocation") or "").strip())

        header = None if fast else _find_local_header(install)
        header_image = str(header) if header else ""

        uri = f"com.epicgames.launcher://apps/{app_name}?action=launch"
        launch = launch_via_open(uri)

        entry: dict[str, Any] = {
            "title": title,
            "appid": 0,
            "store": "epic",
            "library_key": library_key,
            "command": launch["command"],
            "args": launch["args"],
            "cwd": launch.get("cwd", ""),
            "header_image": header_image,
            "epic_app_name": app_name,
        }
        by_key[library_key] = entry

    return sorted(by_key.values(), key=lambda g: str(g["title"]).casefold())
