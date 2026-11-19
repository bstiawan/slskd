#!/usr/bin/env python3
"""Tests for scripts/organize-download.py using real mutagen WAV fixtures."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
import wave

import mutagen
from mutagen.id3 import TALB, TPE1, TPE2
from mutagen.wave import WAVE


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "organize-download.py"
_spec = importlib.util.spec_from_file_location("organize_download", SCRIPT_PATH)
organize_download = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(organize_download)


class OrganizeDownloadTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = (Path(self.tempdir.name) / "library").resolve()
        self.incoming = self.root / ".incoming"
        self.incoming.mkdir(parents=True)

    def tearDown(self):
        self.tempdir.cleanup()

    def make_wav(self, name, *, artist=None, album=None, albumartist=None, raw_id3=False):
        source = self.incoming / name
        source.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(source), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(8000)
            output.writeframes(b"\x00\x00" * 80)

        audio = WAVE(source)
        audio.add_tags()
        if artist is not None:
            audio.tags.add(TPE1(encoding=3, text=[artist]))
        if albumartist is not None:
            audio.tags.add(TPE2(encoding=3, text=[albumartist]))
        if album is not None:
            audio.tags.add(TALB(encoding=3, text=[album]))
        audio.save()
        return source

    def make_text(self, relative_name, content=b"not audio"):
        source = self.incoming / relative_name
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(content)
        return source

    def test_organizes_wav_using_artist_and_album_and_preserves_bytes(self):
        source = self.make_wav("track.wav", artist="Artist", album="Album")
        original = source.read_bytes()

        result = organize_download.organize(source, self.root)

        self.assertEqual(result, self.root / "Artist" / "Album" / "track.wav")
        self.assertEqual(result.read_bytes(), original)
        self.assertFalse(source.exists())

    def test_albumartist_is_preferred_when_artist_is_absent(self):
        source = self.make_wav("track.wav", albumartist="Album Artist", album="Album")

        result = organize_download.organize(source, self.root)

        self.assertEqual(result, self.root / "Album Artist" / "Album" / "track.wav")

    def test_raw_id3_frames_are_supported(self):
        source = self.make_wav(
            "raw.wav", artist="Raw Artist", album="Raw Album", raw_id3=True
        )

        result = organize_download.organize(source, self.root)

        self.assertEqual(result, self.root / "Raw Artist" / "Raw Album" / "raw.wav")

    def test_missing_artist_and_album_use_safe_fallbacks(self):
        source = self.make_wav("untagged.wav")

        result = organize_download.organize(source, self.root)

        self.assertEqual(result, self.root / "Unknown Artist" / "Tracks" / "untagged.wav")

    def test_artist_and_album_path_components_are_sanitized(self):
        source = self.make_wav("track.wav", artist='A/B\\C:D', album="Album")

        result = organize_download.organize(source, self.root)

        self.assertEqual(result, self.root / "A_B_C_D" / "Album" / "track.wav")

    def test_traversal_components_fall_back_to_safe_names(self):
        source = self.make_wav("track.wav", artist="..", album=".")

        result = organize_download.organize(source, self.root)

        self.assertEqual(result, self.root / "Unknown Artist" / "Tracks" / "track.wav")

    def test_duplicate_event_is_idempotent_when_source_is_missing(self):
        self.assertIsNone(organize_download.organize(self.incoming / "missing.wav", self.root))

    def test_existing_destination_is_preserved_and_collision_gets_suffix(self):
        first = self.make_wav("track.wav", artist="Artist", album="Album")
        first_bytes = first.read_bytes()
        first_result = organize_download.organize(first, self.root)

        second = self.make_wav("track.wav", artist="Artist", album="Album")
        second_bytes = second.read_bytes()
        second_result = organize_download.organize(second, self.root)

        self.assertEqual(first_result, self.root / "Artist" / "Album" / "track.wav")
        self.assertEqual(second_result, self.root / "Artist" / "Album" / "track (2).wav")
        self.assertEqual(first_result.read_bytes(), first_bytes)
        self.assertEqual(second_result.read_bytes(), second_bytes)

    def test_non_audio_is_returned_as_none_and_left_unchanged(self):
        source = self.make_text("readme.bin")
        original = source.read_bytes()

        result = organize_download.organize(source, self.root)

        self.assertIsNone(result)
        self.assertTrue(source.exists())
        self.assertEqual(source.read_bytes(), original)

    def test_source_outside_incoming_is_rejected(self):
        source = self.root / "outside.wav"
        source.write_bytes(b"outside")

        with self.assertRaises(ValueError):
            organize_download.organize(source, self.root)

        self.assertTrue(source.exists())

    def test_source_symlink_escape_is_rejected(self):
        outside = Path(self.tempdir.name) / "outside.wav"
        target = self.make_wav("target.wav", artist="Artist")
        outside.write_bytes(target.read_bytes())
        link = self.incoming / "link.wav"
        link.symlink_to(outside)

        with self.assertRaises(ValueError):
            organize_download.organize(link, self.root)

        self.assertTrue(link.is_symlink())

    def test_destination_symlink_escape_is_rejected_without_writing_outside(self):
        source = self.make_wav("track.wav", artist="Escape", album="Album")
        outside = Path(self.tempdir.name) / "outside"
        outside.mkdir()
        (self.root / "Escape").symlink_to(outside, target_is_directory=True)

        with self.assertRaises(ValueError):
            organize_download.organize(source, self.root)

        self.assertTrue(source.exists())
        self.assertEqual(list(outside.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
