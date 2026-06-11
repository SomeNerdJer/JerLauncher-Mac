"""Cross-platform file picker helpers.

On macOS, tkinter must not run in the same process as pygame — it crashes the app.
Launch the dialog in a short-lived child Python process instead.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from host import IS_DARWIN

_PICKER_SCRIPT = r"""
import json
import sys
import tkinter as tk
from tkinter import filedialog

payload = json.loads(sys.stdin.read())
root = tk.Tk()
root.withdraw()
root.attributes("-topmost", True)
root.update()
try:
    kwargs: dict = {"title": payload["title"]}
    initial_dir = payload.get("initial_dir") or ""
    if initial_dir:
        kwargs["initialdir"] = initial_dir
    filetypes = payload.get("filetypes")
    if filetypes:
        kwargs["filetypes"] = filetypes
    selected = filedialog.askopenfilename(**kwargs)
finally:
    root.destroy()
print(selected or "")
"""


def pick_open_file(
    *,
    title: str,
    initial_dir: Path | None = None,
    filetypes: list[tuple[str, str]] | None = None,
    allowed_suffixes: set[str] | None = None,
) -> Path | None:
    if IS_DARWIN:
        chosen = _pick_open_file_subprocess(
            title=title,
            initial_dir=initial_dir,
            filetypes=filetypes,
        )
    else:
        chosen = _pick_open_file_tkinter(
            title=title,
            initial_dir=initial_dir,
            filetypes=filetypes,
        )

    if chosen is None:
        return None
    if allowed_suffixes is not None and chosen.suffix.casefold() not in allowed_suffixes:
        return None
    return chosen


def _pick_open_file_subprocess(
    *,
    title: str,
    initial_dir: Path | None,
    filetypes: list[tuple[str, str]] | None,
) -> Path | None:
    payload = {
        "title": title,
        "initial_dir": str(initial_dir.resolve()) if initial_dir and initial_dir.is_dir() else "",
        "filetypes": filetypes or [("All files", "*.*")],
    }
    try:
        result = subprocess.run(
            [sys.executable, "-c", _PICKER_SCRIPT],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None

    path_text = result.stdout.strip()
    if not path_text:
        return None
    return Path(path_text)


def _pick_open_file_tkinter(
    *,
    title: str,
    initial_dir: Path | None,
    filetypes: list[tuple[str, str]] | None,
) -> Path | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        return None

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askopenfilename(
            title=title,
            filetypes=filetypes or [("All files", "*.*")],
            initialdir=str(initial_dir) if initial_dir and initial_dir.is_dir() else None,
        )
    finally:
        root.destroy()
    if not selected:
        return None
    return Path(selected)
