"""Tests for music_updater.artwork."""

from __future__ import annotations

import pytest
import responses as resp_lib
import requests

from music_updater.artwork import fetch_artwork, _best_itunes_match


# ---------------------------------------------------------------------------
# _best_itunes_match
# ---------------------------------------------------------------------------


class TestBestItunesMatch:
    def test_exact_match_preferred(self):
        results = [
            {"collectionName": "Greatest Hits Vol. 2"},
            {"collectionName": "Abbey Road"},
        ]
        best = _best_itunes_match(results, "Abbey Road")
        assert best["collectionName"] == "Abbey Road"

    def test_case_insensitive_match(self):
        results = [
            {"collectionName": "Abbey Road"},
            {"collectionName": "Let It Be"},
        ]
        best = _best_itunes_match(results, "abbey road")
        assert best["collectionName"] == "Abbey Road"

    def test_fallback_to_first_when_no_match(self):
        results = [
            {"collectionName": "Revolver"},
            {"collectionName": "Help!"},
        ]
        best = _best_itunes_match(results, "Abbey Road")
        assert best["collectionName"] == "Revolver"


# ---------------------------------------------------------------------------
# fetch_artwork – mocked HTTP
# ---------------------------------------------------------------------------


FAKE_JPEG = b"\xff\xd8\xff\xd9"  # Minimal JPEG marker pair
FAKE_PNG = b"\x89PNG\r\n\x1a\n"  # PNG signature


@resp_lib.activate
def test_fetch_artwork_itunes_success():
    """Happy path: iTunes returns a result and the image downloads."""
    itunes_payload = {
        "resultCount": 1,
        "results": [
            {
                "collectionName": "Abbey Road",
                "artworkUrl100": "https://is1-ssl.mzstatic.com/image/thumb/abc/100x100bb.jpg",
            }
        ],
    }
    resp_lib.add(
        resp_lib.GET,
        "https://itunes.apple.com/search",
        json=itunes_payload,
        status=200,
    )
    resp_lib.add(
        resp_lib.GET,
        "https://is1-ssl.mzstatic.com/image/thumb/abc/600x600bb.jpg",
        body=FAKE_JPEG,
        content_type="image/jpeg",
        status=200,
    )

    session = requests.Session()
    result = fetch_artwork("The Beatles", "Abbey Road", size=600, session=session)

    assert result is not None
    image_data, mime_type = result
    assert image_data == FAKE_JPEG
    assert "jpeg" in mime_type


@resp_lib.activate
def test_fetch_artwork_falls_back_to_musicbrainz():
    """When iTunes returns no results, MusicBrainz + CAA should be tried."""
    # iTunes: empty results
    resp_lib.add(
        resp_lib.GET,
        "https://itunes.apple.com/search",
        json={"resultCount": 0, "results": []},
        status=200,
    )
    # MusicBrainz search
    resp_lib.add(
        resp_lib.GET,
        "https://musicbrainz.org/ws/2/release",
        json={"releases": [{"id": "test-mbid-1234"}]},
        status=200,
    )
    # Cover Art Archive
    resp_lib.add(
        resp_lib.GET,
        "https://coverartarchive.org/release/test-mbid-1234/front",
        body=FAKE_JPEG,
        content_type="image/jpeg",
        status=200,
    )

    session = requests.Session()
    result = fetch_artwork("Unknown Artist", "Unknown Album", session=session)

    assert result is not None
    image_data, mime_type = result
    assert image_data == FAKE_JPEG


@resp_lib.activate
def test_fetch_artwork_returns_none_when_all_fail():
    """Returns None when both iTunes and MusicBrainz fail."""
    resp_lib.add(
        resp_lib.GET,
        "https://itunes.apple.com/search",
        json={"resultCount": 0, "results": []},
        status=200,
    )
    resp_lib.add(
        resp_lib.GET,
        "https://musicbrainz.org/ws/2/release",
        json={"releases": []},
        status=200,
    )

    session = requests.Session()
    result = fetch_artwork("Nobody", "Nothing", session=session)

    assert result is None


@resp_lib.activate
def test_fetch_artwork_handles_itunes_error_gracefully():
    """Network error on iTunes should not crash; falls through to MusicBrainz."""
    resp_lib.add(
        resp_lib.GET,
        "https://itunes.apple.com/search",
        body=requests.exceptions.ConnectionError("timeout"),
    )
    resp_lib.add(
        resp_lib.GET,
        "https://musicbrainz.org/ws/2/release",
        json={"releases": []},
        status=200,
    )

    session = requests.Session()
    result = fetch_artwork("Artist", "Album", session=session)
    assert result is None
