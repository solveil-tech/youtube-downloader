"""Real local media fixtures: do not download or modify user media."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import subprocess
import tempfile
import unittest
from pathlib import Path
from download_check import inspect_download, check_audio_packets

FFMPEG = r'D:\ffmpeg-essentials\bin\ffmpeg.exe'
PROBE = r'D:\ffmpeg-essentials\bin\ffprobe.exe'


class Checks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(dir='.checkenv')
        cls.good = Path(cls.folder.name) / 'good.mp4'
        cls.cut_audio = Path(cls.folder.name) / 'cut-audio.mp4'
        for path, audio_duration in ((cls.good, 10), (cls.cut_audio, 3)):
            subprocess.run([FFMPEG, '-v', 'error', '-f', 'lavfi', '-i', 'color=c=black:s=160x90:r=10:d=10',
                            '-f', 'lavfi', '-i', f'sine=frequency=440:duration={audio_duration}',
                            '-c:v', 'libx264', '-c:a', 'aac', '-y', str(path)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_good(self):
        self.assertEqual(inspect_download(self.good, PROBE, FFMPEG, 10), [])

    def test_incomplete_audio(self):
        issues = inspect_download(self.cut_audio, PROBE, FFMPEG, 10)
        codes = {code for code, _ in issues}
        self.assertIn('av_mismatch', codes)
        self.assertIn('audio_coverage', codes)
        self.assertTrue(self.cut_audio.exists())

    def test_missing_and_duration(self):
        self.assertEqual(inspect_download(Path(self.folder.name) / 'absent.mp4', PROBE)[0][0], 'missing_file')
        self.assertIn('duration_mismatch', {c for c, _ in inspect_download(self.good, PROBE, FFMPEG, 20)})

    def test_audio_gap(self):
        self.assertIn('audio_gap', {c for c, _ in check_audio_packets('0,0.1\n0.1,0.1\n5,0.1', 5.1)})

    def test_task_and_translation(self):
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtTest import QTest
        import ytdl
        app = QApplication.instance() or QApplication([])
        manager = ytdl.DownloadManager('https://youtu.be/AAAAAAAAAAA', '137+140', self.cut_audio, 'mp4', False)
        manager.expected_duration = 10
        card = ytdl.DownloadTaskWidget(manager, b'')
        manager.process_finished(0, None)
        self.assertEqual(manager.state, 'checking')
        for _ in range(150):
            QTest.qWait(40)
            if manager.check_worker is None:
                break
        self.assertEqual(manager.state, 'finished')
        self.assertTrue(manager.check_issues)
        self.assertTrue(card.property('checkWarning'))
        previous = ytdl.CURRENT_LANGUAGE
        ytdl.CURRENT_LANGUAGE = 'en'
        card.retranslate_ui()
        self.assertIn('inspection warning', card.detail_label.text())
        self.assertTrue(self.cut_audio.exists())
        ytdl.CURRENT_LANGUAGE = previous
        manager.deleteLater()
        card.deleteLater()
        app.processEvents()


if __name__ == '__main__':
    unittest.main(verbosity=2)
