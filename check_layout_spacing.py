import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
from tempfile import TemporaryDirectory
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest
import ytdl

app = QApplication([])
app.setStyle('Fusion')
with TemporaryDirectory(dir=Path(__file__).parent / '.checkenv') as folder:
    settings = QSettings(str(Path(folder) / 'settings.ini'), QSettings.Format.IniFormat)
    ytdl.QSettings = lambda *args: settings
    window = ytdl.YoutubeDownloader()
    window.start_library_scan = lambda *args, **kwargs: None
    window.show()
    window.clip_panel.show()
    for language in ('zh', 'en', 'de', 'ar'):
        window.set_language(language)
        for width, height in ((860, 700), (1020, 830), (1180, 960)):
            window.resize(width, height)
            QTest.qWait(80)
            window.range_label.setText('00:01.234 → 03:45.678')
            app.processEvents()
            gaps = (window.audio_combo.y() - window.range_label.geometry().bottom(),
                    window.download_btn.y() - window.audio_combo.geometry().bottom())
            print(language, window.size(), 'gaps', gaps)
            print('options', window.right_layout.parentWidget().geometry(), 'bottom', window.clip_panel.geometry(), 'download', window.download_btn.geometry())
            assert window.right_layout.parentWidget().geometry().bottom() + 4 < window.clip_panel.geometry().top(), 'Options overlap clip panel'
            assert min(gaps) >= 4, gaps
            assert window.download_btn.geometry().bottom() < window.download_btn.parentWidget().height()
            assert max(e.width() for e in (window.group_edit, window.idol_edit, window.search_date_edit)) - min(e.width() for e in (window.group_edit, window.idol_edit, window.search_date_edit)) <= 1
            assert window.search_btn.width() > window.search_clear_btn.width()
            row = window.search_card.layout()
            assert row.indexOf(window.search_btn) + 1 == row.indexOf(window.search_clear_btn)
    window.set_language('zh')
    window.resize(860, 700)
    QTest.qWait(80)
    window.grab().save(str(Path(__file__).parent / '.checkenv/layout-spacing.png'))
    window.close()
print('LAYOUT_SPACING_OK')
