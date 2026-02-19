"""Tests for music_updater.metadata."""

from __future__ import annotations

import shutil
import struct
import tempfile
from pathlib import Path

import pytest

from music_updater.metadata import AudioFile, SUPPORTED_EXTENSIONS


# ---------------------------------------------------------------------------
# Helpers – create minimal valid audio files for testing
# ---------------------------------------------------------------------------

def _make_mp3(path: Path) -> Path:
    """Write a minimal valid MP3 file (silent 1-frame MPEG1 layer3)."""
    # Sync word + MPEG1, Layer 3, 128kbps, 44100Hz, stereo
    frame = bytes([0xFF, 0xFB, 0x90, 0x00]) + bytes(413)
    path.write_bytes(frame)
    return path


def _make_flac(path: Path) -> Path:
    """Write a minimal valid FLAC file."""
    # FLAC stream marker + STREAMINFO block (last=1, type=0, length=34)
    # Minimal STREAMINFO: 16-byte min/max block, sample rate, channels, bits, total samples, MD5
    marker = b"fLaC"
    block_header = struct.pack(">I", (1 << 31) | (0 << 24) | 34)  # last=1, type=STREAMINFO, len=34
    streaminfo = (
        struct.pack(">H", 4096)    # min block size
        + struct.pack(">H", 4096)  # max block size
        + b"\x00\x00\x00"         # min frame size (24-bit)
        + b"\x00\x00\x00"         # max frame size (24-bit)
        # 20 bits sample_rate + 3 bits channels-1 + 5 bits bits_per_sample-1 + 36 bits total_samples
        + struct.pack(">Q", (44100 << 44) | (0 << 41) | (15 << 36) | 0)
        + b"\x00" * 16            # MD5
    )
    path.write_bytes(marker + block_header + streaminfo)
    return path


def _make_m4a(path: Path) -> Path:
    """Write a minimal M4A/MP4 container (ftyp box only)."""
    ftyp = b"M4A " + b"\x00" * 4 + b"M4A " + b"mp42" + b"isom"
    size = len(ftyp) + 8
    box = struct.pack(">I", size) + b"ftyp" + ftyp
    path.write_bytes(box)
    return path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_dir():
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture()
def mp3_file(tmp_dir):
    return _make_mp3(tmp_dir / "track.mp3")


@pytest.fixture()
def flac_file(tmp_dir):
    return _make_flac(tmp_dir / "track.flac")


# ---------------------------------------------------------------------------
# SUPPORTED_EXTENSIONS
# ---------------------------------------------------------------------------


def test_supported_extensions_includes_common_formats():
    assert ".mp3" in SUPPORTED_EXTENSIONS
    assert ".flac" in SUPPORTED_EXTENSIONS
    assert ".m4a" in SUPPORTED_EXTENSIONS


# ---------------------------------------------------------------------------
# AudioFile – unsupported format
# ---------------------------------------------------------------------------


def test_unsupported_format_raises(tmp_dir):
    wav = tmp_dir / "audio.wav"
    wav.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
    with pytest.raises(ValueError, match="Unsupported format"):
        AudioFile(wav)


# ---------------------------------------------------------------------------
# AudioFile – MP3
# ---------------------------------------------------------------------------


class TestMP3:
    def test_initial_tags_are_none(self, mp3_file):
        af = AudioFile(mp3_file)
        assert af.title is None
        assert af.artist is None
        assert af.album is None
        assert af.year is None
        assert af.track is None
        assert af.genre is None

    def test_set_and_save_title(self, mp3_file):
        af = AudioFile(mp3_file)
        af.title = "My Song"
        af.save()

        reloaded = AudioFile(mp3_file)
        assert reloaded.title == "My Song"

    def test_set_multiple_fields(self, mp3_file):
        af = AudioFile(mp3_file)
        af.title = "Track 1"
        af.artist = "Artist A"
        af.album = "Album X"
        af.year = "2024"
        af.track = "1/12"
        af.genre = "Rock"
        af.save()

        r = AudioFile(mp3_file)
        assert r.title == "Track 1"
        assert r.artist == "Artist A"
        assert r.album == "Album X"
        assert r.year == "2024"
        assert r.track == "1/12"
        assert r.genre == "Rock"

    def test_has_artwork_false_initially(self, mp3_file):
        af = AudioFile(mp3_file)
        assert af.has_artwork is False

    def test_set_artwork(self, mp3_file):
        af = AudioFile(mp3_file)
        # 1×1 white JPEG (minimal valid JPEG)
        jpeg = (
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
            b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
            b"\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a"
            b"\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\x1e!"
            b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00"
            b"\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00"
            b"\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b"
            b"\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04"
            b"\x04\x00\x00\x01}\x01\x02\x03\x00\x04\x11\x05\x12!1A\x06\x13Qa"
            b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xf5\x00\xff\xd9"
        )
        af.set_artwork(jpeg, "image/jpeg")
        af.save()

        r = AudioFile(mp3_file)
        assert r.has_artwork is True

    def test_to_dict_keys(self, mp3_file):
        af = AudioFile(mp3_file)
        d = af.to_dict()
        assert set(d.keys()) == {"title", "artist", "album", "year", "track", "genre", "has_artwork"}


# ---------------------------------------------------------------------------
# AudioFile – FLAC
# ---------------------------------------------------------------------------


class TestFLAC:
    def test_initial_tags_are_none(self, flac_file):
        af = AudioFile(flac_file)
        assert af.title is None
        assert af.artist is None

    def test_set_and_save_fields(self, flac_file):
        af = AudioFile(flac_file)
        af.title = "FLAC Track"
        af.artist = "FLAC Artist"
        af.album = "FLAC Album"
        af.year = "2023"
        af.track = "2"
        af.genre = "Jazz"
        af.save()

        r = AudioFile(flac_file)
        assert r.title == "FLAC Track"
        assert r.artist == "FLAC Artist"
        assert r.album == "FLAC Album"
        assert r.year == "2023"
        assert r.track == "2"
        assert r.genre == "Jazz"

    def test_has_artwork_false_initially(self, flac_file):
        af = AudioFile(flac_file)
        assert af.has_artwork is False
