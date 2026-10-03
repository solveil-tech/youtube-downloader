"""Exercise actual clicks, stable cover geometry, diagnostics and local playback."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PyQt6.QtCore import QSettings, Qt, QUrl, QPoint, QPointF
from PyQt6.QtGui import QPixmap, QWheelEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QToolButton
from PyQt6.QtMultimedia import QMediaPlayer
import ytdl
from song_catalogue import SongCatalogue

app = QApplication.instance() or QApplication([])


class Checks(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(dir='.checkenv')
        self.settings = QSettings(str(Path(self.folder.name) / 'settings.ini'), QSettings.Format.IniFormat)
        db = SongCatalogue(Path(self.folder.name) / 'songs.json', 'idol_names/song_catalogue.json')
        self.patches = [patch.object(ytdl, 'QSettings', lambda *args: self.settings), patch.object(ytdl, 'SongCatalogue', lambda *args: db)]
        for p in self.patches:
            p.start()
        self.window = ytdl.YoutubeDownloader()
        self.window.show()
        QTest.qWait(100)

    def tearDown(self):
        self.window.close()
        for _ in range(80):
            QTest.qWait(50)
            if not self.window.isVisible():
                break
        for p in self.patches:
            p.stop()
        self.folder.cleanup()

    def test_one_click_member_clear_from_date(self):
        self.window.choose_search_member('fromis9:nagyung')
        self.window.search_date_edit.setFocus()
        QTest.qWait(400)
        button = next(b for b in self.window.idol_edit.findChildren(QToolButton) if b.isVisible())
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        QTest.qWait(200)
        self.assertEqual(self.window.idol_edit.text(), '')
        self.assertIsNone(self.window.selected_idol_id)
        self.assertFalse(self.window.member_completer.popup().isVisible())

    def test_cover_frame_does_not_resize(self):
        records = []
        for index, ratio in enumerate(((320, 180), (160, 120), (120, 160))):
            pixmap = QPixmap(*ratio)
            pixmap.fill(Qt.GlobalColor.blue)
            file = Path(self.folder.name) / f'cover{index}.png'
            pixmap.save(str(file))
            records.append({'info': {'title': 'long title ' * (20 if index else 1), 'uploader': 'author ' * (50 if index else 1)}, 'thumbnail': file.read_bytes()})
        self.window.batch_items = records
        self.window.cover_label.set_stack(records)
        QTest.qWait(100)
        frame = self.window.cover_frame.geometry()
        cover_size = self.window.cover_label.size()
        layer_size = self.window.cover_label.layer_rects[-1][1].size()
        for _ in range(6):
            label = self.window.cover_label
            event = QWheelEvent(QPointF(20, 20), QPointF(label.mapToGlobal(QPoint(20, 20))), QPoint(), QPoint(0, -120),
                                Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
            QApplication.sendEvent(label, event)
            QTest.qWait(40)
            self.assertEqual(self.window.cover_frame.geometry(), frame)
            self.assertEqual(label.size(), cover_size)
            self.assertEqual(label.layer_rects[-1][1].size(), layer_size)

    def test_partial_search_failure_has_reason(self):
        worker = ytdl.IdolSearchWorker({'queries': ['test'], 'short_queries': []})
        messages = []
        worker.diagnostics.connect(messages.append)
        def query(query, shorts):
            if shorts:
                raise TimeoutError('HTTP 403 Forbidden')
            return []
        with patch.object(worker, 'query', query):
            worker.run()
        self.assertTrue(messages[-1])
        self.assertIn('403', messages[-1][0])
        self.window.search_diagnostics(messages[-1])
        self.assertFalse(self.window.search_error_btn.isHidden())
        self.assertIn('403', self.window.search_error_btn.toolTip())

    def test_playback_and_default_player(self):
        root = Path(self.folder.name)
        ffmpeg = r'D:\ffmpeg-essentials\bin\ffmpeg.exe'
        video, audio = root / 'video.mp4', root / 'audio.m4a'
        subprocess.run([ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=160x90:r=30:d=4', '-an', '-c:v', 'libx264', str(video)], check=True)
        subprocess.run([ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=4', '-c:a', 'aac', str(audio)], check=True)
        formats = [{'url': QUrl.fromLocalFile(str(video.resolve())).toString(), 'protocol': 'https', 'height': 2160, 'fps': 60, 'ext': 'mp4', 'vcodec': 'h264', 'acodec': 'none'},
                   {'url': QUrl.fromLocalFile(str(audio.resolve())).toString(), 'protocol': 'https', 'vcodec': 'none', 'acodec': 'aac', 'abr': 128}]
        def fetch(url, cancelled=None):
            return {'title': url, 'formats': formats}, b''
        with patch.object(ytdl.InfoWorker, 'fetch', fetch):
            self.window.play_search_video('https://youtu.be/AAAAAAAAAAA')
            player = self.window.result_player
            player.output.setMuted(True)  # Automated playback checks must remain silent.
            for _ in range(80):
                QTest.qWait(40)
                if player.player.position() > 150 and player.audio_player.position() > 150:
                    break
            self.assertTrue(player.separate_audio)
            self.assertTrue(player.output.isMuted())
            self.assertGreater(player.player.position(), 0)
            self.assertGreater(player.audio_player.position(), 0)
            player.toggle_play()
            self.assertEqual(player.player.playbackState(), QMediaPlayer.PlaybackState.PausedState)
            self.assertEqual(player.audio_player.playbackState(), QMediaPlayer.PlaybackState.PausedState)
            player.seek.setValue(1000)
            player.seek_to_position()
            QTest.mouseClick(player.seek, Qt.MouseButton.LeftButton, pos=QPoint(player.seek.width() * 3 // 4, player.seek.height() // 2))
            self.assertGreater(player.seek.value(), player.seek.maximum() // 2)
            self.window.play_search_video('https://youtu.be/BBBBBBBBBBB')
            self.assertIs(self.window.result_player, player)
            QTest.qWait(200)
            self.assertEqual(player.current_url, 'https://youtu.be/BBBBBBBBBBB')
            player.close()
            QTest.qWait(100)
        manager = ytdl.DownloadManager('https://youtu.be/AAAAAAAAAAA', '137', video, 'mp4', False)
        manager.state = 'finished'
        card = ytdl.DownloadTaskWidget(manager, b'')
        calls = []
        with patch.object(ytdl.QDesktopServices, 'openUrl', lambda url: calls.append(url.toLocalFile())):
            card.play_file_btn.click()
        self.assertEqual([Path(path).resolve() for path in calls], [video.resolve()])
        manager.deleteLater()
        card.deleteLater()


if __name__ == '__main__':
    unittest.main(verbosity=2)
