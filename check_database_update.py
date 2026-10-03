"""Offline database validation, atomic persistence and immediate UI reload checks."""
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest
import database_update as db
import ytdl
from idol_search import IdolCatalogue

ROOT = Path(__file__).resolve().parent


class DatabaseChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.idols = db.read_json(ROOT / 'idol_names/idol_aliases.json')
        cls.songs = db.read_json(ROOT / 'idol_names/song_catalogue.json')
        cls.pack = db.validate(cls.idols, cls.songs)
        cls.app = QApplication.instance() or QApplication([])

    def test_baby_dont_cry_identity_and_tracks(self):
        catalogue = IdolCatalogue(self.idols)
        for alias in ('baby dont cry', "Baby Don't Cry", 'babydontcry', '베이비돈크라이'):
            self.assertEqual(catalogue.resolve_group(alias)['name'], 'Baby DONT Cry')
        for english, korean in [('Yihyun', '이현'), ('Kumi', '쿠미'), ('Mia', '미아'), ('Beni', '베니')]:
            for name in (english, korean):
                matches = catalogue.member_matches(name, 'Baby DONT Cry')
                self.assertEqual(len(matches), 1)
                self.assertEqual(matches[0]['stage_name'], english)
        self.assertEqual(len(self.songs['groups']['Baby DONT Cry']['songs']), 8)

    def test_atomic_install_invalid_data_and_restart(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.checkenv') as folder:
            target = db.install_database(folder, self.pack)
            old = target.read_bytes()
            broken = copy.deepcopy(self.pack)
            broken['idols']['alias_index'] = {}
            with self.assertRaises(ValueError):
                db.install_database(folder, broken)
            self.assertEqual(target.read_bytes(), old)
            with patch('database_update.os.replace', side_effect=OSError('test lock')):
                with self.assertRaises(OSError):
                    db.install_database(folder, self.pack)
            self.assertEqual(target.read_bytes(), old)
            self.assertFalse(list(target.parent.glob('*.tmp')))
            loaded, error = db.load_databases(folder, ROOT / 'idol_names/idol_aliases.json', ROOT / 'idol_names/song_catalogue.json')
            self.assertEqual(loaded['idols'], self.idols)
            self.assertFalse(error)

    def test_corrupt_external_falls_back(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.checkenv') as folder:
            target = db.install_database(folder, self.pack)
            target.write_text('{broken', encoding='utf-8')
            loaded, error = db.load_databases(folder, ROOT / 'idol_names/idol_aliases.json', ROOT / 'idol_names/song_catalogue.json')
            self.assertTrue(error)
            self.assertEqual(loaded['idols'], self.idols)

    def test_local_import_all_supported_formats(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.checkenv') as folder:
            root = Path(folder)
            for name, data in [('idol_aliases.json', self.idols), ('song_catalogue.json', self.songs), (db.PACK_NAME, self.pack)]:
                (root / name).write_text(json.dumps(data), encoding='utf-8')
            for name in ('idol_aliases.json', 'song_catalogue.json', db.PACK_NAME):
                self.assertEqual(db.import_database(root / name, self.pack), self.pack)

    def test_online_uses_one_pinned_revision_and_cancellation(self):
        revision = 'a' * 40
        class Reply:
            def __init__(self, data):
                self.data = json.dumps(data).encode('utf-8')
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def raise_for_status(self): pass
            def iter_content(self, size): yield self.data
        with patch('database_update.requests.get', side_effect=[Reply({'sha': revision}), Reply(self.idols), Reply(self.songs)]) as get:
            pack = db.download_databases()
            self.assertEqual(pack['revision'], revision)
            for call in get.call_args_list[1:]:
                self.assertIn('/' + revision + '/idol_names/', call.args[0])
        with patch('database_update.requests.get') as get:
            with self.assertRaises(InterruptedError):
                db.download_databases(lambda: True)
            get.assert_not_called()

    def test_immediate_ui_reload_preserves_input_and_ignores_old_song_cache(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.checkenv') as folder:
            root = Path(folder)
            settings = QSettings(str(root / 'settings.ini'), QSettings.Format.IniFormat)
            with patch.dict(os.environ, {'YTDL_DATA_DIR': str(root)}), patch.object(ytdl, 'QSettings', lambda *args: settings):
                window = ytdl.YoutubeDownloader()
                try:
                    window.group_edit.setText('Baby DONT Cry')
                    window.idol_edit.setText('Yihyun')
                    window.search_date_edit.setText('261001')
                    window.selected_idol_id = 'babydontcry:yihyun'
                    old = copy.deepcopy(self.songs['groups']['Baby DONT Cry'])
                    old['songs'] = []
                    window.song_catalogue.save_group('Baby DONT Cry', old)
                    with patch.object(ytdl.QMessageBox, 'information'):
                        window.database_update_ready(self.pack)
                    self.assertEqual(window.search_date_edit.text(), '261001')
                    self.assertEqual(window.idol_edit.text(), 'Yihyun')
                    self.assertEqual(window.selected_idol_id, 'babydontcry:yihyun')
                    self.assertIn('Jo Yihyun · Baby DONT Cry', window.member_completion_ids)
                    self.assertIn('Jo Yihyun · Baby DONT Cry', window.member_model.stringList())
                    window.refresh_song_candidates(force=True, all_songs=True)
                    self.assertIn('Bittersweet', window.song_model.stringList())
                    before = window.database_data
                    corrupt = copy.deepcopy(self.pack)
                    corrupt['idols']['schema_version'] = 999
                    with patch.object(ytdl.QMessageBox, 'warning') as warning:
                        window.database_update_ready(corrupt)
                        warning.assert_called_once()
                    self.assertIs(window.database_data, before)
                    window.show_database_menu()
                    self.assertTrue(window.database_menu.isVisible())
                    window.show_database_menu()
                    self.assertFalse(window.database_menu.isVisible())
                finally:
                    window.close()
                    self.app.processEvents()
                reopened = ytdl.YoutubeDownloader()
                self.assertEqual(reopened.idol_catalogue.resolve_group('babydontcry')['name'], 'Baby DONT Cry')
                self.assertEqual(len(reopened.song_catalogue.songs('Baby DONT Cry')), 8)
                reopened.close()
                self.app.processEvents()

    def test_threaded_import_loading_and_error_cleanup(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.checkenv') as folder:
            root = Path(folder)
            settings = QSettings(str(root / 'settings.ini'), QSettings.Format.IniFormat)
            with patch.dict(os.environ, {'YTDL_DATA_DIR': str(root)}), patch.object(ytdl, 'QSettings', lambda *args: settings):
                window = ytdl.YoutubeDownloader()
                try:
                    with patch.object(ytdl.QMessageBox, 'information') as success:
                        window.start_database_update(path=str(ROOT / 'idol_names/idol_aliases.json'))
                        self.assertFalse(window.database_btn.isEnabled())
                        self.assertTrue(window.database_spinner.timer.isActive())
                        for _ in range(100):
                            QTest.qWait(20)
                            if window.database_worker is None:
                                break
                        self.assertIsNone(window.database_worker)
                        self.assertTrue(window.database_btn.isEnabled())
                        self.assertFalse(window.database_spinner.timer.isActive())
                        success.assert_called_once()
                    before = window.database_data
                    with patch.object(ytdl.QMessageBox, 'warning') as failure:
                        window.start_database_update(path=str(root / 'missing.json'))
                        for _ in range(100):
                            QTest.qWait(20)
                            if window.database_worker is None:
                                break
                        self.assertIsNone(window.database_worker)
                        self.assertTrue(window.database_btn.isEnabled())
                        self.assertIs(window.database_data, before)
                        failure.assert_called_once()
                finally:
                    window.close()
                    self.app.processEvents()


if __name__ == '__main__':
    unittest.main()
