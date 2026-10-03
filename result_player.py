"""Single reusable, cancellable search-result player with separate-stream audio."""
from threading import Event
import time
from PyQt6.QtCore import QThread, QTimer, QUrl, Qt, pyqtSignal
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSlider

class ClickSeekSlider(QSlider):
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            fraction = max(0, min(1, (event.position().x() - 7) / max(1, self.width() - 14)))
            self.setValue(round(self.minimum() + fraction * (self.maximum() - self.minimum())))
            self.setSliderDown(True)
            self.sliderReleased.emit()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.isSliderDown():
            fraction = max(0, min(1, (event.position().x() - 7) / max(1, self.width() - 14)))
            self.setValue(round(self.minimum() + fraction * (self.maximum() - self.minimum())))
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.isSliderDown():
            self.setSliderDown(False)
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class PlaybackMetadataWorker(QThread):
    ready = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, url, fetch):
        super().__init__()
        self.url, self.fetch = url, fetch
        self.cancelled = Event()

    def run(self):
        try:
            info, _ = self.fetch(self.url, self.cancelled)
            if not self.cancelled.is_set():
                self.ready.emit(info)
        except Exception as exc:
            if not self.cancelled.is_set():
                self.failed.emit(str(exc))


class SearchVideoPlayer(QDialog):
    def __init__(self, parent, fetch, select_sources, text, icon):
        super().__init__(parent)
        self.fetch, self.select_sources, self.text, self.icon = fetch, select_sources, text, icon
        self.current_worker = None
        self.workers = set()
        self.setWindowTitle('YouTube Player')
        self.resize(960, 640)
        layout = QVBoxLayout(self)
        self.video = QVideoWidget()
        self.video.setStyleSheet('background:#090a0d;')
        layout.addWidget(self.video, 1)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.status)
        self.seek = ClickSeekSlider(Qt.Orientation.Horizontal)
        self.seek.setRange(0, 0)
        self.seek.sliderReleased.connect(self.seek_to_position)
        layout.addWidget(self.seek)
        controls = QHBoxLayout()
        self.play_button = QPushButton()
        self.play_button.clicked.connect(self.toggle_play)
        self.play_button.setIcon(icon('fa5s.play'))
        self.play_button.setToolTip(text('play'))
        controls.addWidget(self.play_button)
        self.time = QLabel('00:00 / 00:00')
        controls.addWidget(self.time)
        controls.addStretch()
        self.mute = QPushButton()
        self.mute.setIcon(icon('fa5s.volume-up'))
        self.mute.clicked.connect(self.toggle_mute)
        controls.addWidget(self.mute)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(75)
        self.volume.setFixedWidth(110)
        controls.addWidget(self.volume)
        self.fullscreen = QPushButton()
        self.fullscreen.setIcon(icon('fa5s.expand'))
        self.fullscreen.clicked.connect(lambda: self.showNormal() if self.isFullScreen() else self.showFullScreen())
        controls.addWidget(self.fullscreen)
        layout.addLayout(controls)
        self.player, self.audio_player = QMediaPlayer(self), QMediaPlayer(self)
        self.output = QAudioOutput(self)
        self.output.setVolume(.75)
        self.player.setVideoOutput(self.video)
        self.player.setAudioOutput(self.output)
        self.separate_audio = False
        self.volume.valueChanged.connect(lambda value: self.output.setVolume(value / 100))
        self.player.durationChanged.connect(lambda duration: self.seek.setRange(0, duration))
        self.player.positionChanged.connect(self.position_changed)
        self.player.playbackStateChanged.connect(self.state_changed)
        self.player.errorOccurred.connect(self.playback_error)
        self.audio_player.errorOccurred.connect(self.playback_error)
        self.player.mediaStatusChanged.connect(self.media_status_changed)
        self.audio_player.mediaStatusChanged.connect(lambda _status: self.check_buffer())
        self.player.bufferProgressChanged.connect(lambda _value: self.check_buffer())
        self.audio_player.bufferProgressChanged.connect(lambda _value: self.check_buffer())
        self.buffer_timer = QTimer(self)
        self.buffer_timer.setInterval(100)
        self.buffer_timer.timeout.connect(self.check_buffer)
        self.waiting_buffer = False
        self.want_play = False
        self.last_audio_seek = 0.0

    def open_video(self, url):
        self.stop_sources()
        for worker in self.workers:
            worker.cancelled.set()
        self.status.setText(self.text('connecting'))
        self.current_url = url
        self.setWindowTitle('YouTube Player')
        self.seek.setRange(0, 0)
        self.time.setText('00:00 / 00:00')
        worker = PlaybackMetadataWorker(url, self.fetch)
        self.current_worker = worker
        self.workers.add(worker)
        worker.ready.connect(lambda info, w=worker: self.metadata_ready(w, info))
        worker.failed.connect(lambda detail, w=worker: self.status.setText(detail) if w is self.current_worker else None)
        worker.finished.connect(lambda w=worker: self.worker_finished(w))
        worker.start()
        self.show()
        self.raise_()
        self.activateWindow()

    def metadata_ready(self, worker, info):
        if worker is not self.current_worker or worker.cancelled.is_set():
            return
        try:
            video, audio = self.select_sources(info)
            self.setWindowTitle(info.get('title') or 'YouTube Player')
            self.status.setText(f"{video.get('height') or '?'}p · {video.get('vcodec') or ''}")
            self.separate_audio = audio is not None
            self.audio_player.setAudioOutput(None)
            self.player.setAudioOutput(None if self.separate_audio else self.output)
            self.audio_player.setAudioOutput(self.output if self.separate_audio else None)
            self.player.setSource(QUrl(video['url']))
            if audio:
                self.audio_player.setSource(QUrl(audio['url']))
            self.player.play()
            if audio:
                self.audio_player.play()
            self.want_play = True
            self.begin_buffer()
        except Exception as exc:
            self.status.setText(str(exc))

    def worker_finished(self, worker):
        self.workers.discard(worker)
        if self.current_worker is worker:
            self.current_worker = None
        worker.deleteLater()

    def stop_sources(self):
        self.want_play = False
        self.waiting_buffer = False
        self.buffer_timer.stop()
        self.player.stop()
        self.audio_player.stop()
        self.player.setSource(QUrl())
        self.audio_player.setSource(QUrl())

    def toggle_play(self):
        if self.waiting_buffer:
            self.want_play = not self.want_play
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.want_play = False
            self.player.pause()
            self.audio_player.pause()
        else:
            self.want_play = True
            self.player.play()
            if self.separate_audio:
                self.audio_player.setPosition(self.player.position())
                self.audio_player.play()

    def seek_to_position(self):
        self.player.setPosition(self.seek.value())
        if self.separate_audio:
            self.audio_player.setPosition(self.seek.value())

    def position_changed(self, position):
        if not self.seek.isSliderDown():
            self.seek.setValue(position)
        def clock(value):
            seconds = value // 1000
            return f'{seconds // 60:02}:{seconds % 60:02}'
        self.time.setText(f'{clock(position)} / {clock(self.player.duration())}')
        if (self.separate_audio
                and self.audio_player.mediaStatus() in (QMediaPlayer.MediaStatus.LoadedMedia,
                    QMediaPlayer.MediaStatus.BufferingMedia, QMediaPlayer.MediaStatus.BufferedMedia)
                and self.audio_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState):
            drift = self.audio_player.position() - position
            # Repeated remote seeks were restarting audio buffering every ~half second.
            if abs(drift) > 1500 and time.monotonic() - self.last_audio_seek > 8:
                self.audio_player.setPosition(position)
                self.last_audio_seek = time.monotonic()
            else:
                self.audio_player.setPlaybackRate(0.98 if drift > 150 else 1.02 if drift < -150 else 1.0)

    def state_changed(self, state):
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.play_button.setIcon(self.icon('fa5s.pause' if playing else 'fa5s.play'))
        self.play_button.setToolTip(self.text('pause' if playing else 'play'))
        if not playing:
            self.audio_player.pause()

    def media_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.audio_player.stop()
        elif status == QMediaPlayer.MediaStatus.StalledMedia:
            if self.want_play:
                self.begin_buffer()
        elif status == QMediaPlayer.MediaStatus.BufferedMedia and self.separate_audio and self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.audio_player.setPosition(self.player.position())
            self.audio_player.play()

    def begin_buffer(self):
        self.waiting_buffer = True
        self.buffer_started = time.monotonic()
        self.player.pause()
        self.audio_player.pause()
        self.status.setText(self.text('connecting'))
        self.buffer_timer.start()

    def check_buffer(self):
        if not self.waiting_buffer or time.monotonic() - self.buffer_started < 1:
            return
        players = [self.player, self.audio_player] if self.separate_audio else [self.player]
        ready = all(p.bufferProgress() >= .95 or p.mediaStatus() == QMediaPlayer.MediaStatus.BufferedMedia
                    or p.source().isLocalFile()
                    or (p.mediaStatus() == QMediaPlayer.MediaStatus.LoadedMedia
                        and time.monotonic() - self.buffer_started >= 2)
                    for p in players)
        if ready:
            self.waiting_buffer = False
            self.buffer_timer.stop()
            self.status.setText('')
            if self.want_play:
                self.player.play()
                if self.separate_audio:
                    self.audio_player.setPosition(self.player.position())
                    self.audio_player.play()

    def toggle_mute(self):
        self.output.setMuted(not self.output.isMuted())
        self.mute.setIcon(self.icon('fa5s.volume-mute' if self.output.isMuted() else 'fa5s.volume-up'))

    def playback_error(self, _error, detail):
        self.want_play = False
        self.waiting_buffer = False
        self.buffer_timer.stop()
        self.status.setText(detail)
        self.player.pause()
        self.audio_player.pause()

    def closeEvent(self, event):
        self.current_worker = None
        self.stop_sources()
        for worker in self.workers:
            worker.cancelled.set()
        if self.workers:
            event.ignore()
            QTimer.singleShot(100, self.close)
        else:
            event.accept()
