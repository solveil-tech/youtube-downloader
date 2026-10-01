"""Batch ownership, queue limits, cover selection and preview audio regression."""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import tempfile
import time
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch
from PyQt6.QtCore import QBuffer, QIODevice, QSettings, Qt
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton
import ytdl

app = QApplication([])
app.setStyle("Fusion")


def thumbnail(color):
    pixmap = QPixmap(320, 180)
    pixmap.fill(QColor(color))
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    return bytes(buffer.data())


def video(index):
    return {"id": f"{index:011d}", "title": "Same title" if index < 2 else f"Video {index}",
            "duration": 10, "uploader": "Channel", "formats": [
        {"format_id": "v", "url": "https://example.org/video", "protocol": "https", "vcodec": "avc1", "acodec": "none", "ext": "mp4", "height": 2160, "width": 3840, "fps": 60, "filesize": 1000},
        {"format_id": "a", "url": "https://example.org/audio", "protocol": "https", "vcodec": "none", "acodec": "mp4a.40.2", "ext": "m4a", "abr": 128, "filesize": 100}]}


with tempfile.TemporaryDirectory(dir=Path(__file__).parent / ".checkenv") as directory:
    isolated = QSettings(str(Path(directory) / "settings.ini"), QSettings.Format.IniFormat)
    ytdl.QSettings = lambda *args: isolated
    window = ytdl.YoutubeDownloader()
    window.start_library_scan = lambda *args, **kwargs: None
    window.request_search_thumbnail = lambda *args: None
    window.show()
    app.processEvents()
    assert window.clip_video.toolTip() == "", "Preview hover tooltip should be disabled"
    formats = [dict(video(0)["formats"][0], format_id=str(height), height=height,
                    acodec="mp4a.40.2" if height == 360 else "none")
               for height in (360, 720, 1080, 2160)]
    assert ytdl.select_preview_format({"formats": formats})["height"] == 720
    assert ytdl.select_preview_format({"formats": formats[:2]})["height"] == 720
    assert ytdl.select_preview_format({"formats": formats[:1]})["height"] == 360
    package = ytdl.preview_package({"formats": formats + [video(0)["formats"][1]]})
    assert package["selector"] == "720+a", "720p preview must keep audio"
    cover_info = {"thumbnail": "https://example.org/low.jpg", "thumbnails": [
        {"url": "https://example.org/low.jpg", "width": 320, "height": 180},
        {"url": "https://example.org/high.jpg", "width": 1920, "height": 1080},
        {"url": "https://example.org/mid.jpg", "width": 1280, "height": 720}]}
    assert ytdl.cover_thumbnail_urls(cover_info)[0] == "https://example.org/high.jpg"
    from unittest.mock import Mock
    def image_bytes(width, height):
        image = ytdl.QImage(width, height, ytdl.QImage.Format.Format_RGB32)
        image.fill(QColor("#5986b3"))
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        return bytes(buffer.data())
    # Reported metadata may exaggerate size; use actual image pixels.
    cover_info["thumbnail"] = "https://example.org/unreported.jpg"
    image_data = {"https://example.org/high.jpg": image_bytes(320, 180),
                  "https://example.org/mid.jpg": image_bytes(1280, 720),
                  "https://example.org/low.jpg": image_bytes(120, 90),
                  "https://example.org/unreported.jpg": image_bytes(1920, 1080)}
    with patch.object(ytdl.requests, "get", side_effect=lambda url, **kwargs: Mock(content=image_data[url])):
        best = ytdl.fetch_best_cover(cover_info)
    assert ytdl.QImage.fromData(best).size() == ytdl.QSize(1920, 1080)
    entries = [{"id": f"{i:011d}", "title": f"Search {i}", "webpage_url": f"https://youtu.be/{i:011d}",
                "upload_date": "20260919", "duration": 10} for i in range(12)]
    window.search_entries = entries
    window.render_search_results()
    first_card = window.results_list.itemWidget(window.results_list.item(0))
    first_check = window.search_checks[entries[0]["id"]]
    QTest.mouseClick(first_card, Qt.MouseButton.LeftButton, pos=ytdl.QPoint(4, 4))
    assert first_check.isChecked(), "Clicking card background did not select result"
    title_label = next(label for label in first_card.findChildren(QLabel) if label.text() == "Search 0")
    QTest.mouseClick(title_label, Qt.MouseButton.LeftButton)
    assert not first_check.isChecked(), "Clicking card title did not toggle result"
    thumb_label = window.thumbnail_labels[entries[0]["id"]]
    QTest.mouseClick(thumb_label, Qt.MouseButton.LeftButton)
    assert first_check.isChecked(), "Clicking thumbnail did not select result"
    assert any("2026-09-19" in label.text() and "≈" not in label.text() for label in first_card.findChildren(QLabel))
    icons = [button for button in first_card.findChildren(QPushButton) if button.objectName() == "taskIcon"]
    assert len(icons) == 2
    icons[0].click()
    assert QApplication.clipboard().text() == entries[0]["webpage_url"]
    assert first_check.isChecked(), "Copy action changed selection"
    with patch.object(ytdl.QDesktopServices, "openUrl", return_value=True) as browser:
        icons[1].click()
        assert browser.call_args.args[0].toString() == entries[0]["webpage_url"]
    window.select_all_search_results(True)
    window.render_search_results()
    assert len(window.selected_search_ids) == 12 and all(box.isChecked() for box in window.search_checks.values())
    data = [thumbnail("#c7647c"), thumbnail("#5986b3")]
    fetch = lambda url, cancelled=None: (video(int(url.rsplit("/", 1)[-1])), data[int(url[-1]) % 2])
    with patch.object(ytdl.InfoWorker, "fetch", side_effect=fetch):
        window.parse_selected_results()
        deadline = time.monotonic() + 5
        while window.batch_worker is not None and time.monotonic() < deadline:
            QTest.qWait(10)
    assert window.batch_worker is None and len(window.batch_items) == 12
    assert window.download_btn.isEnabled() and not window.range_combo.isEnabled()
    app.processEvents()
    window.cover_label.grab()
    old_order = [item["url"] for item in window.batch_items]
    back_index, back_rect = window.cover_label.layer_rects[0]
    exposed = back_rect.bottomRight().toPoint()
    exposed.setX(exposed.x() - 3)
    exposed.setY(exposed.y() - 3)
    QTest.mouseClick(window.cover_label, Qt.MouseButton.LeftButton, pos=exposed)
    app.processEvents()
    assert window.cover_label.stack_order[0] == back_index
    front_rect = window.cover_label.layer_rects[-1][1]
    next_rect = window.cover_label.layer_rects[-2][1]
    assert next_rect.x() - front_rect.x() >= 18, "Cover hit area is too narrow"
    class Wheel:
        def angleDelta(self):
            return ytdl.QPoint(0, -120)
        def accept(self):
            pass
    visited = set()
    for _ in range(12):
        visited.add(window.cover_label.stack_order[0])
        window.cover_label.wheelEvent(Wheel())
    assert len(visited) == 12, "Wheel does not reach all covers"
    assert [item["url"] for item in window.batch_items] == old_order
    assert window.selected_cover()["url"] == old_order[back_index]
    saved_batch = window.batch_items
    window.batch_items = saved_batch[:1]
    window.cover_label.set_stack(window.batch_items)
    assert not window.cover_label.stack_entries and window.cover_label.source_pixmap is not None
    assert window.selected_cover() is window.batch_items[0], "Single cover lost ownership"
    window.batch_items = saved_batch
    window.cover_label.set_stack(saved_batch)
    with patch.object(ytdl.QFileDialog, "getExistingDirectory", return_value=directory), patch.object(ytdl.QMessageBox, "information"):
        # Avoid a name collision only for this cover-save check.
        window.batch_items[1]["info"]["title"] = "Cover one"
        window.save_all_covers()
    assert len(list(Path(directory).glob("*.jpg"))) == 12
    assert all(path.read_bytes().startswith(b"\xff\xd8") for path in Path(directory).glob("*.jpg"))
    window.batch_items[1]["info"]["title"] = "Same title"
    def fake_start(manager):
        manager.state = "running"
    with patch.object(ytdl.DownloadManager, "start", fake_start), patch.object(ytdl.QFileDialog, "getExistingDirectory", return_value=directory):
        window.max_concurrent_downloads = 2
        window.prepare_download()
        assert len(window.tasks) == 12
        assert sum(manager.state == "running" for manager, _ in window.tasks) == 2
        assert sum(manager.state == "waiting" for manager, _ in window.tasks) == 10
        assert sum(not card.isHidden() for _, card in window.tasks) == 10
        assert len({manager.output_path for manager, _ in window.tasks}) == 12
        assert [manager.url for manager, _ in window.tasks] == old_order
        assert all(manager.selector == "v+a" for manager, _ in window.tasks)
        window.tasks[0][0].state = "finished"
        window.schedule_tasks()
        assert window.tasks[2][0].state == "running"
    package = ytdl.preview_package(video(0))
    assert package["selector"] == "v+a" and package["merge_ext"] == "mp4"
    class CancelledPreview(ytdl.QThread):
        def __init__(self):
            super().__init__()
            self.stopped = False
        def run(self):
            while not self.stopped:
                self.msleep(5)
        def request_stop(self):
            self.stopped = True
    cancelled_worker = CancelledPreview()
    window.preview_cache_worker = cancelled_worker
    cancelled_worker.start()
    window.stop_preview_cache()
    deadline = time.monotonic() + 2
    while window.retired_preview_workers and time.monotonic() < deadline:
        QTest.qWait(10)
    assert not window.retired_preview_workers and window.preview_cache_worker is None
    for width, height in ((860, 700), (1020, 830)):
        window.resize(width, height)
        QTest.qWait(40)
        last = window.page_layout.itemAt(window.page_layout.count() - 1).geometry()
        assert last.bottom() < window.centralWidget().height(), "Batch layout overflowed window"
    window.grab().save(str(Path(__file__).parent / ".checkenv" / "batch-ui-check.png"))
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        audio_clip = Path(directory) / "audio-preview.mp4"
        subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=320x180:r=30",
                        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100", "-t", "3",
                        "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p", str(audio_clip)],
                       check=True, capture_output=True, timeout=20)
        assert window.ensure_preview_player()
        window.clip_panel.show()
        window.preview_waiting_cache = True
        window.preview_waiting_play = False
        window.preview_target_ms = 0
        window.preview_cache_ready(str(audio_clip))
        deadline = time.monotonic() + 5
        while not window.preview_player.hasAudio() and time.monotonic() < deadline:
            QTest.qWait(20)
        assert window.preview_player.hasAudio(), "Preview player did not recognize audio stream"
        assert window.preview_player.audioOutput() is window.preview_audio
        assert not window.preview_audio.isMuted() and window.preview_audio.volume() > 0
        window.toggle_preview()
        QTest.qWait(300)
        assert window.preview_player.position() > 0, "Audio/video preview did not play"
        window.cancel_clip_selection()
        window.preview_player.setSource(ytdl.QUrl())
        print("PREVIEW_AUDIO_OK: AAC stream recognized, audio output connected and unmuted, playback advances")
    # Moving from a real batch to one selected result restores normal parsing.
    window.selected_search_ids = {entries[0]["id"]}
    with patch.object(ytdl.InfoWorker, "fetch", side_effect=fetch), patch.object(window, "start_preview_cache"):
        window.parse_selected_results()
        deadline = time.monotonic() + 5
        while window.info_worker is not None and time.monotonic() < deadline:
            QTest.qWait(10)
        assert window.info_worker is None and window.batch_worker is None
        assert not window.batch_items and window.info["id"] == entries[0]["id"]
        assert window.url_edit.text() == entries[0]["webpage_url"]
        assert window.audio_combo.isEnabled() and window.range_combo.isEnabled()
        assert window.format_combo.isEnabled() and window.filename_edit.isEnabled()
        assert not window.cover_label.stack_entries and window.cover_label.source_pixmap is not None
        assert window.save_all_covers_btn.isHidden()
        window.show_clip_selector()
        assert not window.clip_panel.isHidden(), "Single selected result cannot open clipping"
        window.cancel_clip_selection()
    print("SINGLE_SELECTION_OK: normal parsing, audio, clipping, formats, filename and cover restored")
    for manager, _ in window.tasks:
        manager.state = "finished"
    window.close()
    app.processEvents()
    print("BATCH_OK: 12 items, 2 running, 10 queued, 10 visible; cover ownership and saved JPEGs verified")
