"""Read and write audio file metadata for MP3, FLAC, and M4A/AAC formats."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from mutagen.flac import FLAC, Picture
from mutagen.id3 import (
    APIC,
    ID3,
    ID3NoHeaderError,
    TALB,
    TCON,
    TDRC,
    TIT2,
    TPE1,
    TRCK,
)
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover
from mutagen.wave import WAVE

SUPPORTED_EXTENSIONS = frozenset({".mp3", ".flac", ".m4a", ".aac", ".wav"})


class AudioFile:
    """Unified read/write interface for MP3, FLAC, and M4A/AAC metadata."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if self.path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported format '{self.path.suffix}'. "
                f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            )
        self._fmt = self.path.suffix.lower()
        self._wave = None  # only set for .wav files
        self._tag = self._load_tag()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_tag(self):
        if self._fmt == ".mp3":
            try:
                return ID3(str(self.path))
            except ID3NoHeaderError:
                tag = ID3()
                tag.save(str(self.path))
                return tag
        elif self._fmt == ".flac":
            return FLAC(str(self.path))
        elif self._fmt == ".wav":
            w = WAVE(str(self.path))
            if w.tags is None:
                w.add_tags()
            self._wave = w
            return w.tags
        else:  # .m4a / .aac
            return MP4(str(self.path))

    def _get_id3(self, frame_id: str) -> Optional[str]:
        frame = self._tag.get(frame_id)
        return str(frame) if frame else None

    def _set_id3_text(self, frame_cls, frame_id: str, value: str) -> None:
        self._tag[frame_id] = frame_cls(encoding=3, text=value)

    def _get_flac(self, key: str) -> Optional[str]:
        vals = self._tag.get(key.lower())
        return vals[0] if vals else None

    def _set_flac(self, key: str, value: str) -> None:
        self._tag[key.lower()] = [value]

    def _get_mp4(self, atom: str) -> Optional[str]:
        vals = self._tag.get(atom)
        return str(vals[0]) if vals else None

    def _set_mp4(self, atom: str, value: str) -> None:
        self._tag[atom] = [value]

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def title(self) -> Optional[str]:
        if self._fmt in (".mp3", ".wav"):
            return self._get_id3("TIT2")
        elif self._fmt == ".flac":
            return self._get_flac("title")
        return self._get_mp4("\xa9nam")

    @title.setter
    def title(self, value: str) -> None:
        if self._fmt in (".mp3", ".wav"):
            self._set_id3_text(TIT2, "TIT2", value)
        elif self._fmt == ".flac":
            self._set_flac("title", value)
        else:
            self._set_mp4("\xa9nam", value)

    @property
    def artist(self) -> Optional[str]:
        if self._fmt in (".mp3", ".wav"):
            return self._get_id3("TPE1")
        elif self._fmt == ".flac":
            return self._get_flac("artist")
        return self._get_mp4("\xa9ART")

    @artist.setter
    def artist(self, value: str) -> None:
        if self._fmt in (".mp3", ".wav"):
            self._set_id3_text(TPE1, "TPE1", value)
        elif self._fmt == ".flac":
            self._set_flac("artist", value)
        else:
            self._set_mp4("\xa9ART", value)

    @property
    def album(self) -> Optional[str]:
        if self._fmt in (".mp3", ".wav"):
            return self._get_id3("TALB")
        elif self._fmt == ".flac":
            return self._get_flac("album")
        return self._get_mp4("\xa9alb")

    @album.setter
    def album(self, value: str) -> None:
        if self._fmt in (".mp3", ".wav"):
            self._set_id3_text(TALB, "TALB", value)
        elif self._fmt == ".flac":
            self._set_flac("album", value)
        else:
            self._set_mp4("\xa9alb", value)

    @property
    def year(self) -> Optional[str]:
        if self._fmt in (".mp3", ".wav"):
            return self._get_id3("TDRC")
        elif self._fmt == ".flac":
            return self._get_flac("date")
        return self._get_mp4("\xa9day")

    @year.setter
    def year(self, value: str) -> None:
        if self._fmt in (".mp3", ".wav"):
            self._set_id3_text(TDRC, "TDRC", value)
        elif self._fmt == ".flac":
            self._set_flac("date", value)
        else:
            self._set_mp4("\xa9day", value)

    @property
    def track(self) -> Optional[str]:
        if self._fmt in (".mp3", ".wav"):
            return self._get_id3("TRCK")
        elif self._fmt == ".flac":
            return self._get_flac("tracknumber")
        val = self._tag.get("trkn")
        if val:
            num, total = val[0]
            return f"{num}/{total}" if total else str(num)
        return None

    @track.setter
    def track(self, value: str) -> None:
        if self._fmt in (".mp3", ".wav"):
            self._set_id3_text(TRCK, "TRCK", value)
        elif self._fmt == ".flac":
            self._set_flac("tracknumber", value)
        else:
            parts = value.split("/")
            num = int(parts[0])
            total = int(parts[1]) if len(parts) > 1 else 0
            self._tag["trkn"] = [(num, total)]

    @property
    def genre(self) -> Optional[str]:
        if self._fmt in (".mp3", ".wav"):
            return self._get_id3("TCON")
        elif self._fmt == ".flac":
            return self._get_flac("genre")
        return self._get_mp4("\xa9gen")

    @genre.setter
    def genre(self, value: str) -> None:
        if self._fmt in (".mp3", ".wav"):
            self._set_id3_text(TCON, "TCON", value)
        elif self._fmt == ".flac":
            self._set_flac("genre", value)
        else:
            self._set_mp4("\xa9gen", value)

    @property
    def has_artwork(self) -> bool:
        if self._fmt in (".mp3", ".wav"):
            return any(k.startswith("APIC") for k in self._tag.keys())
        elif self._fmt == ".flac":
            return len(self._tag.pictures) > 0
        return bool(self._tag.get("covr"))

    # ------------------------------------------------------------------
    # Artwork
    # ------------------------------------------------------------------

    def set_artwork(self, image_data: bytes, mime_type: str = "image/jpeg") -> None:
        """Embed cover art into the file."""
        if self._fmt in (".mp3", ".wav"):
            # Remove any existing artwork frames
            self._tag.delall("APIC")
            self._tag["APIC"] = APIC(
                encoding=3,
                mime=mime_type,
                type=3,  # Cover (front)
                desc="Cover",
                data=image_data,
            )
        elif self._fmt == ".flac":
            pic = Picture()
            pic.type = 3
            pic.mime = mime_type
            pic.desc = "Cover"
            pic.data = image_data
            self._tag.clear_pictures()
            self._tag.add_picture(pic)
        else:
            fmt = (
                MP4Cover.FORMAT_JPEG
                if "jpeg" in mime_type or "jpg" in mime_type
                else MP4Cover.FORMAT_PNG
            )
            self._tag["covr"] = [MP4Cover(image_data, imageformat=fmt)]

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> None:
        """Write all pending changes back to disk."""
        if self._fmt == ".mp3":
            self._tag.save(str(self.path))
        elif self._fmt == ".wav":
            self._wave.save()
        else:
            self._tag.save()

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "year": self.year,
            "track": self.track,
            "genre": self.genre,
            "has_artwork": self.has_artwork,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"AudioFile({self.path.name!r})"
