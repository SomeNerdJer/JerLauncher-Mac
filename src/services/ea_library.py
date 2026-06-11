"""
Discover EA PC titles on Windows and macOS.

On Windows, prefers the EA app encrypted install list under ProgramData.
On macOS, scans Application Support / Applications for EA game bundles.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from host import IS_DARWIN
from host.launch import launch_app_bundle
from host.paths import ea_scan_roots
from services.ea_desktop_is import try_load_ea_desktop_games

try:
    import winreg
except ImportError:  # pragma: no cover
    winreg = None  # type: ignore

__all__ = ["list_installed_ea_games"]

if winreg is not None:
    _EA_REG_PARENTS: tuple[tuple[int, str], ...] = (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\EA Games"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Origin Games"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\EA Games"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\EA Games"),
    )
else:  # pragma: no cover
    _EA_REG_PARENTS = ()

_INSTALL_VALUE_NAMES: tuple[str, ...] = ("Install Dir", "InstallDir", "InstallPath")

_SKIP_SUBKEYS: frozenset[str] = frozenset(
    k.casefold()
    for k in (
        "EA Core",
        "EADM",
    )
)

_SKIP_FOLDER_NAMES: frozenset[str] = frozenset(
    k.casefold()
    for k in (
        "ea desktop",
        "ea app",
        "origin",
        "ea installer",
        "eaanticheat",
        "easyanticheat",
        "electronic arts",
    )
)

_APP_SKIP_RE = re.compile(
    r"(redist|unins|setup|touchup|activation|datacollect|crash|error|repair|vc_redist|"
    r"dxsetup|dotnet|easyanticheat|eac_|origin(?:thin)?setup|launcher|helper|updater)",
    re.IGNORECASE,
)

_EXE_SKIP_RE = re.compile(
    r"(redist|unins|setup|touchup|activation|datacollect|crash|error|repair|vc_redist|"
    r"dxsetup|dotnet|easyanticheat|eac_|origin(?:thin)?setup)\.exe$",
    re.IGNORECASE,
)


def _read_install_dir(key_path: str, hive: int) -> Path | None:
    try:
        with winreg.OpenKey(hive, key_path) as key:
            for name in _INSTALL_VALUE_NAMES:
                try:
                    raw, _ = winreg.QueryValueEx(key, name)
                except OSError:
                    continue
                p = Path(str(raw).strip().strip('"'))
                if p.is_dir():
                    return p
            try:
                gdf, _ = winreg.QueryValueEx(key, "GDFBinary")
                gp = Path(str(gdf).strip().strip('"'))
                if gp.is_file():
                    cand = gp.parent
                    if cand.is_dir():
                        return cand
            except OSError:
                pass
    except OSError:
        pass
    return None


def _pick_launch_exe(install: Path) -> Path | None:
    """Pick a plausible game executable under the install folder (Windows)."""
    roots = [install]
    for sub in ("bin", "Bin", "x64", "Game", "__Installer"):
        p = install / sub
        if p.is_dir():
            roots.append(p)

    candidates: list[Path] = []
    for root in roots:
        try:
            for exe in root.glob("*.exe"):
                if _EXE_SKIP_RE.search(exe.name):
                    continue
                try:
                    if exe.stat().st_size < 200_000:
                        continue
                except OSError:
                    continue
                candidates.append(exe)
        except OSError:
            continue

    if not candidates:
        return None

    def sort_key(p: Path) -> tuple[int, int]:
        try:
            size = p.stat().st_size
        except OSError:
            size = 0
        name_l = p.name.casefold()
        priority = 0
        if "launcher" in name_l or "game" in name_l or "start" in name_l:
            priority = 2
        elif not any(x in name_l for x in ("server", "sdk", "tool", "editor")):
            priority = 1
        return (priority, size)

    candidates.sort(key=sort_key, reverse=True)
    return candidates[0]


def _pick_launch_app(install: Path) -> Path | None:
    """Pick a game .app bundle (macOS)."""
    candidates: list[Path] = []
    search_roots = [install]
    for sub in ("Contents", "Game", "Games"):
        p = install / sub
        if p.is_dir():
            search_roots.append(p)

    for root in search_roots:
        try:
            for app in root.glob("*.app"):
                if _APP_SKIP_RE.search(app.name):
                    continue
                candidates.append(app)
        except OSError:
            continue

    if not candidates:
        return None

    def sort_key(p: Path) -> tuple[int, int]:
        name_l = p.name.casefold()
        priority = 1
        if any(x in name_l for x in ("launcher", "helper", "installer", "origin")):
            priority = 0
        try:
            size = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
        except OSError:
            size = 0
        return (priority, size)

    candidates.sort(key=sort_key, reverse=True)
    return candidates[0]


def _program_files_ea_roots() -> list[Path]:
    roots: list[Path] = []
    for env in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(env)
        if not base:
            continue
        b = Path(base)
        for tail in ("EA Games", "Origin Games"):
            roots.append(b / tail)
    seen: set[str] = set()
    out: list[Path] = []
    for r in roots:
        try:
            key = str(r.resolve()).casefold()
        except OSError:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _folder_display_title(folder_name: str) -> str:
    name = folder_name.removesuffix(".app")
    return name.replace("_", " ").strip() or "EA Game"


def _iter_ea_install_dirs(root: Path) -> list[Path]:
    """Yield plausible per-game install directories under an EA root."""
    found: list[Path] = []
    try:
        children = list(root.iterdir())
    except OSError:
        return found

    for child in children:
        if not child.is_dir() and child.suffix != ".app":
            continue
        name_cf = child.name.casefold()
        if name_cf in _SKIP_FOLDER_NAMES:
            continue
        if child.suffix == ".app":
            if _APP_SKIP_RE.search(child.name):
                continue
            found.append(child)
            continue
        if child.is_dir():
            nested_app = _pick_launch_app(child)
            if nested_app is not None:
                found.append(child)
    return found


def _list_ea_games_from_folders(*, fast: bool = False) -> list[dict[str, Any]]:
    by_path: dict[str, dict[str, Any]] = {}
    roots = ea_scan_roots() if IS_DARWIN else _program_files_ea_roots()

    for root in roots:
        if not root.is_dir():
            continue
        for install in _iter_ea_install_dirs(root):
            if IS_DARWIN:
                app = _pick_launch_app(install)
                if app is None:
                    if install.suffix == ".app":
                        app = install
                    else:
                        continue
                launch = launch_app_bundle(app)
                command = launch["command"]
                args = launch["args"]
                cwd = str(install)
                display_name = install.name if install.suffix == ".app" else app.stem
            else:
                exe = _pick_launch_exe(install)
                if exe is None or not exe.is_file():
                    continue
                command = str(exe)
                args: list[str] = []
                cwd = str(install)
                display_name = install.name

            try:
                path_key = str(install.resolve()).casefold()
            except OSError:
                continue
            slug = re.sub(r"[^\w.\-]+", "_", display_name.strip())[:80] or "game"
            library_key = f"ea:{slug}"
            title = _folder_display_title(display_name)
            header = None if fast else _find_local_cover(install)
            by_path[path_key] = {
                "title": title,
                "appid": 0,
                "store": "ea",
                "library_key": library_key,
                "command": command,
                "args": args,
                "cwd": cwd,
                "header_image": str(header) if header else "",
                "ea_source": "program_files" if not IS_DARWIN else "mac_scan",
                "ea_install_dir": str(install),
            }
    return list(by_path.values())


def _merge_ea_game_lists(*lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    priority = {"ea_desktop_is": 0, "ea_desktop": 0, "mac_scan": 1, "program_files": 1, "registry": 2}

    flat: list[dict[str, Any]] = []
    for lst in lists:
        flat.extend(lst)

    flat.sort(
        key=lambda g: (
            priority.get(str(g.get("ea_source") or "registry"), 9),
            str(g.get("title", "")).casefold(),
        )
    )

    seen_install: set[str] = set()
    seen_lk: set[str] = set()
    out: list[dict[str, Any]] = []
    for game in flat:
        install_dir = str(game.get("ea_install_dir") or game.get("cwd") or "").strip()
        lk = str(game.get("library_key") or "")
        ik = ""
        if install_dir:
            try:
                ik = str(Path(install_dir).resolve()).casefold()
            except OSError:
                ik = ""
        if ik:
            if ik in seen_install:
                continue
            seen_install.add(ik)
        elif lk:
            if lk in seen_lk:
                continue
            seen_lk.add(lk)
        else:
            continue
        out.append(game)
    return sorted(out, key=lambda g: str(g.get("title", "")).casefold())


def _list_ea_games_from_registry(*, fast: bool = False) -> list[dict[str, Any]]:
    if winreg is None:
        return []

    by_key: dict[str, dict[str, Any]] = {}
    for hive, parent in _EA_REG_PARENTS:
        if not parent:
            break
        try:
            with winreg.OpenKey(hive, parent) as pkey:
                i = 0
                while True:
                    try:
                        sub_name = winreg.EnumKey(pkey, i)
                    except OSError:
                        break
                    i += 1
                    if sub_name.casefold() in _SKIP_SUBKEYS:
                        continue
                    sub_path = f"{parent}\\{sub_name}"
                    install = _read_install_dir(sub_path, hive)
                    if install is None:
                        continue
                    exe = _pick_launch_exe(install)
                    if exe is None or not exe.is_file():
                        continue

                    slug = re.sub(r"[^\w.\-]+", "_", sub_name.strip())[:80] or "game"
                    library_key = f"ea:{slug}"
                    title = sub_name.strip() or "EA Game"
                    header = None if fast else _find_local_cover(install)
                    entry: dict[str, Any] = {
                        "title": title,
                        "appid": 0,
                        "store": "ea",
                        "library_key": library_key,
                        "command": str(exe),
                        "args": [],
                        "cwd": str(install),
                        "header_image": str(header) if header else "",
                        "ea_registry_title": sub_name,
                        "ea_source": "registry",
                        "ea_install_dir": str(install),
                    }
                    by_key[library_key] = entry
        except OSError:
            continue

    return sorted(by_key.values(), key=lambda g: str(g["title"]).casefold())


def list_installed_ea_games(*, fast: bool = False) -> list[dict[str, Any]]:
    if IS_DARWIN:
        return _list_ea_games_from_folders(fast=fast)

    games, mode = try_load_ea_desktop_games()
    if mode == "ea_desktop":
        return games
    program_files = _list_ea_games_from_folders(fast=fast)
    registry = _list_ea_games_from_registry(fast=fast)
    return _merge_ea_game_lists(program_files, registry)


def _find_local_cover(install: Path) -> Path | None:
    for pat in (
        "CoverArt*.jpg",
        "CoverArt*.png",
        "**/CoverArt*.jpg",
        "**/CoverArt*.png",
        "**/logo*.png",
        "**/gameface*.png",
        "**/*.icns",
    ):
        try:
            for p in install.glob(pat):
                if p.is_file():
                    return p
        except OSError:
            continue
    return None
