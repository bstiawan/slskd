#!/usr/bin/env python3
"""Sort completed slskd music downloads using embedded artist/album tags."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import sys

import mutagen


def component(value, fallback):
    value = re.sub(r'[/\\:\x00-\x1f\x7f]', '_', str(value or '')).strip(' .')
    value = value.encode('utf-8')[:180].decode('utf-8', errors='ignore').rstrip(' .')
    return value or fallback


def tag(tags, *names):
    for name in names:
        value = tags.get(name)
        if value is None:
            continue
        if hasattr(value, 'text'):
            value = value.text
        if isinstance(value, (list, tuple)):
            value = value[0] if value else ''
        if str(value).strip():
            return str(value).strip()
    return ''


def position(value):
    match = re.fullmatch(r'\s*(\d+)(?:\s*/\s*(\d+))?\s*', value or '')
    if not match or not 1 <= int(match[1]) <= 999:
        return 0, 0
    return int(match[1]), int(match[2] or 0)


def track_destination(tags, source):
    title = tag(tags, 'title', 'TIT2', '\xa9nam')
    track, _ = position(tag(tags, 'tracknumber', 'TRCK'))
    disc, total = position(tag(tags, 'discnumber', 'TPOS'))
    total = max(total, position(tag(tags, 'disctotal', 'totaldiscs'))[0])
    disc_folder = f'Disc {disc:02d}' if disc and (disc > 1 or total > 1) else ''
    filename = f'{track:02d} - {component(title, "Untitled")}{source.suffix.lower()}' if track and title else source.name
    return disc_folder, filename


def organize(source, root):
    root = Path(root).resolve()
    incoming = root / '.incoming'
    source = Path(source)
    # Check both the lexical path and resolved path, including symlinks.
    if not source.is_absolute() or incoming not in source.parents:
        raise ValueError('Completed file must be inside the library .incoming directory')
    resolved = source.resolve()
    if incoming.resolve() != incoming or incoming not in resolved.parents or source.is_symlink():
        raise ValueError('Refusing an unsafe source path')
    if not source.exists():
        return None  # duplicate delivery after the previous invocation moved it
    if not source.is_file():
        raise ValueError('Completed path must be a regular file')
    try:
        audio = mutagen.File(source, easy=True)
    except mutagen.MutagenError:
        return None  # preserve invalid audio and other files for inspection
    if audio is None:
        return None
    tags = audio.tags or {}
    artist = component(tag(tags, 'artist', 'TPE1', '\xa9ART', 'albumartist', 'TPE2', 'aART'), 'Unknown Artist')
    album = component(tag(tags, 'album', 'TALB', '\xa9alb'), 'Tracks')
    directory = root / artist / album
    disc_folder, filename = track_destination(tags, source)
    if disc_folder:
        directory /= disc_folder
    # Embedded tags and pre-existing links must never move a file outside the library.
    if root not in directory.resolve().parents or incoming in directory.resolve().parents:
        raise ValueError('Refusing an unsafe artist/album directory')
    directory.mkdir(parents=True, exist_ok=True)
    if root not in directory.resolve().parents:
        raise ValueError('Artist/album directory escapes the library')
    destination = directory / filename
    stem, suffix = Path(filename).stem, Path(filename).suffix
    counter = 1
    while True:
        try:
            output = destination.open('xb')
            break
        except FileExistsError:
            counter += 1
            destination = directory / f'{stem} ({counter}){suffix}'
    # Exclusive creation preserves existing music even if two hooks run at once.
    try:
        with output, source.open('rb') as handle:
            shutil.copyfileobj(handle, output)
            output.flush()
            os.fsync(output.fileno())
        shutil.copystat(source, destination)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    source.unlink()
    # Keep staging directories while slskd may still be downloading other files
    # into them. Repeated delete/recreate cycles can deadlock iCloud File Provider.
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--lock', required=True, type=Path)
    args = parser.parse_args()
    event = json.loads(os.environ.get('SLSKD_SCRIPT_DATA', '{}'))
    if event.get('type') != 'DownloadFileComplete':
        return
    source = event.get('localFilename')
    if not isinstance(source, str) or not source:
        raise ValueError('Download event has no localFilename')
    # slskd starts one process per event; serialize duplicate deliveries and moves.
    with args.lock.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        destination = organize(Path(source), args.root)
    if destination:
        print(json.dumps({'organized': str(destination)}))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError) as error:
        print(f'Music organizer: {error}', file=sys.stderr)
        sys.exit(1)
