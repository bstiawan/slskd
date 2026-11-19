"""Verify track naming from music tags, including multi-disc albums."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
import wave

from mutagen.wave import WAVE
from mutagen.id3 import TALB, TIT2, TPE1, TPOS, TRCK

spec = importlib.util.spec_from_file_location('organizer', Path(__file__).resolve().parents[2] / 'scripts/organize-download.py')
organizer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(organizer)


class NamingTests(unittest.TestCase):
    def save_track(self, root, track='2/15', title='Remember to Breathe', disc='1/1'):
        source = root / '.incoming/remote/odd_name.WAV'
        source.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(source), 'wb') as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(8000)
            handle.writeframes(b'\x00\x00' * 80)
        audio = WAVE(source)
        audio.add_tags()
        for frame in [TPE1(text=['Artist']), TALB(text=['Album']), TRCK(text=[track]), TIT2(text=[title]), TPOS(text=[disc])]:
            audio.tags.add(frame)
        audio.save()
        return source

    def test_single_disc_uses_track_number_and_preserves_title_case(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            source = self.save_track(root)
            original = source.read_bytes()
            result = organizer.organize(source, root)
            self.assertEqual(result.relative_to(root).as_posix(), 'Artist/Album/02 - Remember to Breathe.wav')
            self.assertEqual(result.read_bytes(), original)
            self.assertTrue(source.parent.is_dir(), 'Keep staging folders available for the next download')

    def test_multiple_discs_keep_same_track_numbers_separate(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            first = organizer.organize(self.save_track(root, disc='1/2'), root)
            second = organizer.organize(self.save_track(root, disc='2/2'), root)
            self.assertEqual(first.parent.name, 'Disc 01')
            self.assertEqual(second.parent.name, 'Disc 02')
            self.assertEqual(first.name, second.name)

    def test_invalid_track_number_preserves_filename(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            result = organizer.organize(self.save_track(root, track='bad'), root)
            self.assertEqual(result.name, 'odd_name.WAV')

    def test_title_separators_cannot_create_directories(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            result = organizer.organize(self.save_track(root, title='../../A/B: C'), root)
            self.assertEqual(result.parent, root / 'Artist/Album')
            self.assertNotIn('/', result.name)


if __name__ == '__main__':
    unittest.main()
