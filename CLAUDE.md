# CLAUDE.md — Music Metadata Updater

This document captures everything an AI assistant needs to understand, develop,
and extend this codebase efficiently.

---

## Project overview

**music-metadata-updater** is a Python application that:

1. Reads and writes metadata tags on MP3, FLAC, and M4A/AAC audio files.
2. Fetches missing album artwork from the iTunes Search API (primary) and
   the MusicBrainz / Cover Art Archive pipeline (fallback).
3. Provides a `rich`-formatted terminal CLI and a **browser-based web UI** with
   a music player, search, and playlist management.

---

## Repository layout

```
music-metadata-updater/
├── music_updater/              # Main package
│   ├── __init__.py             # Package version
│   ├── cli.py                  # Click CLI (main entry point, includes `serve`)
│   ├── db.py                   # SQLite library index + playlist CRUD
│   ├── metadata.py             # AudioFile class – unified read/write for all formats
│   ├── artwork.py              # fetch_artwork() – iTunes + MusicBrainz
│   ├── scanner.py              # scan() – yield audio paths from a directory
│   ├── server.py               # FastAPI app – REST API + static file serving
│   └── static/                 # Web UI assets (served by FastAPI)
│       ├── index.html          # Single-page app shell
│       ├── style.css           # Dark-theme CSS (CSS Grid layout)
│       └── app.js              # Vanilla JS: player, search, playlists
├── tests/
│   ├── __init__.py
│   ├── test_metadata.py        # AudioFile unit tests
│   ├── test_artwork.py         # Artwork tests (mocked HTTP via `responses`)
│   └── test_scanner.py         # Scanner unit tests
├── pyproject.toml              # Build config + pytest settings
├── requirements.txt            # Runtime dependencies
├── requirements-dev.txt        # Dev/test dependencies
└── CLAUDE.md                   # This file
```

---

## Key modules

### `music_updater/metadata.py`

Central module. `AudioFile` wraps `mutagen` and provides a single property
interface regardless of format:

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

1. **iTunes Search API** — free, no auth. Artwork URLs contain `100x100bb`;
   replaced with `{size}x{size}bb` for higher resolution.
2. **MusicBrainz + Cover Art Archive** — searches for a release MBID, then
   fetches `coverartarchive.org/release/{mbid}/front`.

The MusicBrainz `User-Agent` header is **required** (causes 403 if omitted).

### `music_updater/scanner.py`

`scan(root, recursive=True)` yields `Path` objects filtered to
`SUPPORTED_EXTENSIONS`.

### `music_updater/db.py`

SQLite database stored at `~/.music_updater/library.db` (WAL mode, FK on).

**Tables:**

| Table             | Purpose                                         |
|-------------------|-------------------------------------------------|
| `tracks`          | Indexed audio file metadata + duration          |
| `playlists`       | Named playlists with timestamps                 |
| `playlist_tracks` | Many-to-many join with ordered `position`       |

Key functions: `init_db`, `index_directory`, `search_tracks`, `get_track`,
`list_playlists`, `create_playlist`, `get_playlist`, `update_playlist`,
`delete_playlist`, `add_track_to_playlist`, `remove_track_from_playlist`,
`reorder_playlist`.

### `music_updater/server.py`

FastAPI application. Mounts `/static` from `music_updater/static/`. All API
routes are prefixed `/api/`.

**REST endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Serves `index.html` |
| `GET` | `/api/library` | List/search tracks (`?q=`, `?artist=`, `?album=`) |
| `POST` | `/api/library/scan` | Index a directory `{"path": "..."}` |
| `GET` | `/api/tracks/{id}/stream` | Stream audio (Range-request aware via `FileResponse`) |
| `GET` | `/api/tracks/{id}/artwork` | Serve embedded artwork as image |
| `GET/POST` | `/api/playlists` | List / create playlists |
| `GET/PUT/DELETE` | `/api/playlists/{id}` | Get / rename / delete |
| `POST` | `/api/playlists/{id}/tracks` | Add track `{track_id, position?}` |
| `DELETE` | `/api/playlists/{id}/tracks/{track_id}` | Remove track |
| `PUT` | `/api/playlists/{id}/tracks` | Reorder `{tracks: [{track_id, position}]}` |

