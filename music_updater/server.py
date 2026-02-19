"""FastAPI web server — serves the music library UI and REST API."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .db import (
    DB_PATH,
    add_track_to_playlist,
    create_playlist,
    delete_playlist,
    get_playlist,
    get_track,
    index_directory,
    init_db,
    list_playlists,
    remove_track_from_playlist,
    reorder_playlist,
    search_tracks,
    update_playlist,
)
from .metadata import AudioFile

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Music Library", docs_url=None, redoc_url=None)


@app.on_event("startup")
async def _startup() -> None:
    init_db()


# ---------------------------------------------------------------------------
# Static files / SPA root
# ---------------------------------------------------------------------------

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def root() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


# ---------------------------------------------------------------------------
# Library
# ---------------------------------------------------------------------------


@app.get("/api/library")
async def get_library(
    q: Optional[str] = Query(None, description="Full-text search across title/artist/album/genre"),
    artist: Optional[str] = Query(None),
    album: Optional[str] = Query(None),
) -> list[dict]:
    return search_tracks(query=q, artist=artist, album=album)


class ScanRequest(BaseModel):
    path: str


@app.post("/api/library/scan")
async def scan_library(req: ScanRequest) -> dict:
    path = Path(req.path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {req.path}")
    count = index_directory(path)
    return {"indexed": count, "path": str(path)}


# ---------------------------------------------------------------------------
# Tracks — streaming and artwork
# ---------------------------------------------------------------------------


@app.get("/api/tracks/{track_id}/stream")
async def stream_track(track_id: int) -> FileResponse:
    """Stream the audio file; Starlette FileResponse handles HTTP Range requests."""
    track = get_track(track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    path = Path(track["path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing from disk")
    mime, _ = mimetypes.guess_type(str(path))
    return FileResponse(str(path), media_type=mime or "audio/mpeg")


@app.get("/api/tracks/{track_id}/artwork")
async def track_artwork(track_id: int) -> Response:
    track = get_track(track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    if not track["has_artwork"]:
        raise HTTPException(status_code=404, detail="No artwork embedded")

    path = Path(track["path"])
    fmt = path.suffix.lower()
    try:
        af = AudioFile(path)
        if fmt == ".mp3":
            for frame in af._tag.values():
                if hasattr(frame, "data") and hasattr(frame, "mime"):
                    return Response(content=frame.data, media_type=frame.mime)
        elif fmt == ".flac":
            pics = af._tag.pictures
            if pics:
                return Response(content=pics[0].data, media_type=pics[0].mime)
        elif fmt in (".m4a", ".aac"):
            from mutagen.mp4 import MP4Cover

            covers = af._tag.get("covr")
            if covers:
                cover = covers[0]
                mime = (
                    "image/jpeg"
                    if cover.imageformat == MP4Cover.FORMAT_JPEG
                    else "image/png"
                )
                return Response(content=bytes(cover), media_type=mime)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    raise HTTPException(status_code=404, detail="Artwork not extractable")


# ---------------------------------------------------------------------------
# Playlists
# ---------------------------------------------------------------------------


class PlaylistCreate(BaseModel):
    name: str


class PlaylistUpdate(BaseModel):
    name: str


class AddTrackRequest(BaseModel):
    track_id: int
    position: Optional[int] = None


class ReorderRequest(BaseModel):
    tracks: List[dict]  # [{track_id: int, position: int}, ...]


@app.get("/api/playlists")
async def get_playlists() -> list[dict]:
    return list_playlists()


@app.post("/api/playlists", status_code=201)
async def new_playlist(req: PlaylistCreate) -> dict:
    return create_playlist(req.name)


@app.get("/api/playlists/{playlist_id}")
async def get_playlist_detail(playlist_id: int) -> dict:
    pl = get_playlist(playlist_id)
    if not pl:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return pl


@app.put("/api/playlists/{playlist_id}")
async def rename_playlist(playlist_id: int, req: PlaylistUpdate) -> dict:
    pl = update_playlist(playlist_id, req.name)
    if not pl:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return pl


@app.delete("/api/playlists/{playlist_id}", status_code=204)
async def del_playlist(playlist_id: int) -> None:
    if not delete_playlist(playlist_id):
        raise HTTPException(status_code=404, detail="Playlist not found")


@app.post("/api/playlists/{playlist_id}/tracks", status_code=201)
async def add_to_playlist(playlist_id: int, req: AddTrackRequest) -> dict:
    if not get_playlist(playlist_id):
        raise HTTPException(status_code=404, detail="Playlist not found")
    if not get_track(req.track_id):
        raise HTTPException(status_code=404, detail="Track not found")
    add_track_to_playlist(playlist_id, req.track_id, req.position)
    return get_playlist(playlist_id)  # type: ignore[return-value]


@app.delete("/api/playlists/{playlist_id}/tracks/{track_id}", status_code=204)
async def remove_from_playlist(playlist_id: int, track_id: int) -> None:
    remove_track_from_playlist(playlist_id, track_id)


@app.put("/api/playlists/{playlist_id}/tracks")
async def reorder_pl(playlist_id: int, req: ReorderRequest) -> dict:
    if not get_playlist(playlist_id):
        raise HTTPException(status_code=404, detail="Playlist not found")
    reorder_playlist(playlist_id, req.tracks)
    return get_playlist(playlist_id)  # type: ignore[return-value]
