"""Tests for music_updater.scanner."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from music_updater.scanner import scan


@pytest.fixture()
def tmp_dir():
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return path


class TestScan:
    def test_single_file(self, tmp_dir):
        f = _touch(tmp_dir / "song.mp3")
        assert list(scan(f)) == [f]

    def test_unsupported_single_file_yields_nothing(self, tmp_dir):
        f = _touch(tmp_dir / "audio.wav")
        assert list(scan(f)) == []

    def test_flat_directory(self, tmp_dir):
        _touch(tmp_dir / "a.mp3")
        _touch(tmp_dir / "b.flac")
        _touch(tmp_dir / "c.txt")
        results = list(scan(tmp_dir))
        names = {p.name for p in results}
        assert names == {"a.mp3", "b.flac"}

    def test_recursive(self, tmp_dir):
        _touch(tmp_dir / "top.mp3")
        _touch(tmp_dir / "sub" / "deep.m4a")
        _touch(tmp_dir / "sub" / "sub2" / "deeper.flac")
        results = list(scan(tmp_dir, recursive=True))
        names = {p.name for p in results}
        assert names == {"top.mp3", "deep.m4a", "deeper.flac"}

    def test_non_recursive(self, tmp_dir):
        _touch(tmp_dir / "top.mp3")
        _touch(tmp_dir / "sub" / "nested.mp3")
        results = list(scan(tmp_dir, recursive=False))
        names = {p.name for p in results}
        assert "top.mp3" in names
        assert "nested.mp3" not in names

    def test_nonexistent_path_raises(self, tmp_dir):
        with pytest.raises(FileNotFoundError):
            list(scan(tmp_dir / "does_not_exist"))

    def test_m4a_and_aac_included(self, tmp_dir):
        _touch(tmp_dir / "track.m4a")
        _touch(tmp_dir / "track.aac")
        results = list(scan(tmp_dir))
        names = {p.name for p in results}
        assert names == {"track.m4a", "track.aac"}