Audio streaming uses FastAPI's `FileResponse`, which handles HTTP `Range`
headers automatically so the browser can seek without re-downloading.

### `music_updater/static/`

Vanilla JS SPA — no framework. Key concepts in `app.js`:

- **`state`** object holds `view`, `tracks`, `playlists`, `queue`, `queueIndex`,
  `currentTrack`, `isPlaying`.
- **`loadLibrary(q?)`** / **`loadPlaylist(id)`** — fetch from API, call
  `renderTracks()`.
- **`playTrack(track, queue, index)`** — sets `audio.src` and calls `audio.play()`.
- Double-click a row to play; the whole visible track list becomes the queue.
- **`showAddMenu(track, anchor)`** — floating context menu to pick a playlist.
- Keyboard shortcuts: `Space` = play/pause, `Alt+→` = next, `Alt+←` = prev.
- Search is debounced 300 ms. Library search hits the API; playlist search
  filters client-side.

### `music_updater/cli.py`

Click commands exposed via the `music-update` entry point:

| Command | Description |
|---------|-------------|
| `info PATH` | Pretty-print metadata table |
| `update PATH [OPTIONS]` | Set tag fields |
| `fetch-art PATH` | Fetch & embed artwork |
| `scan DIR` | List supported files |
| `auto PATH` | `info` + `fetch-art` combined |
| `serve` | Start the web UI server |

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

## Running the web UI

```bash
music-update serve                    # http://127.0.0.1:8000
music-update serve --port 3000        # custom port
music-update serve --host 0.0.0.0     # expose on network
music-update serve --reload           # dev auto-reload (requires pip install watchfiles)
```

Open the URL in a browser, paste your music directory path into the **Scan**
input in the bottom-left of the sidebar, and click **Scan**. Tracks appear
in the library. Double-click any track to play.

---

## Running the CLI

```bash
music-update info /path/to/song.mp3
music-update update /path/to/song.mp3 --artist "The Beatles" --album "Abbey Road"
music-update fetch-art /music/ --recursive
music-update auto /music/
```

---

## Running tests

```bash
pytest                          # all tests with coverage
pytest tests/test_metadata.py   # single module
pytest -k "test_set_and_save"   # filter by name
pytest --no-cov                 # skip coverage
```

HTTP calls in `test_artwork.py` are fully mocked via `responses`.
No network access or real audio hardware is required.

---

## Adding a new audio format

1. Add the extension to `SUPPORTED_EXTENSIONS` in `metadata.py`.
2. Add `elif self._fmt == ".xxx":` branches to every property getter, setter,
   `set_artwork`, and `save` in `AudioFile`.
3. Add a fixture + test class in `tests/test_metadata.py`.
4. No changes needed elsewhere.

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `mutagen` | Audio tag read/write for all formats |
| `requests` | HTTP calls to iTunes and MusicBrainz |
| `Pillow` | Image processing (available for future use) |
| `rich` | Terminal formatting |
| `click` | CLI argument parsing |
| `fastapi` | REST API + static file serving |
| `uvicorn` | ASGI server for FastAPI |

Dev only: `pytest`, `pytest-cov`, `responses`.

---

## Conventions

- Python 3.10+ required. Use `from __future__ import annotations` in all modules.
- Prefer `Path` over raw strings for file paths.
- All HTTP calls go through a shared `requests.Session` passed as a parameter
  so tests can inject mocks and production code reuses connections.
- Log with `logging`, never `print()`, inside library code. Only `cli.py` uses
  `rich` console output.
- `AudioFile.save()` must be called explicitly after mutations.
- The DB path defaults to `~/.music_updater/library.db`; pass `db_path` to any
  db function to override (used in tests).
- Frontend JS follows a simple state + render pattern. Avoid framework
  dependencies — keep it vanilla.

---

## External API notes

| API | Rate limits | Auth |
|-----|-------------|------|
| iTunes Search | ~20 req/min (unofficial) | None |
| MusicBrainz | 1 req/sec (enforced) | None (User-Agent required) |
| Cover Art Archive | Reasonable use | None |

For batch processing large libraries, add `time.sleep(1)` between MusicBrainz
calls to stay within their rate limit.
