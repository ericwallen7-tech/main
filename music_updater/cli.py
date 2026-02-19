"""Command-line interface for music-metadata-updater."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

import click
import requests
from rich.console import Console
from rich.table import Table
from rich import box

from .artwork import fetch_artwork
from .metadata import AudioFile, SUPPORTED_EXTENSIONS
from .scanner import scan

console = Console()
err_console = Console(stderr=True)

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------


@click.group()
@click.version_option()
def main() -> None:
    """Update music file metadata and fetch album artwork from online sources."""


# ---------------------------------------------------------------------------
# info
# ---------------------------------------------------------------------------


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--recursive/--no-recursive", "-r/-R", default=True, show_default=True)
def info(path: str, recursive: bool) -> None:
    """Show metadata for audio file(s) at PATH."""
    files = list(scan(path, recursive=recursive))
    if not files:
        err_console.print(f"[yellow]No supported audio files found at:[/] {path}")
        sys.exit(1)

    for fp in files:
        try:
            af = AudioFile(fp)
        except Exception as exc:
            err_console.print(f"[red]Cannot read {fp.name}:[/] {exc}")
            continue

        _print_info(af)


def _print_info(af: AudioFile) -> None:
    table = Table(
        title=f"[bold]{af.path.name}[/]",
        box=box.ROUNDED,
        show_header=False,
        padding=(0, 1),
    )
    table.add_column("Field", style="cyan", no_wrap=True)
    table.add_column("Value")

    meta = af.to_dict()
    labels = {
        "title": "Title",
        "artist": "Artist",
        "album": "Album",
        "year": "Year",
        "track": "Track",
        "genre": "Genre",
        "has_artwork": "Artwork",
    }
    for key, label in labels.items():
        value = meta[key]
        if key == "has_artwork":
            display = "[green]Yes[/]" if value else "[red]No[/]"
        else:
            display = str(value) if value is not None else "[dim]—[/]"
        table.add_row(label, display)

    console.print(table)
    console.print()


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--title", "-t", help="Track title")
@click.option("--artist", "-a", help="Artist name")
@click.option("--album", "-A", help="Album name")
@click.option("--year", "-y", help="Release year (e.g. 2024)")
@click.option("--track", "-n", help="Track number (e.g. 3 or 3/12)")
@click.option("--genre", "-g", help="Genre")
@click.option("--recursive/--no-recursive", "-r/-R", default=False, show_default=True)
def update(
    path: str,
    title: Optional[str],
    artist: Optional[str],
    album: Optional[str],
    year: Optional[str],
    track: Optional[str],
    genre: Optional[str],
    recursive: bool,
) -> None:
    """Set metadata fields for audio file(s) at PATH."""
    fields = {k: v for k, v in dict(
        title=title, artist=artist, album=album,
        year=year, track=track, genre=genre,
    ).items() if v is not None}

    if not fields:
        err_console.print("[yellow]No fields specified. Use --help to see options.[/]")
        sys.exit(1)

    files = list(scan(path, recursive=recursive))
    if not files:
        err_console.print(f"[yellow]No supported audio files found at:[/] {path}")
        sys.exit(1)

    for fp in files:
        try:
            af = AudioFile(fp)
            for field, value in fields.items():
                setattr(af, field, value)
            af.save()
            console.print(f"[green]Updated[/] {fp.name}")
        except Exception as exc:
            err_console.print(f"[red]Failed to update {fp.name}:[/] {exc}")


# ---------------------------------------------------------------------------
# fetch-art
# ---------------------------------------------------------------------------


@main.command("fetch-art")
@click.argument("path", type=click.Path(exists=True))
@click.option("--artist", "-a", help="Override artist name for search")
@click.option("--album", "-A", help="Override album name for search")
@click.option("--size", "-s", default=600, show_default=True, help="Artwork size in pixels")
@click.option("--recursive/--no-recursive", "-r/-R", default=False, show_default=True)
@click.option("--overwrite/--no-overwrite", default=False, show_default=True,
              help="Replace existing embedded artwork")
def fetch_art(
    path: str,
    artist: Optional[str],
    album: Optional[str],
    size: int,
    recursive: bool,
    overwrite: bool,
) -> None:
    """Fetch and embed album artwork for audio file(s) at PATH."""
    files = list(scan(path, recursive=recursive))
    if not files:
        err_console.print(f"[yellow]No supported audio files found at:[/] {path}")
        sys.exit(1)

    with requests.Session() as session:
        for fp in files:
            try:
                af = AudioFile(fp)
                _embed_artwork(af, artist, album, size, overwrite, session)
            except Exception as exc:
                err_console.print(f"[red]Failed for {fp.name}:[/] {exc}")


def _embed_artwork(
    af: AudioFile,
    artist_override: Optional[str],
    album_override: Optional[str],
    size: int,
    overwrite: bool,
    session: requests.Session,
) -> None:
    if af.has_artwork and not overwrite:
        console.print(f"[dim]Skipped[/] {af.path.name} [dim](already has artwork; use --overwrite)[/]")
        return

    search_artist = artist_override or af.artist
    search_album = album_override or af.album

    if not search_artist or not search_album:
        err_console.print(
            f"[yellow]Skipped {af.path.name}:[/] missing artist/album tags "
            "(use --artist / --album to override)"
        )
        return

    console.print(f"Searching for artwork: [cyan]{search_artist}[/] — [cyan]{search_album}[/] …")
    result = fetch_artwork(search_artist, search_album, size=size, session=session)

    if result is None:
        err_console.print(f"[yellow]No artwork found for[/] {af.path.name}")
        return

    image_data, mime_type = result
    af.set_artwork(image_data, mime_type)
    af.save()
    console.print(f"[green]Embedded artwork[/] ({len(image_data) // 1024} KB, {mime_type}) → {af.path.name}")


# ---------------------------------------------------------------------------
# auto
# ---------------------------------------------------------------------------


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--recursive/--no-recursive", "-r/-R", default=True, show_default=True)
@click.option("--overwrite-art/--no-overwrite-art", default=False, show_default=True,
              help="Replace existing embedded artwork")
@click.option("--size", "-s", default=600, show_default=True, help="Artwork size in pixels")
def auto(path: str, recursive: bool, overwrite_art: bool, size: int) -> None:
    """Show metadata then fetch missing artwork for all files at PATH.

    This is a convenience command that combines `info` and `fetch-art`.
    Only artwork that is not already embedded will be fetched (use
    --overwrite-art to replace existing artwork).
    """
    files = list(scan(path, recursive=recursive))
    if not files:
        err_console.print(f"[yellow]No supported audio files found at:[/] {path}")
        sys.exit(1)

    console.print(f"\n[bold]Found {len(files)} audio file(s)[/]\n")

    with requests.Session() as session:
        for fp in files:
            try:
                af = AudioFile(fp)
                _print_info(af)
                _embed_artwork(af, None, None, size, overwrite_art, session)
            except Exception as exc:
                err_console.print(f"[red]Error processing {fp.name}:[/] {exc}")


# ---------------------------------------------------------------------------
# scan (list files only)
# ---------------------------------------------------------------------------


@main.command()
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
@click.option("--recursive/--no-recursive", "-r/-R", default=True, show_default=True)
def scan_dir(directory: str, recursive: bool) -> None:
    """List supported audio files found in DIRECTORY."""
    files = list(scan(directory, recursive=recursive))
    if not files:
        console.print("[yellow]No supported audio files found.[/]")
        return

    table = Table(title=f"{len(files)} file(s) in {directory}", box=box.SIMPLE)
    table.add_column("#", style="dim", justify="right")
    table.add_column("File", style="cyan")
    table.add_column("Format", justify="center")
    table.add_column("Size", justify="right")

    for i, fp in enumerate(files, 1):
        size_kb = fp.stat().st_size // 1024
        table.add_row(str(i), str(fp), fp.suffix.upper().lstrip("."), f"{size_kb} KB")

    console.print(table)


# Alias for the CLI entry point
main.add_command(scan_dir, name="scan")


# ---------------------------------------------------------------------------
# serve
# ---------------------------------------------------------------------------


@main.command()
@click.option("--host", default="127.0.0.1", show_default=True, help="Bind address")
@click.option("--port", "-p", default=8000, show_default=True, help="Port to listen on")
@click.option("--reload", is_flag=True, default=False, help="Enable auto-reload (dev mode)")
def serve(host: str, port: int, reload: bool) -> None:
    """Start the web UI and music player server.

    Open http://HOST:PORT in your browser after starting.
    Use the Scan input in the sidebar to index your music folder.
    """
    try:
        import uvicorn
    except ImportError:
        err_console.print(
            "[red]uvicorn is not installed.[/] Run: [bold]pip install uvicorn[standard][/]"
        )
        raise SystemExit(1)

    console.print(
        f"\n[bold green]Music Library[/] is running at "
        f"[underline]http://{host}:{port}[/]\n"
        "Press [bold]Ctrl+C[/] to stop.\n"
    )
    uvicorn.run(
        "music_updater.server:app",
        host=host,
        port=port,
        reload=reload,
        log_level="warning",
    )
