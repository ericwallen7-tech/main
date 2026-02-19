"""Fetch album artwork from online sources.

Sources (tried in order):
1. iTunes Search API  - free, no auth, returns high-res JPEG
2. MusicBrainz + Cover Art Archive - open database, no auth required
"""

from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)

_ITUNES_SEARCH = "https://itunes.apple.com/search"
_MUSICBRAINZ_SEARCH = "https://musicbrainz.org/ws/2/release"
_COVER_ART_ARCHIVE = "https://coverartarchive.org/release/{mbid}/front"

# MusicBrainz requires a descriptive User-Agent
_MB_USER_AGENT = (
    "music-metadata-updater/0.1.0 ( https://github.com/your-org/music-metadata-updater )"
)

_REQUEST_TIMEOUT = 15  # seconds


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fetch_artwork(
    artist: str,
    album: str,
    size: int = 600,
    session: Optional[requests.Session] = None,
) -> Optional[tuple[bytes, str]]:
    """Return ``(image_bytes, mime_type)`` for *artist* / *album*, or ``None``.

    Tries the iTunes Search API first, then falls back to the MusicBrainz /
    Cover Art Archive pipeline.

    Args:
        artist: Artist name.
        album:  Album title.
        size:   Desired image dimension (iTunes only; nearest available is used).
        session: Optional ``requests.Session`` to reuse connections.
    """
    sess = session or requests.Session()

    result = _itunes(artist, album, size, sess)
    if result:
        return result

    logger.debug("iTunes returned nothing; trying MusicBrainz…")
    return _musicbrainz(artist, album, sess)


# ---------------------------------------------------------------------------
# iTunes
# ---------------------------------------------------------------------------


def _itunes(
    artist: str,
    album: str,
    size: int,
    session: requests.Session,
) -> Optional[tuple[bytes, str]]:
    """Query the iTunes Search API and download the best-matching cover."""
    params = {
        "term": f"{artist} {album}",
        "entity": "album",
        "media": "music",
        "limit": "5",
        "lang": "en_us",
    }
    try:
        resp = session.get(_ITUNES_SEARCH, params=params, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("iTunes search failed: %s", exc)
        return None

    results = data.get("results", [])
    if not results:
        return None

    # Pick the result whose collectionName is the closest match.
    best = _best_itunes_match(results, album)
    artwork_url: str = best.get("artworkUrl100", "")
    if not artwork_url:
        return None

    # iTunes artwork URLs end in "100x100bb.jpg"; swap in our desired size.
    artwork_url = artwork_url.replace("100x100bb", f"{size}x{size}bb")

    return _download_image(artwork_url, session)


def _best_itunes_match(results: list[dict], album: str) -> dict:
    """Return the result whose collection name best matches *album*."""
    album_lower = album.lower()
    for r in results:
        if r.get("collectionName", "").lower() == album_lower:
            return r
    return results[0]


# ---------------------------------------------------------------------------
# MusicBrainz + Cover Art Archive
# ---------------------------------------------------------------------------


def _musicbrainz(
    artist: str,
    album: str,
    session: requests.Session,
) -> Optional[tuple[bytes, str]]:
    """Search MusicBrainz for a release MBID, then fetch its cover art."""
    mbid = _search_mb_release(artist, album, session)
    if not mbid:
        return None

    url = _COVER_ART_ARCHIVE.format(mbid=mbid)
    return _download_image(url, session, extra_headers={"User-Agent": _MB_USER_AGENT})


def _search_mb_release(
    artist: str,
    album: str,
    session: requests.Session,
) -> Optional[str]:
    """Return the MusicBrainz release MBID for *artist* / *album*, or ``None``."""
    query = f'artist:"{quote(artist)}" AND release:"{quote(album)}"'
    params = {"query": query, "fmt": "json", "limit": "5"}
    headers = {"User-Agent": _MB_USER_AGENT}
    try:
        resp = session.get(
            _MUSICBRAINZ_SEARCH,
            params=params,
            headers=headers,
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("MusicBrainz search failed: %s", exc)
        return None

    releases = data.get("releases", [])
    if not releases:
        return None
    return releases[0].get("id")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _download_image(
    url: str,
    session: requests.Session,
    extra_headers: Optional[dict] = None,
) -> Optional[tuple[bytes, str]]:
    """Download an image from *url* and return ``(bytes, mime_type)``."""
    headers = extra_headers or {}
    try:
        resp = session.get(url, headers=headers, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("Image download failed (%s): %s", url, exc)
        return None

    content_type = resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
    return resp.content, content_type
