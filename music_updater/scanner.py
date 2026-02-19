"""Scan directories for supported audio files."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from .metadata import SUPPORTED_EXTENSIONS


def scan(root: str | Path, recursive: bool = True) -> Iterator[Path]:
    """Yield paths to every supported audio file under *root*.

    Args:
        root:      Directory (or single file) to scan.
        recursive: When *True* (default), descend into sub-directories.
    """
    root = Path(root)

    if root.is_file():
        if root.suffix.lower() in SUPPORTED_EXTENSIONS:
            yield root
        return

    if not root.is_dir():
        raise FileNotFoundError(f"Path does not exist: {root}")

    pattern = "**/*" if recursive else "*"
    for path in sorted(root.glob(pattern)):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            yield path
