from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from host import IS_DARWIN


class LaunchError(RuntimeError):
    pass


class Launcher:
    def __init__(self) -> None:
        self._process: subprocess.Popen[Any] | None = None

    def launch(self, game_config: dict[str, Any]) -> subprocess.Popen[Any]:
        command = game_config.get("command")
        if not command:
            raise LaunchError("Missing launch command.")

        args = list(game_config.get("args", []))
        cwd = game_config.get("cwd")
        working_directory = Path(cwd) if cwd else None

        if working_directory and not working_directory.exists():
            raise LaunchError(f"Working directory not found: {working_directory}")

        cmd_path = Path(str(command))
        if IS_DARWIN and cmd_path.suffix == ".app" and cmd_path.is_dir():
            full_command = ["/usr/bin/open", str(cmd_path), *args]
            working_directory = None
        else:
            full_command = [str(command), *args]

        try:
            self._process = subprocess.Popen(full_command, cwd=working_directory)
        except OSError as exc:
            raise LaunchError(f"Failed to launch: {exc}") from exc
        return self._process

    def poll(self) -> int | None:
        if not self._process:
            return None
        return self._process.poll()

    def is_running(self) -> bool:
        return self.poll() is None if self._process else False
