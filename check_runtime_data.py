"""Ensure mutable runtime data never relies on the executable directory."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import ytdl
from song_catalogue import SongCatalogue


class DataPaths(unittest.TestCase):
    def test_portable_directory_stays_clean(self):
        with tempfile.TemporaryDirectory(dir='.checkenv') as folder:
            root = Path(folder)
            portable, data = root / 'desktop-copy', root / 'app-data'
            portable.mkdir()
            with patch.dict(os.environ, {'YTDL_DATA_DIR': str(data)}), patch.object(ytdl, 'runtime_dir', return_value=portable):
                ytdl.app_data_file('.download-source-index.json').write_text('{}')
                ytdl.app_data_file('.media-library-cache.json').write_text('{}')
                ytdl.app_data_file('ytdl_startup_error.log').write_text('test')
                db = SongCatalogue(ytdl.app_data_dir() / 'idol_names' / 'song_catalogue.json')
                db.save_group('test', {'songs': []})
                self.assertEqual(list(portable.iterdir()), [])
                self.assertEqual(ytdl.preview_cache_dir(), data / 'preview-cache')

    def test_legacy_index_migration_never_overwrites_new_data(self):
        with tempfile.TemporaryDirectory(dir='.checkenv') as folder:
            root = Path(folder)
            portable, data = root / 'portable', root / 'data'
            portable.mkdir()
            old = portable / '.download-source-index.json'
            old.write_text('legacy')
            with patch.dict(os.environ, {'YTDL_DATA_DIR': str(data)}), patch.object(ytdl, 'runtime_dir', return_value=portable):
                new = ytdl.app_data_file(old.name, migrate=True)
                self.assertEqual(new.read_text(), 'legacy')
                new.write_text('updated')
                self.assertEqual(ytdl.app_data_file(old.name, migrate=True).read_text(), 'updated')
                self.assertEqual(old.read_text(), 'legacy')

    def test_private_cookies_and_engine_precedence(self):
        with tempfile.TemporaryDirectory(dir='.checkenv') as folder:
            root = Path(folder)
            portable, data = root / 'portable', root / 'data'
            portable.mkdir()
            data.mkdir()
            for base in (portable, data):
                (base / 'cookies.txt').write_text('private')
                (base / 'yt_dlp.exe').write_text('engine')
            with patch.dict(os.environ, {'YTDL_DATA_DIR': str(data)}), patch.object(ytdl, 'runtime_dir', return_value=portable):
                self.assertEqual(ytdl.engine_path(), data / 'yt_dlp.exe')
                self.assertEqual(ytdl.cookie_path(), data / 'cookies.txt')


if __name__ == '__main__':
    unittest.main()
