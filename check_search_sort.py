"""Offline sorting, selection and diagnostics regression checks."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PyQt6.QtCore import QSettings, Qt, QPoint
from PyQt6.QtWidgets import QApplication, QLabel
from PyQt6.QtTest import QTest
import ytdl


def sample(video_id, exact, short, date=None, duration=None):
    return {'id': video_id, 'title': video_id, '_score': (exact, 1, 1),
            '_is_short': short, 'upload_date': date, 'duration': duration,
            'webpage_url': 'https://www.youtube.com/' + ('shorts/' if short else 'watch?v=') + video_id}


class Sorting(unittest.TestCase):
    def setUp(self):
        self.entries = [sample('similar', False, False, '20261003', 900),
                        sample('short', True, True, '20261002', 40),
                        sample('long_old', True, False, '20260919', 180),
                        sample('long_new', True, False, '20261001', 240),
                        sample('unknown', True, False)]

    def ids(self, mode):
        return [e['id'] for e in ytdl.sorted_search_entries(self.entries, mode)]

    def test_tiers(self):
        for mode in ('match', 'newest', 'oldest', 'longest', 'shortest'):
            ids = self.ids(mode)
            self.assertEqual(ids[-2:], ['short', 'similar'])

    def test_date_order_and_unknown(self):
        self.assertEqual(self.ids('newest')[:3], ['long_new', 'long_old', 'unknown'])
        self.assertEqual(self.ids('oldest')[:3], ['long_old', 'long_new', 'unknown'])

    def test_duration_order_and_unknown(self):
        self.assertEqual(self.ids('longest')[:3], ['long_new', 'long_old', 'unknown'])
        self.assertEqual(self.ids('shortest')[:3], ['long_old', 'long_new', 'unknown'])

    def test_timestamp_and_url_short(self):
        old = sample('old', True, False, '20260919', 180)
        new = sample('new', True, False, duration=200)
        new['timestamp'] = 1790899200
        short = sample('s', True, False, '20261003', 50)
        short['webpage_url'] = 'https://www.youtube.com/shorts/AAAAAAAAAAA'
        self.assertEqual([e['id'] for e in ytdl.sorted_search_entries([old, short, new], 'newest')], ['new', 'old', 's'])

    def test_ui_selection_popup_and_diagnostics(self):
        app = QApplication.instance() or QApplication([])
        self.__class__._app = app
        with tempfile.TemporaryDirectory(dir='.checkenv') as folder:
            settings = QSettings(str(Path(folder) / 'settings.ini'), QSettings.Format.IniFormat)
            with patch.object(ytdl, 'QSettings', lambda *args: settings):
                window = ytdl.YoutubeDownloader()
            window.request_search_thumbnail = lambda entry: None
            window.search_entries = self.entries
            window.selected_search_ids = {'long_old'}
            window.show()
            self.assertTrue(window.search_card.isHidden())
            self.assertEqual(window.duplicate_indicator.text(), '✔')
            QTest.mouseClick(window.search_disclosure_btn, Qt.MouseButton.LeftButton)
            self.assertFalse(window.search_card.isHidden())
            window.song_edit.setText('WE GO')
            QTest.mouseClick(window.search_disclosure_arrow, Qt.MouseButton.LeftButton)
            self.assertTrue(window.search_card.isHidden())
            self.assertEqual(window.song_edit.text(), 'WE GO')
            QTest.mouseClick(window.search_disclosure_arrow, Qt.MouseButton.LeftButton)
            self.assertFalse(window.search_card.isHidden())
            window.render_search_results()
            with patch.object(window, 'duplicate_tooltip', return_value='Already downloaded'):
                window.render_search_results()
                badges = [label for label in window.results_list.findChildren(QLabel)
                          if label.toolTip() == 'Already downloaded']
                self.assertEqual(len(badges), len(self.entries))
                self.assertTrue(all(label.text() == '✔' for label in badges))
            window.results_sort_combo.setCurrentIndex(1)
            self.assertEqual(window.selected_search_ids, {'long_old'})
            self.assertTrue(window.search_checks['long_old'].isChecked())
            self.assertEqual(list(window.search_checks), self.ids('newest'))
            selected_card = window.search_checks['long_old'].parentWidget()
            self.assertTrue(selected_card.property('chosen'))
            window.search_checks['long_old'].setChecked(False)
            self.assertFalse(selected_card.property('chosen'))
            window.search_checks['long_old'].setChecked(True)
            window.render_search_results()
            self.assertTrue(window.search_checks['long_old'].parentWidget().property('chosen'))
            window.search_diagnostics(['PRIVATE DIAGNOSTIC LOG'])
            self.assertEqual(window.results_status.toolTip(), '')
            self.assertNotIn('PRIVATE', window.search_error_btn.toolTip())
            self.assertFalse(window.search_error_btn.isHidden())
            window.show_search_results()
            QTest.qWait(20)
            combo = window.results_sort_combo
            QTest.mouseClick(combo.arrow_button, Qt.MouseButton.LeftButton)
            QTest.qWait(20)
            self.assertTrue(combo.popup_frame.isVisible())
            item = combo.popup_list.item(4)
            QTest.mouseClick(combo.popup_list.viewport(), Qt.MouseButton.LeftButton,
                             pos=combo.popup_list.visualItemRect(item).center())
            self.assertEqual(combo.currentData(), 'shortest')
            self.assertTrue(window.results_popup.isVisible())
            self.assertEqual(window.selected_search_ids, {'long_old'})
            for dark, color in ((False, '#eef0ff'), (True, '#343a4b')):
                window.dark_mode = dark
                window.apply_style(window.ui_scale)
                checkbox = window.search_checks['long_old']
                card = checkbox.parentWidget()
                checkbox.setChecked(False)
                QTest.mouseMove(card, QPoint(3, 3))
                app.processEvents()
                hover_color = card.grab().toImage().pixelColor(3, 3).name()
                checkbox.setChecked(True)
                QTest.mouseMove(window.results_close_btn)
                app.processEvents()
                selected_color = card.grab().toImage().pixelColor(3, 3).name()
                self.assertEqual(hover_color, color)
                self.assertEqual(selected_color, hover_color)
                checkbox.setChecked(False)
                app.processEvents()
                self.assertNotEqual(card.grab().toImage().pixelColor(3, 3).name(), selected_color)
            window.results_popup.hide()
            window.close()


if __name__ == '__main__':
    unittest.main()
