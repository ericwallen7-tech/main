"""FastAPI web server — serves the music library UI and REST API."""

from __future__ import annotations

import mimetypes
import platform
import re
import shutil
from pathlib import Path
from typing import List, Optional

import requests as _requests
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .artwork import fetch_artwork
from .db import (
    DB_PATH,
    add_track_to_playlist,
    create_playlist,
    delete_playlist,
    get_conn,
    get_playlist,
    get_track,
    index_directory,
    index_file,
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


_UPLOAD_DIR = Path.home() / ".music_updater" / "uploads"
_UPLOAD_EXTS = {".mp3", ".flac", ".m4a", ".aac", ".wav"}


@app.post("/api/library/upload")
async def upload_tracks(files: list[UploadFile] = File(...)) -> dict:
    """Accept dragged/uploaded audio files, save them, and index them."""
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    errors: list[dict] = []

    for uf in files:
        suffix = Path(uf.filename or "").suffix.lower()
        if suffix not in _UPLOAD_EXTS:
            errors.append({"file": uf.filename, "reason": "unsupported format"})
            continue
        dest = _UPLOAD_DIR / (uf.filename or f"upload{suffix}")
        try:
            dest.write_bytes(await uf.read())
            saved.append(dest)
        except OSError as exc:
            errors.append({"file": uf.filename, "reason": str(exc)})

    if saved:
        index_directory(_UPLOAD_DIR)

    return {"saved": len(saved), "errors": errors}


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
        if fmt in (".mp3", ".wav"):
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


@app.post("/api/tracks/{track_id}/fetch-art")
async def fetch_track_art(track_id: int) -> dict:
    """Fetch artwork from iTunes/MusicBrainz and embed it into the file."""
    track = get_track(track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    path = Path(track["path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing from disk")

    af = AudioFile(path)
    if not af.artist or not af.album:
        raise HTTPException(
            status_code=422,
            detail="Track is missing artist or album tags needed for artwork search",
        )

    with _requests.Session() as session:
        result = fetch_artwork(af.artist, af.album, session=session)

    if result is None:
        raise HTTPException(status_code=404, detail="No artwork found online")

    image_data, mime_type = result
    af.set_artwork(image_data, mime_type)
    af.save()
    with get_conn() as conn:
        index_file(path, conn)

    return {"ok": True, "bytes": len(image_data), "mime_type": mime_type}


@app.post("/api/library/fetch-art")
async def fetch_library_art() -> dict:
    """Fetch and embed artwork for every track currently missing it."""
    tracks = search_tracks()
    missing = [t for t in tracks if not t["has_artwork"]]

    fetched = 0
    skipped = 0
    errors: list[dict] = []

    with _requests.Session() as session:
        for track in missing:
            path = Path(track["path"])
            if not path.exists():
                errors.append({"id": track["id"], "reason": "file missing"})
                continue

            af = AudioFile(path)
            if not af.artist or not af.album:
                skipped += 1
                continue

            result = fetch_artwork(af.artist, af.album, session=session)
            if result is None:
                skipped += 1
                continue

            image_data, mime_type = result
            af.set_artwork(image_data, mime_type)
            af.save()
            with get_conn() as conn:
                index_file(path, conn)
            fetched += 1

    return {"fetched": fetched, "skipped": skipped, "errors": errors}


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


# ---------------------------------------------------------------------------
# Devices — detect mounted drives and copy tracks to them
# ---------------------------------------------------------------------------

_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe_name(name: str) -> str:
    """Sanitize a string for use as a filesystem path component."""
    return _UNSAFE_CHARS.sub("_", name).strip(". ") or "Unknown"


def _list_mounts() -> list[dict]:
    """Return plausible removable-drive mount points for the current OS."""
    system = platform.system()
    results: list[dict] = []

    if system == "Linux":
        for base in (Path("/media"), Path("/mnt"), Path("/run/media")):
            if not base.exists():
                continue
            try:
                base_dev = base.stat().st_dev
            except OSError:
                continue
            for child in base.iterdir():
                # Walk one extra level so /media/<username>/<device> works too
                candidates = [child] + (list(child.iterdir()) if child.is_dir() else [])
                for p in candidates:
                    try:
                        if p.is_dir() and p.stat().st_dev != base_dev:
                            results.append({"path": str(p), "label": p.name})
                    except OSError:
                        pass

    elif system == "Darwin":
        vols = Path("/Volumes")
        if vols.exists():
            for v in vols.iterdir():
                if v.is_dir() and v.name != "Macintosh HD":
                    results.append({"path": str(v), "label": v.name})

    elif system == "Windows":
        import string
        for letter in string.ascii_uppercase[2:]:  # skip A:\ B:\
            d = Path(f"{letter}:\\")
            if d.exists():
                results.append({"path": str(d), "label": f"{letter}:\\"})

    return results


@app.get("/api/devices")
async def list_devices() -> list[dict]:
    """Return detected removable drives / mount points."""
    return _list_mounts()


class CopyRequest(BaseModel):
    track_ids: List[int]
    device_path: str
    organize: bool = True  # arrange into Music/Artist/Album/ on device


@app.post("/api/devices/copy")
async def copy_to_device(req: CopyRequest) -> dict:
    """Copy one or more library tracks to a connected device."""
    device = Path(req.device_path)
    if not device.exists():
        raise HTTPException(status_code=404, detail=f"Device path not found: {req.device_path}")

    copied = 0
    skipped = 0
    errors: list[dict] = []

    for tid in req.track_ids:
        track = get_track(tid)
        if not track:
            errors.append({"id": tid, "reason": "track not found"})
            continue

        src = Path(track["path"])
        if not src.exists():
            errors.append({"id": tid, "reason": "file missing from disk"})
            continue

        if req.organize:
            artist = _safe_name(track.get("artist") or "Unknown Artist")
            album  = _safe_name(track.get("album")  or "Unknown Album")
            dest_dir = device / "Music" / artist / album
        else:
            dest_dir = device / "Music"

        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / src.name
            if dest.exists():
                skipped += 1
                continue
            shutil.copy2(str(src), str(dest))
            copied += 1
        except OSError as exc:
            errors.append({"id": tid, "reason": str(exc)})

    return {"copied": copied, "skipped": skipped, "errors": errors}
