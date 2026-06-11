"""Build launch command/args for store URIs and macOS .app bundles."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from host import IS_DARWIN


def open_command() -> str:
    if IS_DARWIN:
        return "/usr/bin/open"
    if shutil.which("cmd.exe"):
        return "cmd.exe"
    return "cmd.exe"


def launch_via_open(target: str, *, app_name: str | None = None) -> dict[str, Any]:
    """Return a game_config fragment using the OS handler (``open`` on macOS)."""
    if IS_DARWIN:
        args: list[str] = []
        if app_name:
            args.extend(["-a", app_name, target])
        else:
            args.append(target)
        return {"command": "/usr/bin/open", "args": args, "cwd": ""}
    return {
        "command": "cmd.exe",
        "args": ["/c", "start", "", target],
        "cwd": "",
    }


def launch_app_bundle(app_path: Path) -> dict[str, Any]:
    if IS_DARWIN:
        return {"command": "/usr/bin/open", "args": [str(app_path)], "cwd": ""}
    return {"command": str(app_path), "args": [], "cwd": str(app_path.parent)}


def settings_uri(windows_ms_settings: str, macos_settings_path: str) -> dict[str, Any]:
    if IS_DARWIN:
        return launch_via_open(macos_settings_path)
    return {
        "command": "cmd.exe",
        "args": ["/c", "start", "", windows_ms_settings],
        "cwd": "",
    }
