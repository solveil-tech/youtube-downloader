"""Offline regression checks for song filters and verified deep-search dates."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from idol_search import IdolCatalogue, make_search_plan, rank_results, matches_song, normalize
from song_catalogue import SongCatalogue, base_track_title


class SearchExtensions(unittest.TestCase):
    def setUp(self):
        self.catalogue = IdolCatalogue('idol_names/idol_aliases.json')
        self.member = self.catalogue.by_id['fromis9:nagyung']
        self.group = self.catalogue.resolve_group('fro')

    def plan(self, **kwargs):
        kwargs.setdefault('deep_mode', 'member')
        return make_search_plan(self.member, self.group, 'nagyung', '260919', self.catalogue, **kwargs)

    def entry(self, title, date='20260920', verified=True, key='AAAAAAAAAAA'):
        return {'id': key, 'title': title, 'publish_date': date, '_publish_verified': verified}

    def test_song_is_hard_filter(self):
        p = self.plan(song='WE GO')
        self.assertEqual(len(rank_results([self.entry('260919 nagyung WEGO')], p)), 1)
        for title in ('260919 nagyung DM', '260919 nagyung WE MUSIC GO', '260919 nagyung SWE GOES'):
            self.assertEqual(rank_results([self.entry(title)], p), [])
        self.assertTrue(matches_song('nagyung Love Bomb fancam', 'LOVE BOMB'))

    def test_deep_window_verified_only(self):
        p = self.plan(deep=True, deep_mode='member')
        for day in ('20260919', '20260920', '20261003'):
            self.assertEqual(len(rank_results([self.entry('nagyung fancam', day)], p)), 1)
        for day in ('20260918', '20261004', '', '2026092'):
            self.assertEqual(rank_results([self.entry('nagyung fancam', day)], p), [])
        self.assertEqual(rank_results([self.entry('nagyung fancam', verified=False)], p), [])
        self.assertEqual(len(rank_results([self.entry('nagyung fancam', verified=False)], p, allow_unverified=True)), 1)
        self.assertEqual(rank_results([self.entry('nagyderence fancam')], p), [])
        self.assertEqual(rank_results([self.entry('김나경 nagyung fancam')], p), [])

    def test_modes_and_order(self):
        both = self.plan(deep=True, deep_mode='both')
        self.assertEqual(rank_results([self.entry('nagyung fancam')], both), [])
        self.assertEqual(len(rank_results([self.entry('fromis9 nagyung fancam')], both)), 1)
        group = self.plan(deep=True, deep_mode='group')
        self.assertEqual(len(rank_results([self.entry('fromis_9 WE GO')], group)), 1)
        ordinary = self.entry('nagyung 260919', key='BBBBBBBBBBB')
        self.assertEqual(rank_results([ordinary], both), [])
        self.assertEqual(len(rank_results([ordinary], self.plan())), 1)
        ordinary = self.entry('fromis_9 nagyung 260919', key='BBBBBBBBBBB')
        ranked = rank_results([self.entry('fromis9 nagyung fancam'), ordinary, ordinary], both)
        self.assertEqual([e['id'] for e in ranked], ['BBBBBBBBBBB', 'AAAAAAAAAAA'])
        self.assertFalse(ranked[0]['_deep_result'])
        self.assertTrue(ranked[1]['_deep_result'])
        song = self.plan(deep=True, deep_mode='group', song='DM')
        self.assertEqual(rank_results([self.entry('fromis9 WE GO')], song), [])

    def test_date_and_identity_are_independent(self):
        titles = ('fromis9 260919 fancam', 'nagyung 260919 fancam', 'fromis9 nagyung 260919 fancam')
        for deep in (False, True):
            for mode, expected in (('group', (True, False, True)), ('member', (False, True, True)), ('both', (False, False, True))):
                plan = self.plan(deep=deep, deep_mode=mode)
                for title, accepted in zip(titles, expected):
                    # Exact title date does not depend on upload-date verification.
                    results = rank_results([self.entry(title, verified=False)], plan)
                    self.assertEqual(bool(results), accepted, (mode, deep, title))
                    if results:
                        self.assertFalse(results[0]['_deep_result'])
                no_date = self.entry('fromis9 nagyung fancam')
                self.assertEqual(bool(rank_results([no_date], plan)), deep)
                self.assertEqual(rank_results([self.entry('fromis9 nagyung fancam', '20261004')], plan), [])
        group_plan = self.plan(deep=True, deep_mode='group')
        self.assertTrue(any('fromis' in query for query in group_plan['queries']))
        self.assertTrue(all('nagyung' not in query for query in group_plan['queries']))

    def test_song_versions(self):
        for title in ('DM (Remix)', 'WE GO (Instrumental)', 'Love Bomb (Sped Up)', 'TANK (Inst.)', 'DICE [Inst.]', 'Blue Valentine (A Cappella Ver.)'):
            self.assertIsNone(base_track_title(title))
        self.assertEqual(base_track_title('DM (English Ver.)'), 'DM')
        self.assertEqual(base_track_title('Feel Good (SECRET CODE)'), 'Feel Good (SECRET CODE)')

    def test_verified_artist_does_not_use_ambiguous_search(self):
        from song_catalogue import fetch_group_songs, VERIFIED_ARTISTS
        for name in ('STAYC', 'ITZY'):
            artist_id = VERIFIED_ARTISTS[name.lower()]
            replies = [[{'artistId': artist_id, 'artistName': name}],
                       [{'wrapperType': 'collection', 'collectionId': 1,
                         'artistId': artist_id, 'releaseDate': '2020-01-01'}],
                       [{'kind': 'song', 'artistId': artist_id, 'trackName': 'Test Song'}]]
            with patch('song_catalogue.catalogue_request', side_effect=replies) as request:
                result = fetch_group_songs(self.catalogue.resolve_group(name))
                self.assertEqual(result['artist_id'], artist_id)
                self.assertEqual(request.call_args_list[0].args[0], '/lookup')
                self.assertEqual(result['songs'][0]['title'], 'Test Song')

    def test_local_catalogue_covers_registered_groups(self):
        db = SongCatalogue('idol_names/song_catalogue.json')
        for group in self.catalogue.groups:
            songs = db.songs(group['name'])
            self.assertTrue(songs, group['name'])
            self.assertEqual(len({normalize(s['title']) for s in songs}), len(songs))
            self.assertTrue(all(s.get('sources') for s in songs))

    def test_worker_verifies_date_before_publishing(self):
        from PyQt6.QtCore import QCoreApplication
        import ytdl
        app = QCoreApplication.instance() or QCoreApplication([])
        plan = self.plan(deep=True, deep_mode='member')
        plan['queries'], plan['short_queries'], plan['deep_queries'] = [], [], ['nagyung']
        worker = ytdl.IdolSearchWorker(plan)
        emitted = []
        worker.results.connect(emitted.append)
        entry = {'id': 'AAAAAAAAAAA', 'title': 'nagyung fancam'}
        verified = {**entry, 'upload_date': '20260920', 'publish_date': '20260920', '_publish_verified': True,
                    'uploader': 'Test', 'duration': 10, '_metadata_complete': True}
        with patch.object(worker, 'query', lambda *args: [entry]), patch.object(ytdl, 'complete_short_metadata', lambda *args: verified):
            worker.run()
        self.assertEqual(len(emitted[-1]), 1)
        self.assertTrue(emitted[-1][0]['_deep_result'])
        emitted.clear()
        with patch.object(worker, 'query', lambda *args: [entry]), patch.object(ytdl, 'complete_short_metadata', side_effect=ValueError('No date')):
            worker.run()
        self.assertEqual(emitted[-1], [])

    def test_ui_member_survives_group_deletion(self):
        from PyQt6.QtCore import QSettings
        from PyQt6.QtTest import QTest
        from PyQt6.QtWidgets import QApplication
        import ytdl
        app = QApplication.instance() or QApplication([])
        self.__class__._qt_app = app
        with tempfile.TemporaryDirectory(dir='.checkenv') as folder:
            settings = QSettings(str(Path(folder) / 'settings.ini'), QSettings.Format.IniFormat)
            db = SongCatalogue(Path(folder) / 'songs.json')
            db.groups['fromis_9'] = {'songs': [{'title': 'WE GO', 'aliases': []}]}
            with patch.object(ytdl, 'QSettings', lambda *args: settings), patch.object(ytdl, 'SongCatalogue', lambda *args: db):
                window = ytdl.YoutubeDownloader()
                window.start_library_scan = lambda *args, **kwargs: None
                window.choose_search_member('fromis9:nagyung')
                window.group_edit.clear()
                window.search_group_edited('')
                self.assertEqual(window.selected_idol_id, 'fromis9:nagyung')
                window.song_edit.setText('WE GO')
                window.search_date_edit.setText('260919')
                plans = []
                def offline_start(worker):
                    plans.append(worker.plan)
                with patch.object(ytdl.IdolSearchWorker, 'start', offline_start):
                    window.start_idol_search()
                self.assertTrue(plans)
                self.assertEqual(plans[0]['group_names'], [])
                self.assertFalse(plans[0]['keyword_filters']['group'])
                self.assertEqual(plans[0]['song_names'], ['WE GO'])
                self.assertEqual(window.group_edit.text(), '')
                worker, window.search_worker = window.search_worker, None
                worker.deleteLater()
                # Song + member works without a date and without an implicit group.
                window.search_date_edit.clear()
                with patch.object(ytdl.IdolSearchWorker, 'start', offline_start):
                    window.start_idol_search()
                self.assertEqual(plans[-1]['dates'], [])
                self.assertEqual(plans[-1]['group_names'], [])
                worker, window.search_worker = window.search_worker, None
                worker.deleteLater()
                window.clear_search_inputs()
                self.assertFalse(window.song_edit.text())
                # Song + date does not require selecting an idol or a group.
                window.song_edit.setText('DM')
                window.search_date_edit.setText('260919')
                with patch.object(ytdl.IdolSearchWorker, 'start', offline_start):
                    window.start_idol_search()
                self.assertIsNone(plans[-1]['member_id'])
                self.assertEqual(plans[-1]['group_names'], [])
                worker, window.search_worker = window.search_worker, None
                worker.deleteLater()
                window.close()
                QTest.qWait(500)

    def test_song_popup_mouse_keyboard_and_clear(self):
        from PyQt6.QtCore import QSettings, Qt
        from PyQt6.QtTest import QTest
        from PyQt6.QtWidgets import QApplication
        import ytdl
        app = QApplication.instance() or QApplication([])
        self.__class__._qt_app = app
        with tempfile.TemporaryDirectory(dir='.checkenv') as folder:
            settings = QSettings(str(Path(folder) / 'settings.ini'), QSettings.Format.IniFormat)
            db = SongCatalogue(Path(folder) / 'songs.json')
            result = {'songs': [{'title': 'DM', 'aliases': []}, {'title': 'WE GO', 'aliases': []}]}
            db.groups['fromis_9'] = result
            with patch.object(ytdl, 'QSettings', lambda *args: settings), patch.object(ytdl, 'SongCatalogue', lambda *args: db):
                window = ytdl.YoutubeDownloader()
                window.show()
                window.toggle_kpop_search()
                window.group_edit.setText('fromis_9')
                QTest.qWait(400)
                popup = window.song_completer.popup()
                QTest.mouseClick(window.song_edit, Qt.MouseButton.LeftButton)
                QTest.qWait(100)
                self.assertFalse(popup.isVisible(), 'Focusing song input must not force a modal popup')
                QTest.mouseClick(window.song_list_button, Qt.MouseButton.LeftButton)
                QTest.qWait(100)
                self.assertTrue(popup.isVisible())
                QTest.mouseClick(window.song_list_button, Qt.MouseButton.LeftButton)
                QTest.qWait(100)
                self.assertFalse(popup.isVisible(), 'Second arrow click reopened list')
                QTest.mouseClick(window.song_list_button, Qt.MouseButton.LeftButton)
                QTest.qWait(60)
                index = popup.model().index(0, 0)
                QTest.mouseClick(popup.viewport(), Qt.MouseButton.LeftButton, pos=popup.visualRect(index).center())
                QTest.qWait(150)
                self.assertEqual(window.song_edit.text(), 'DM')
                self.assertFalse(popup.isVisible(), 'Selection reopened list on focus restoration')
                QTest.mouseClick(window.song_list_button, Qt.MouseButton.LeftButton)
                QTest.qWait(60)
                self.assertEqual(popup.model().rowCount(), 2, 'Arrow must show full list even after selection')
                QTest.keyClick(popup, Qt.Key.Key_Escape)
                QTest.qWait(100)
                self.assertFalse(popup.isVisible(), 'Escape reopened list')
                window.song_edit.clear()
                window.song_edit.setFocus()
                QTest.keyClicks(window.song_edit, 'custom song')
                QTest.qWait(100)
                self.assertEqual(window.song_edit.text(), 'custom song')
                self.assertFalse(popup.isVisible())
                window.song_catalogue_ready('fromis_9', result)
                QTest.qWait(100)
                self.assertFalse(popup.isVisible(), 'Background refresh stole focus')
                window.group_edit.clear()
                window.song_edit.clear()
                window.song_edit.setFocus()
                QTest.keyClicks(window.song_edit, 'we')
                QTest.qWait(100)
                self.assertIn('WE GO · fromis_9', window.song_model.stringList())
                self.assertTrue(popup.isVisible())
                window.choose_search_song('WE GO · fromis_9')
                self.assertEqual(window.song_edit.text(), 'WE GO')
                self.assertEqual(window.group_edit.text(), 'fromis_9')
                self.assertFalse(popup.isVisible())
                mock_worker = Mock()
                mock_worker.isInterruptionRequested.return_value = False
                mock_worker.requestInterruption.side_effect = lambda: setattr(mock_worker.isInterruptionRequested, 'return_value', True)
                with patch.object(ytdl, 'SongCatalogueWorker', return_value=mock_worker) as factory:
                    with patch.object(ytdl.requests, 'get', side_effect=AssertionError('Local catalogue must not use network')):
                        QTest.mouseClick(window.song_refresh_button, Qt.MouseButton.LeftButton)
                    factory.assert_not_called()
                    self.assertFalse(window.song_loading_spinner.timer.isActive())
                    window.group_edit.setText('ITZY')
                    window.refresh_song_candidates()
                    factory.assert_not_called()
                    self.assertFalse(window.song_loading_spinner.timer.isActive())
                    self.assertFalse(window.song_loading_spinner.timer.isActive())
                    self.assertFalse(window.song_loading_spinner.isVisible())
                window.group_edit.setText('fromis_9')
                window.deep_menu.popup(window.deep_btn.mapToGlobal(window.deep_btn.rect().bottomLeft()))
                QTest.qWait(50)
                QTest.mouseClick(window.keyword_actions['group'], Qt.MouseButton.LeftButton)
                self.assertFalse(window.keyword_actions['group'].isChecked())
                self.assertTrue(window.deep_menu.isVisible(), 'Choosing an option closed settings')
                QTest.mouseClick(window.keyword_actions['song'], Qt.MouseButton.LeftButton)
                self.assertFalse(window.keyword_actions['song'].isChecked())
                self.assertTrue(window.deep_menu.isVisible())
                QTest.mouseClick(window.search_date_edit, Qt.MouseButton.LeftButton)
                QTest.qWait(50)
                self.assertFalse(window.deep_menu.isVisible(), 'Outside click did not close settings')
                window.song_edit.clear()
                QTest.mouseClick(window.song_list_button, Qt.MouseButton.LeftButton)
                QTest.qWait(60)
                self.assertTrue(popup.isVisible())
                QTest.mouseClick(window.search_date_edit, Qt.MouseButton.LeftButton)
                QTest.qWait(100)
                self.assertFalse(popup.isVisible(), 'Outside click did not dismiss list')
                QTest.mouseClick(window.song_list_button, Qt.MouseButton.LeftButton)
                QTest.qWait(60)
                window.idol_edit.setText('nagyung')
                window.search_date_edit.setText('260919')
                QTest.mouseClick(window.search_clear_btn, Qt.MouseButton.LeftButton)
                QTest.qWait(200)
                self.assertTrue(all(not edit.text() for edit in (window.group_edit, window.song_edit, window.idol_edit, window.search_date_edit)))
                self.assertFalse(popup.isVisible(), 'Clear reopened list')
                window.close()
                QTest.qWait(500)


if __name__ == '__main__':
    unittest.main(verbosity=2)
