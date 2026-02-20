"""SQLite database layer for music library index and playlists."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import mutagen

from .metadata import AudioFile
from .scanner import scan

logger = logging.getLogger(__name__)

DB_PATH = Path.home() / ".music_updater" / "library.db"


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------


def get_conn(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def init_db(db_path: Path = DB_PATH) -> None:
    """Create tables if they don't exist."""
    with get_conn(db_path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS tracks (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                path            TEXT    UNIQUE NOT NULL,
                title           TEXT,
                artist          TEXT,
                album           TEXT,
                year            TEXT,
                track_number    TEXT,
                genre           TEXT,
                has_artwork     INTEGER DEFAULT 0,
                duration_secs   REAL,
                file_size_bytes INTEGER,
                date_indexed    TEXT    NOT NULL,
                play_count      INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS playlists (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL,
                created_at  TEXT    NOT NULL,
                updated_at  TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS playlist_tracks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
                track_id    INTEGER NOT NULL REFERENCES tracks(id)    ON DELETE CASCADE,
                position    INTEGER NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_tracks_artist ON tracks(artist COLLATE NOCASE);
            CREATE INDEX IF NOT EXISTS idx_tracks_album  ON tracks(album  COLLATE NOCASE);
            CREATE INDEX IF NOT EXISTS idx_tracks_title  ON tracks(title  COLLATE NOCASE);
            CREATE INDEX IF NOT EXISTS idx_pt_playlist   ON playlist_tracks(playlist_id);
        """)
        # Schema migration: add play_count if the DB predates it
        existing = {row[1] for row in conn.execute("PRAGMA table_info(tracks)")}
        if "play_count" not in existing:
            conn.execute("ALTER TABLE tracks ADD COLUMN play_count INTEGER DEFAULT 0")


# ---------------------------------------------------------------------------
# Library indexing
# ---------------------------------------------------------------------------


def _get_duration(path: Path) -> Optional[float]:
    try:
        audio = mutagen.File(str(path))
        if audio and hasattr(audio, "info"):
            return audio.info.length
    except Exception:
        pass
    return None


def index_file(path: Path, conn: sqlite3.Connection) -> None:
    """Upsert a single audio file's metadata into the tracks table."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        af = AudioFile(path)
        meta = af.to_dict()
    except Exception as exc:
        logger.warning("Cannot read %s: %s", path, exc)
        return

    conn.execute(
        """
        INSERT INTO tracks
            (path, title, artist, album, year, track_number, genre,
             has_artwork, duration_secs, file_size_bytes, date_indexed)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            title           = excluded.title,
            artist          = excluded.artist,
            album           = excluded.album,
            year            = excluded.year,
            track_number    = excluded.track_number,
            genre           = excluded.genre,
            has_artwork     = excluded.has_artwork,
            duration_secs   = excluded.duration_secs,
            file_size_bytes = excluded.file_size_bytes,
            date_indexed    = excluded.date_indexed
        """,
        (
            str(path),
            meta["title"], meta["artist"], meta["album"], meta["year"],
            meta["track"], meta["genre"], int(meta["has_artwork"]),
            _get_duration(path), path.stat().st_size, now,
        ),
    )


def index_directory(root: str | Path, db_path: Path = DB_PATH) -> int:
    """Scan *root* recursively and upsert all audio files. Returns count indexed."""
    root = Path(root)
    count = 0
    with get_conn(db_path) as conn:
        for path in scan(root, recursive=True):
            index_file(path, conn)
            count += 1
    return count


# ---------------------------------------------------------------------------
# Track queries
# ---------------------------------------------------------------------------


def search_tracks(
    query: Optional[str] = None,
    artist: Optional[str] = None,
    album: Optional[str] = None,
    db_path: Path = DB_PATH,
) -> list[dict]:
    conditions: list[str] = []
    params: list = []

    if query:
        like = f"%{query}%"
        conditions.append(
            "(title LIKE ? OR artist LIKE ? OR album LIKE ? OR genre LIKE ?)"
        )
        params.extend([like, like, like, like])
    if artist:
        conditions.append("artist LIKE ?")
        params.append(f"%{artist}%")
    if album:
        conditions.append("album LIKE ?")
        params.append(f"%{album}%")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = f"""
        SELECT * FROM tracks {where}
        ORDER BY
            artist       COLLATE NOCASE,
            album        COLLATE NOCASE,
            CAST(track_number AS INTEGER),
            title        COLLATE NOCASE
    """
    with get_conn(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_track(track_id: int, db_path: Path = DB_PATH) -> Optional[dict]:
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM tracks WHERE id = ?", (track_id,)).fetchone()
    return dict(row) if row else None


def delete_track(track_id: int, db_path: Path = DB_PATH) -> bool:
    """Remove a track from the library index. Returns True if a row was deleted."""
    with get_conn(db_path) as conn:
        cur = conn.execute("DELETE FROM tracks WHERE id = ?", (track_id,))
    return cur.rowcount > 0


def increment_play_count(track_id: int, db_path: Path = DB_PATH) -> None:
    """Increment play_count for the given track."""
    with get_conn(db_path) as conn:
        conn.execute(
            "UPDATE tracks SET play_count = COALESCE(play_count, 0) + 1 WHERE id = ?",
            (track_id,),
        )


# ---------------------------------------------------------------------------
# Playlist CRUD
# ---------------------------------------------------------------------------


def list_playlists(db_path: Path = DB_PATH) -> list[dict]:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT id, name, created_at, updated_at FROM playlists ORDER BY name COLLATE NOCASE"
        ).fetchall()
    return [dict(r) for r in rows]


def create_playlist(name: str, db_path: Path = DB_PATH) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    with get_conn(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO playlists (name, created_at, updated_at) VALUES (?, ?, ?)",
            (name, now, now),
        )
        row = conn.execute(
            "SELECT * FROM playlists WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return dict(row)


def get_playlist(playlist_id: int, db_path: Path = DB_PATH) -> Optional[dict]:
    with get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM playlists WHERE id = ?", (playlist_id,)
        ).fetchone()
        if not row:
            return None
        playlist = dict(row)
        tracks = conn.execute(
            """
            SELECT t.* FROM tracks t
            JOIN playlist_tracks pt ON pt.track_id = t.id
            WHERE pt.playlist_id = ?
            ORDER BY pt.position
            """,
            (playlist_id,),
        ).fetchall()
        playlist["tracks"] = [dict(t) for t in tracks]
    return playlist


def update_playlist(
    playlist_id: int, name: str, db_path: Path = DB_PATH
) -> Optional[dict]:
    now = datetime.now(timezone.utc).isoformat()
    with get_conn(db_path) as conn:
        conn.execute(
            "UPDATE playlists SET name = ?, updated_at = ? WHERE id = ?",
            (name, now, playlist_id),
        )
        row = conn.execute(
            "SELECT * FROM playlists WHERE id = ?", (playlist_id,)
        ).fetchone()
    return dict(row) if row else None


def delete_playlist(playlist_id: int, db_path: Path = DB_PATH) -> bool:
    with get_conn(db_path) as conn:
        cur = conn.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))
    return cur.rowcount > 0


def add_track_to_playlist(
    playlist_id: int,
    track_id: int,
    position: Optional[int] = None,
    db_path: Path = DB_PATH,
) -> None:
    with get_conn(db_path) as conn:
        if position is None:
            row = conn.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM playlist_tracks WHERE playlist_id = ?",
                (playlist_id,),
            ).fetchone()
            position = row[0]
        conn.execute(
            "INSERT INTO playlist_tracks (playlist_id, track_id, position) VALUES (?, ?, ?)",
            (playlist_id, track_id, position),
        )
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE playlists SET updated_at = ? WHERE id = ?", (now, playlist_id)
        )


def remove_track_from_playlist(
    playlist_id: int, track_id: int, db_path: Path = DB_PATH
) -> bool:
    with get_conn(db_path) as conn:
        cur = conn.execute(
            "DELETE FROM playlist_tracks WHERE playlist_id = ? AND track_id = ?",
            (playlist_id, track_id),
        )
    return cur.rowcount > 0


def reorder_playlist(
    playlist_id: int,
    track_positions: list[dict],
    db_path: Path = DB_PATH,
) -> None:
    """Update positions. *track_positions* is [{track_id, position}, ...]."""
    with get_conn(db_path) as conn:
        for item in track_positions:
            conn.execute(
                "UPDATE playlist_tracks SET position = ? WHERE playlist_id = ? AND track_id = ?",
                (item["position"], playlist_id, item["track_id"]),
            )
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE playlists SET updated_at = ? WHERE id = ?", (now, playlist_id)
        )
