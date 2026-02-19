# CLAUDE.md — Music Metadata Updater

This document captures everything an AI assistant needs to understand, develop,
and extend this codebase efficiently.

---

## Project overview

**music-metadata-updater** is a Python CLI tool that:

1. Reads and writes metadata tags on MP3, FLAC, and M4A/AAC audio files.
2. Fetches missing album artwork from the iTunes Search API (primary) and
   the MusicBrainz / Cover Art Archive pipeline (fallback).
3. Provides a `rich`-formatted terminal UI and a `click`-based CLI.

---

## Repository layout

```
music-metadata-updater/
├── music_updater/          # Main package
│   ├── __init__.py         # Package version
│   ├── cli.py              # Click commands (main entry point)
│   ├── metadata.py         # AudioFile class – unified read/write for all formats
│   ├── artwork.py          # fetch_artwork() – iTunes + MusicBrainz
│   └── scanner.py          # scan() – yield audio paths from a directory
├── tests/
│   ├── __init__.py
│   ├── test_metadata.py    # AudioFile unit tests (uses real minimal audio fixtures)
│   ├── test_artwork.py     # artwork tests (uses `responses` to mock HTTP)
│   └── test_scanner.py     # scanner unit tests
├── pyproject.toml          # Build config + pytest settings
├── requirements.txt        # Runtime dependencies
├── requirements-dev.txt    # Dev/test dependencies (includes -r requirements.txt)
└── CLAUDE.md               # This file
```

---

## Key modules

### `music_updater/metadata.py`

Central module. `AudioFile` wraps `mutagen` and provides a single interface
regardless of format:

| Property | MP3 (ID3) | FLAC (Vorbis) | M4A/AAC (iTunes atoms) |
|----------|-----------|---------------|------------------------|
| `title`  | `TIT2`    | `title`       | `©nam`                 |
| `artist` | `TPE1`    | `artist`      | `©ART`                 |
| `album`  | `TALB`    | `album`       | `©alb`                 |
| `year`   | `TDRC`    | `date`        | `©day`                 |
| `track`  | `TRCK`    | `tracknumber` | `trkn`                 |
| `genre`  | `TCON`    | `genre`       | `©gen`                 |
| artwork  | `APIC`    | `Picture`     | `covr`                 |

All properties are read/write. Call `af.save()` to persist changes.

`SUPPORTED_EXTENSIONS` is a `frozenset` used by both `AudioFile` and `scanner`.

### `music_updater/artwork.py`

`fetch_artwork(artist, album, size, session)` returns `(bytes, mime_type)` or
`None`. Two sources are tried in order:

1. **iTunes Search API** (`itunes.apple.com/search`) — free, no auth. Artwork
   URLs contain `100x100bb`; the code replaces this with `{size}x{size}bb` to
   get the requested resolution (max ~1000 px on iTunes).
2. **MusicBrainz + Cover Art Archive** — searches for a release MBID, then
   fetches `coverartarchive.org/release/{mbid}/front`.

The MusicBrainz User-Agent header is **required**; omitting it causes 403s.

### `music_updater/scanner.py`

`scan(root, recursive=True)` yields `Path` objects. It delegates extension
filtering to `SUPPORTED_EXTENSIONS` from `metadata.py`.

### `music_updater/cli.py`

`click` commands exposed via the `music-update` entry point:

| Command      | Description                                           |
|--------------|-------------------------------------------------------|
| `info PATH`  | Pretty-print metadata table for file(s)               |
| `update PATH [OPTIONS]` | Set one or more tag fields                |
| `fetch-art PATH` | Fetch & embed artwork (skips files that already have it unless `--overwrite`) |
| `scan DIR`   | List supported files in a directory                   |
| `auto PATH`  | Combine `info` + `fetch-art` for all files            |

---

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
# or
pip install -r requirements-dev.txt && pip install -e .
```

---

## Running the CLI

```bash
# Show metadata
music-update info /path/to/song.mp3

# Set fields
music-update update /path/to/song.mp3 --artist "The Beatles" --album "Abbey Road"

# Fetch artwork for a single file
music-update fetch-art /path/to/song.mp3

# Fetch artwork for an entire directory (recursive, skip existing)
music-update fetch-art /music/ --recursive

# Force-replace existing artwork at 1000px
music-update fetch-art /music/ -r --overwrite --size 1000

# Auto-update (info + artwork) for all files in a directory
music-update auto /music/

# List all supported files
music-update scan /music/
```

---

## Running tests

```bash
pytest                          # all tests with coverage
pytest tests/test_metadata.py   # single module
pytest -k "test_set_and_save"   # filter by test name
pytest --no-cov                 # skip coverage report
```

Tests use real minimal audio fixtures (not zero-byte files) for MP3 and FLAC.
HTTP calls in `test_artwork.py` are mocked via the `responses` library so no
network access is needed.

---

## Adding a new audio format

1. Add the extension to `SUPPORTED_EXTENSIONS` in `metadata.py`.
2. Add a new branch (`elif self._fmt == ".xxx": ...`) to every property getter,
   setter, `set_artwork`, and `save` in `AudioFile`.
3. Add a fixture + test class in `tests/test_metadata.py`.
4. No changes needed in `scanner.py`, `artwork.py`, or `cli.py`.

---

## Dependencies

| Package   | Purpose                                        |
|-----------|------------------------------------------------|
| `mutagen` | Low-level audio tag read/write for all formats |
| `requests`| HTTP calls to iTunes and MusicBrainz APIs      |
| `Pillow`  | Image validation / conversion (optional use)   |
| `rich`    | Terminal formatting (tables, colors)           |
| `click`   | CLI argument parsing                           |

Dev only: `pytest`, `pytest-cov`, `responses`.

---

## Conventions

- Python 3.10+ required. Use `from __future__ import annotations` for PEP 604
  union types (`X | Y`) in all modules.
- Prefer `Path` over raw strings for file paths throughout.
- All HTTP calls go through a shared `requests.Session` passed as a parameter
  so tests can inject mocks and production code reuses connections.
- Log with the standard `logging` module; never `print()` inside library code
  (`metadata.py`, `artwork.py`, `scanner.py`). Only `cli.py` uses `rich` console.
- `AudioFile.save()` must always be called explicitly after mutations — the
  class never auto-saves.
- When adding iTunes URL manipulation, the pattern to modify is the `100x100bb`
  suffix replacement in `artwork._itunes()`.

---

## External API notes

| API | Rate limits | Auth |
|-----|-------------|------|
| iTunes Search | ~20 req/min (unofficial) | None |
| MusicBrainz | 1 req/sec (enforced) | None (but User-Agent required) |
| Cover Art Archive | Reasonable use | None |

For batch processing large libraries, add a `time.sleep(1)` between MusicBrainz
calls to stay within their rate limit. The iTunes API is more lenient.
