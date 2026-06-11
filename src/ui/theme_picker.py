from __future__ import annotations

from pathlib import Path

from host.file_picker import pick_open_file


def pick_theme_zip(*, initial_dir: Path | None = None) -> Path | None:
    return pick_open_file(
        title="Choose Theme Package",
        initial_dir=initial_dir,
        filetypes=[("Theme packages", "*.zip"), ("All files", "*.*")],
        allowed_suffixes={".zip"},
    )
