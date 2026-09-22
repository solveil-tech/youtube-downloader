import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

import requests

# PyInstaller's Qt hook normally configures this path, but on some Windows
# systems QtCore is imported before the wheel's DLL directory is retained.
# Keep the add_dll_directory handle alive for the full process lifetime.
_QT_DLL_DIRECTORY_HANDLE = None
if getattr(sys, "frozen", False) and os.name == "nt":
    _qt_dll_dir = Path(sys._MEIPASS) / "PyQt6" / "Qt6" / "bin"
    if _qt_dll_dir.is_dir():
        os.environ["PATH"] = str(_qt_dll_dir) + os.pathsep + os.environ.get("PATH", "")
        if hasattr(os, "add_dll_directory"):
            _QT_DLL_DIRECTORY_HANDLE = os.add_dll_directory(str(_qt_dll_dir))

from PyQt6.QtCore import QEvent, QPoint, QProcess, QRectF, QSettings, QSize, Qt, QThread, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QDesktopServices, QFont, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QProgressBar, QPushButton,
    QScrollArea, QScrollBar, QSizePolicy, QStyle, QStyledItemDelegate, QStyleOptionViewItem,
    QVBoxLayout, QWidget,
)

try:
    import qtawesome as qta
except ImportError:
    qta = None

APP_NAME = "Youtube Downloader"
ORG_NAME = "Solveil"
COOKIE_FILE = "cookies.txt"
MAX_TASKS = 5
WINDOW_ASPECT_RATIO = 860 / 700
BG, CARD, TEXT, MUTED = "#f5f6f8", "#ffffff", "#17191d", "#737984"
ACCENT, ACCENT_HOVER, BORDER, DANGER = "#5668e9", "#4658d8", "#dde1e8", "#d94b54"

LANGUAGE_CODES = ("zh", "en", "ja", "ko", "fr", "de", "ru", "it", "es", "ar")
LANGUAGE_NAMES = {
    "zh": "中文", "en": "English", "ja": "日本語", "ko": "한국어", "fr": "Français",
    "de": "Deutsch", "ru": "Русский", "it": "Italiano", "es": "Español", "ar": "العربية",
}
CURRENT_LANGUAGE = "zh"

# Chinese, English, Japanese, Korean, French, German, Russian, Italian, Spanish, Arabic
TEXTS = {
    "language_tip": ("切换语言", "Change language", "言語を変更", "언어 변경", "Changer de langue", "Sprache ändern", "Сменить язык", "Cambia lingua", "Cambiar idioma", "تغيير اللغة"),
    "theme_tip": ("切换明暗颜色模式", "Toggle light/dark mode", "ライト／ダーク切替", "라이트/다크 모드", "Changer le thème", "Hell/Dunkel wechseln", "Сменить тему", "Cambia tema", "Cambiar tema", "تبديل المظهر"),
    "url_placeholder": ("粘贴 YouTube 视频链接", "Paste a YouTube video link", "YouTube動画リンクを貼り付け", "YouTube 동영상 링크 붙여넣기", "Collez un lien YouTube", "YouTube-Link einfügen", "Вставьте ссылку YouTube", "Incolla un link YouTube", "Pega un enlace de YouTube", "ألصق رابط فيديو YouTube"),
    "paste_parse": ("粘贴并解析", "Paste & analyze", "貼り付けて解析", "붙여넣고 분석", "Coller et analyser", "Einfügen & analysieren", "Вставить и разобрать", "Incolla e analizza", "Pegar y analizar", "لصق وتحليل"),
    "no_cover": ("暂无封面", "No thumbnail", "サムネイルなし", "썸네일 없음", "Aucune miniature", "Kein Vorschaubild", "Нет обложки", "Nessuna miniatura", "Sin miniatura", "لا توجد صورة مصغرة"),
    "title_placeholder": ("解析视频后将在这里显示标题", "The video title will appear here", "動画タイトルがここに表示されます", "동영상 제목이 여기에 표시됩니다", "Le titre apparaîtra ici", "Der Videotitel erscheint hier", "Название появится здесь", "Il titolo apparirà qui", "El título aparecerá aquí", "سيظهر عنوان الفيديو هنا"),
    "cover_with_video": ("随视频下载封面", "Download thumbnail with video", "動画と一緒にサムネイルを保存", "동영상과 함께 썸네일 저장", "Télécharger la miniature", "Vorschaubild mitladen", "Скачать обложку", "Scarica miniatura", "Descargar miniatura", "تنزيل الصورة المصغرة"),
    "save_cover": ("单独保存封面", "Save thumbnail", "サムネイルを保存", "썸네일 저장", "Enregistrer la miniature", "Vorschaubild speichern", "Сохранить обложку", "Salva miniatura", "Guardar miniatura", "حفظ الصورة المصغرة"),
    "download_format": ("下载格式", "Download format", "ダウンロード形式", "다운로드 형식", "Format de téléchargement", "Downloadformat", "Формат загрузки", "Formato download", "Formato de descarga", "صيغة التنزيل"),
    "filename": ("文件名", "File name", "ファイル名", "파일 이름", "Nom du fichier", "Dateiname", "Имя файла", "Nome file", "Nombre del archivo", "اسم الملف"),
    "filename_placeholder": ("保存文件名，可手动修改", "Output file name — editable", "保存ファイル名（編集可）", "저장 파일 이름(편집 가능)", "Nom du fichier modifiable", "Dateiname (bearbeitbar)", "Имя файла можно изменить", "Nome file modificabile", "Nombre de archivo editable", "اسم الملف قابل للتعديل"),
    "download_range": ("下载范围", "Download range", "ダウンロード範囲", "다운로드 범위", "Plage de téléchargement", "Downloadbereich", "Диапазон загрузки", "Intervallo download", "Rango de descarga", "نطاق التنزيل"),
    "full_video": ("完整视频", "Full video", "動画全体", "전체 동영상", "Vidéo complète", "Ganzes Video", "Полное видео", "Video completo", "Vídeo completo", "الفيديو كاملاً"),
    "select_clip": ("选择片段", "Select clip", "範囲を選択", "구간 선택", "Sélectionner un extrait", "Ausschnitt wählen", "Выбрать фрагмент", "Seleziona clip", "Seleccionar fragmento", "تحديد مقطع"),
    "full_video_info": ("将下载完整视频", "The full video will be downloaded", "動画全体をダウンロードします", "전체 동영상을 다운로드합니다", "La vidéo complète sera téléchargée", "Das ganze Video wird geladen", "Будет загружено полное видео", "Verrà scaricato il video completo", "Se descargará el vídeo completo", "سيتم تنزيل الفيديو كاملاً"),
    "choosing_range": ("待选择：{value}", "Selecting: {value}", "選択中：{value}", "선택 중: {value}", "Sélection : {value}", "Auswahl: {value}", "Выбор: {value}", "Selezione: {value}", "Seleccionando: {value}", "جارٍ التحديد: {value}"),
    "pending_range": ("待应用：{value}", "Ready to apply: {value}", "適用待ち：{value}", "적용 대기: {value}", "À appliquer : {value}", "Bereit: {value}", "Готово к применению: {value}", "Da applicare: {value}", "Listo para aplicar: {value}", "جاهز للتطبيق: {value}"),
    "selected_range": ("已选择：{value}", "Selected: {value}", "選択済み：{value}", "선택됨: {value}", "Sélectionné : {value}", "Ausgewählt: {value}", "Выбрано: {value}", "Selezionato: {value}", "Seleccionado: {value}", "تم التحديد: {value}"),
    "download_audio": ("下载音频", "Download audio", "音声をダウンロード", "오디오 다운로드", "Télécharger l’audio", "Audio herunterladen", "Скачать аудио", "Scarica audio", "Descargar audio", "تنزيل الصوت"),
    "add_task": ("添加下载任务", "Add download task", "ダウンロードを追加", "다운로드 작업 추가", "Ajouter un téléchargement", "Download hinzufügen", "Добавить загрузку", "Aggiungi download", "Añadir descarga", "إضافة مهمة تنزيل"),
    "tasks": ("下载任务", "Download tasks", "ダウンロード", "다운로드 작업", "Téléchargements", "Downloads", "Загрузки", "Download", "Descargas", "مهام التنزيل"),
    "clip_panel": ("选择片段", "Clip selection", "範囲選択", "구간 선택", "Sélection de l’extrait", "Ausschnitt wählen", "Выбор фрагмента", "Selezione clip", "Selección de fragmento", "تحديد المقطع"),
    "preview_tip": ("点击画面播放或暂停", "Click the video to play or pause", "画面をクリックして再生／一時停止", "화면을 클릭해 재생/일시정지", "Cliquez pour lire ou mettre en pause", "Zum Abspielen/Pausieren klicken", "Нажмите для воспроизведения/паузы", "Clicca per riprodurre o mettere in pausa", "Haz clic para reproducir o pausar", "انقر للتشغيل أو الإيقاف المؤقت"),
    "frame_back": ("◀ 帧", "◀ Frame", "◀ コマ", "◀ 프레임", "◀ Image", "◀ Bild", "◀ Кадр", "◀ Fotogramma", "◀ Fotograma", "◀ إطار"),
    "frame_forward": ("帧 ▶", "Frame ▶", "コマ ▶", "프레임 ▶", "Image ▶", "Bild ▶", "Кадр ▶", "Fotogramma ▶", "Fotograma ▶", "إطار ▶"),
    "play": ("播放", "Play", "再生", "재생", "Lire", "Abspielen", "Воспроизвести", "Riproduci", "Reproducir", "تشغيل"),
    "pause": ("暂停", "Pause", "一時停止", "일시정지", "Pause", "Pause", "Пауза", "Pausa", "Pausa", "إيقاف مؤقت"),
    "cancel": ("取消", "Cancel", "キャンセル", "취소", "Annuler", "Abbrechen", "Отмена", "Annulla", "Cancelar", "إلغاء"),
    "apply": ("应用", "Apply", "適用", "적용", "Appliquer", "Anwenden", "Применить", "Applica", "Aplicar", "تطبيق"),
    "waiting": ("等待开始", "Waiting", "待機中", "대기 중", "En attente", "Warten", "Ожидание", "In attesa", "En espera", "في الانتظار"),
    "open_folder": ("打开文件夹", "Open folder", "フォルダーを開く", "폴더 열기", "Ouvrir le dossier", "Ordner öffnen", "Открыть папку", "Apri cartella", "Abrir carpeta", "فتح المجلد"),
    "clear": ("清除", "Clear", "消去", "지우기", "Effacer", "Löschen", "Очистить", "Cancella", "Borrar", "مسح"),
    "hide_task": ("隐藏任务", "Hide task", "タスクを隠す", "작업 숨기기", "Masquer la tâche", "Aufgabe ausblenden", "Скрыть задачу", "Nascondi attività", "Ocultar tarea", "إخفاء المهمة"),
    "resume": ("继续", "Resume", "再開", "계속", "Reprendre", "Fortsetzen", "Продолжить", "Riprendi", "Reanudar", "متابعة"),
    "remaining": ("剩余 {value}", "{value} remaining", "残り {value}", "남은 시간 {value}", "{value} restantes", "Noch {value}", "Осталось {value}", "{value} rimanenti", "Quedan {value}", "متبقي {value}"),
    "downloading": ("正在下载", "Downloading", "ダウンロード中", "다운로드 중", "Téléchargement", "Wird heruntergeladen", "Загрузка", "Download in corso", "Descargando", "جارٍ التنزيل"),
    "connecting": ("正在连接...", "Connecting...", "接続中...", "연결 중...", "Connexion...", "Verbindung...", "Подключение...", "Connessione...", "Conectando...", "جارٍ الاتصال..."),
    "speed_estimating": ("速度估算中", "Estimating speed", "速度を計算中", "속도 계산 중", "Estimation de la vitesse", "Geschwindigkeit wird geschätzt", "Оценка скорости", "Stima velocità", "Calculando velocidad", "تقدير السرعة"),
    "processing": ("处理中", "Processing", "処理中", "처리 중", "Traitement", "Verarbeitung", "Обработка", "Elaborazione", "Procesando", "جارٍ المعالجة"),
    "clip_processing": ("片段处理中", "Processing clip", "範囲を処理中", "구간 처리 중", "Traitement de l’extrait", "Ausschnitt wird verarbeitet", "Обработка фрагмента", "Elaborazione clip", "Procesando fragmento", "جارٍ معالجة المقطع"),
    "muxing": ("正在封装", "Muxing", "多重化中", "병합 중", "Muxage", "Muxing", "Мультиплексирование", "Muxing", "Multiplexando", "جارٍ الدمج"),
    "muxing_detail": ("音视频合并处理中", "Combining audio and video", "映像と音声を結合中", "오디오와 비디오 병합 중", "Fusion audio et vidéo", "Audio und Video werden verbunden", "Объединение аудио и видео", "Unione audio e video", "Combinando audio y vídeo", "جارٍ دمج الصوت والفيديو"),
    "finished": ("下载完成", "Download complete", "ダウンロード完了", "다운로드 완료", "Téléchargement terminé", "Download abgeschlossen", "Загрузка завершена", "Download completato", "Descarga completada", "اكتمل التنزيل"),
}


def tr(key, **values):
    options = TEXTS.get(key)
    if not options:
        return key
    try:
        text = options[LANGUAGE_CODES.index(CURRENT_LANGUAGE)]
    except (ValueError, IndexError):
        text = options[0]
    return text.format(**values) if values else text


def runtime_dir():
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent


def bundled_path(name):
    bundled = Path(getattr(sys, "_MEIPASS", runtime_dir())) / name
    return bundled if bundled.exists() else runtime_dir() / name


def cookie_path():
    path = runtime_dir() / COOKIE_FILE
    return path if path.exists() else None


def clean_filename(name):
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", str(name or ""))
    name = re.sub(r"\s+", " ", name).strip().rstrip(".")
    return name[:180] or "Youtube Video"


def is_supported_url(url):
    return bool(re.search(r"(youtube\.com/(watch|shorts|live)|youtu\.be/)", url, re.I))


def human_size(value):
    if not value:
        return "未知"
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return "未知"


def seconds_text(seconds):
    try:
        seconds = max(0, int(float(seconds)))
    except (TypeError, ValueError):
        seconds = 0
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"


def seconds_text_ms(seconds):
    try:
        milliseconds = max(0, int(round(float(seconds) * 1000)))
    except (TypeError, ValueError):
        milliseconds = 0
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, millis = divmod(remainder, 1000)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{millis:03d}"
    return f"{minutes:02d}:{whole_seconds:02d}.{millis:03d}"


def filename_time(seconds):
    seconds = max(0, int(round(float(seconds or 0))))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}-{minutes:02d}-{seconds:02d}" if hours else f"{minutes:02d}-{seconds:02d}"


def strip_time_suffix(name):
    return re.sub(r"\s*\[\d{2}(?:-\d{2}){1,2}~\d{2}(?:-\d{2}){1,2}\]$", "", name).rstrip()


def parse_time(value):
    parts = str(value or "").strip().split(":")
    if not parts or len(parts) > 3 or any(not p.isdigit() for p in parts):
        raise ValueError("请使用 HH:MM:SS 或 MM:SS 格式")
    total = 0
    for part in parts:
        total = total * 60 + int(part)
    return float(total)


def estimated_size(fmt, duration, audio_size=0):
    size = estimated_size_bytes(fmt, duration, audio_size)
    return human_size(size) if size else "未知"


def estimated_size_bytes(fmt, duration, audio_size=0):
    size = fmt.get("filesize") or fmt.get("filesize_approx")
    if not size and (fmt.get("tbr") or fmt.get("vbr")) and duration:
        size = float(fmt.get("tbr") or fmt.get("vbr")) * float(duration) * 1000 / 8
    return int(float(size) + float(audio_size or 0)) if size else 0


def quality_height(fmt):
    width = int(fmt.get("width") or 0)
    height = int(fmt.get("height") or 0)
    if width > 0 and height > 0:
        return min(width, height)
    return height or width


def format_label(fmt, duration, audio_size):
    height, width, fps = fmt.get("height") or 0, fmt.get("width") or 0, fmt.get("fps") or 0
    ext = (fmt.get("ext") or "?").upper()
    codec = codec_label(fmt.get("vcodec"))
    display_height = quality_height(fmt)
    resolution = f"{display_height}p" if display_height else (fmt.get("resolution") or "未知分辨率")
    if width and height:
        resolution += f" ({width}×{height})"
    fps_text = f"{fps:g}fps" if fps else "帧率未知"
    audio = fmt.get("acodec") not in (None, "none")
    size = estimated_size(fmt, duration, 0 if audio else audio_size)
    bitrate = fmt.get("tbr") or fmt.get("vbr")
    bitrate_text = f" · {bitrate / 1000:.1f}Mbps" if bitrate else ""
    return f"{resolution} · {fps_text} · {ext} · {codec}{bitrate_text} · {size}"


def codec_label(codec):
    raw = str(codec or "?").lower()
    short = raw.split(".")[0]
    if raw.startswith(("avc1", "h264")):
        return "H.264 (AVC)"
    if raw.startswith(("hev1", "hvc1", "hevc")):
        return "H.265 (HEVC)"
    if raw.startswith(("vp09", "vp9")):
        return "VP9"
    if raw.startswith(("av01", "av1")):
        return "AV1"
    return short


def numeric_progress(value):
    try:
        number = float(str(value or "").strip())
        return number if number >= 0 else 0.0
    except (TypeError, ValueError):
        return 0.0


def is_direct_media_format(fmt):
    protocol = str(fmt.get("protocol") or "").lower()
    return bool(fmt.get("url")) and protocol in {"http", "https"}


def default_format_key(fmt):
    return (quality_height(fmt), fmt.get("fps") or 0, int(str(fmt.get("ext", "")).lower() == "mp4"), fmt.get("tbr") or 0)


class InfoWorker(QThread):
    result = pyqtSignal(dict, bytes)
    failed = pyqtSignal(str)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            engine = bundled_path("yt_dlp.exe")
            if not engine.exists():
                raise RuntimeError("未找到下载引擎 yt_dlp.exe")
            command = [str(engine), "--dump-single-json", "--skip-download", "--no-playlist", "--no-warnings"]
            cookie = cookie_path()
            if cookie:
                command += ["--cookies", str(cookie)]
            command.append(self.url)
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=120,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            if completed.returncode:
                raise RuntimeError(completed.stderr.strip() or "视频信息解析失败")
            info = json.loads(completed.stdout)
            thumb = b""
            if info.get("thumbnail"):
                response = requests.get(info["thumbnail"], timeout=20)
                response.raise_for_status()
                thumb = response.content
            self.result.emit(info, thumb)
        except Exception as exc:
            self.failed.emit(str(exc))


class LoadingSpinner(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.advance)
        self.setFixedSize(24, 24)
        self.hide()

    def set_scale(self, scale):
        size = max(18, round(24 * scale))
        self.setFixedSize(size, size)

    def start(self):
        self.show()
        self.timer.start(35)

    def stop(self):
        self.timer.stop()
        self.hide()

    def advance(self):
        self.angle = (self.angle - 12) % 360
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(ACCENT), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(self.rect().adjusted(4, 4, -4, -4), self.angle * 16, 250 * 16)


class CoverLabel(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.source_pixmap = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_image(self, data):
        pixmap = QPixmap()
        self.source_pixmap = pixmap if data and pixmap.loadFromData(data) else None
        if self.source_pixmap:
            self.setText("")
        else:
            self.clear()
            self.setText(tr("no_cover"))
        self.refresh()

    def refresh(self):
        if self.source_pixmap:
            self.setPixmap(self.source_pixmap.scaled(
                self.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refresh()


class AspectRatioContainer(QWidget):
    def __init__(self, child, parent=None):
        super().__init__(parent)
        self.child = child
        self.child.setParent(self)
        self.setMinimumSize(320, 180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return max(180, int(width * 9 / 16))

    def sizeHint(self):
        return QSize(480, 270)

    def set_scale(self, scale):
        self.setMinimumSize(max(230, round(320 * scale)), max(129, round(180 * scale)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        width, height = self.width(), self.height()
        target_width = min(width, int(height * 16 / 9))
        target_height = min(height, int(width * 9 / 16))
        x = (width - target_width) // 2
        y = (height - target_height) // 2
        self.child.setGeometry(x, y, target_width, target_height)


class RangeTimeline(QWidget):
    seek_requested = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.duration = 1
        self.position = 0
        self.start_value = 0
        self.end_value = 1
        self.applied = False
        self.track_color = QColor("#dfe2e8")
        self.selection_color = QColor(ACCENT)
        self.position_color = QColor(TEXT)
        self.setMinimumHeight(30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_scale(self, scale):
        self.setMinimumHeight(max(22, round(30 * scale)))

    def set_theme(self, dark):
        self.track_color = QColor("#3a3f49" if dark else "#dfe2e8")
        self.selection_color = QColor("#7987ff" if dark else ACCENT)
        self.position_color = QColor("#f1f3f7" if dark else TEXT)
        self.update()

    def set_duration(self, milliseconds):
        self.duration = max(1, int(milliseconds))
        self.end_value = self.duration
        self.update()

    def set_position(self, milliseconds):
        self.position = max(0, min(self.duration, int(milliseconds)))
        self.update()

    def set_selection(self, start, end, applied=False):
        self.start_value = max(0, min(self.duration, int(start)))
        self.end_value = max(self.start_value, min(self.duration, int(end)))
        self.applied = applied
        self.update()

    def value_from_x(self, x):
        margin = 8
        usable = max(1, self.width() - margin * 2)
        ratio = max(0.0, min(1.0, (x - margin) / usable))
        return int(ratio * self.duration)

    def mousePressEvent(self, event):
        self.seek_requested.emit(self.value_from_x(event.position().x()))

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.seek_requested.emit(self.value_from_x(event.position().x()))

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        margin, bar_height = 8, 8
        width = max(1, self.width() - margin * 2)
        y = (self.height() - bar_height) / 2
        bar = QRectF(margin, y, width, bar_height)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.track_color)
        painter.drawRoundedRect(bar, 4, 4)
        start_x = margin + width * self.start_value / self.duration
        end_x = margin + width * self.end_value / self.duration
        if self.applied and end_x > start_x:
            painter.setBrush(self.selection_color)
            painter.drawRoundedRect(QRectF(start_x, y, end_x - start_x, bar_height), 4, 4)
        painter.setPen(QPen(self.selection_color, 2))
        painter.drawLine(int(start_x), int(y - 3), int(start_x), int(y + bar_height + 3))
        painter.drawLine(int(end_x), int(y - 3), int(end_x), int(y + bar_height + 3))
        play_x = margin + width * self.position / self.duration
        painter.setPen(QPen(self.position_color, 2))
        painter.drawLine(int(play_x), int(y - 3), int(play_x), int(y + bar_height + 3))


class ClickableVideoWidget(QVideoWidget):
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)


class FlatItemDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        clean_option = QStyleOptionViewItem(option)
        clean_option.state &= ~QStyle.StateFlag.State_HasFocus
        super().paint(painter, clean_option, index)


class MinimalVerticalScrollBar(QScrollBar):
    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Vertical, parent)
        self.dragging = False
        self.drag_offset = 0.0
        self.bar_width = 8
        self.track_color = QColor(CARD)
        self.handle_color = QColor(BORDER)
        self.setFixedWidth(self.bar_width)
        self.valueChanged.connect(self.update)
        self.rangeChanged.connect(lambda _minimum, _maximum: self.update())

    def set_scale(self, scale):
        self.bar_width = max(6, round(8 * scale))
        self.setFixedWidth(self.bar_width)
        self.update()

    def set_theme(self, dark):
        self.track_color = QColor("#1d2027" if dark else CARD)
        self.handle_color = QColor("#4a505d" if dark else BORDER)
        self.update()

    def handle_rect(self):
        top_margin = 2.0
        track_height = max(1.0, self.height() - top_margin * 2)
        value_range = self.maximum() - self.minimum()
        if value_range <= 0:
            return QRectF(1, top_margin, max(2, self.width() - 2), track_height)
        total = value_range + max(1, self.pageStep())
        handle_height = max(22.0, track_height * self.pageStep() / total)
        handle_height = min(track_height, handle_height)
        travel = max(1.0, track_height - handle_height)
        ratio = (self.value() - self.minimum()) / value_range
        top = top_margin + travel * ratio
        return QRectF(1, top, max(2, self.width() - 2), handle_height)

    def value_from_position(self, y, drag_offset=None):
        rect = self.handle_rect()
        track_height = max(1.0, self.height() - 4.0)
        travel = max(1.0, track_height - rect.height())
        offset = rect.height() / 2 if drag_offset is None else drag_offset
        ratio = max(0.0, min(1.0, (y - 2.0 - offset) / travel))
        return round(self.minimum() + ratio * (self.maximum() - self.minimum()))

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), self.track_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.handle_color)
        rect = self.handle_rect()
        radius = min(rect.width(), rect.height()) / 2
        painter.drawRoundedRect(rect, radius, radius)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self.maximum() <= self.minimum():
            event.accept()
            return
        rect = self.handle_rect()
        if rect.contains(event.position()):
            self.dragging = True
            self.drag_offset = event.position().y() - rect.top()
        else:
            self.setValue(self.value_from_position(event.position().y()))
        event.accept()

    def mouseMoveEvent(self, event):
        if self.dragging:
            self.setValue(self.value_from_position(event.position().y(), self.drag_offset))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False
            event.accept()
            return
        super().mouseReleaseEvent(event)


class ChevronButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.arrow_up = False
        self.arrow_color = QColor(MUTED)
        self.setObjectName("comboArrowButton")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_direction(self, up):
        self.arrow_up = up
        self.update()

    def set_theme(self, dark):
        self.arrow_color = QColor("#a5abb6" if dark else MUTED)
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(self.arrow_color, 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        center_x, center_y = self.width() / 2, self.height() / 2
        direction = -1 if self.arrow_up else 1
        painter.drawLine(int(center_x - 4), int(center_y - 2 * direction), int(center_x), int(center_y + 2 * direction))
        painter.drawLine(int(center_x), int(center_y + 2 * direction), int(center_x + 4), int(center_y - 2 * direction))


class LanguageButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.dark_theme = False
        self.setObjectName("languageSwitch")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_theme(self, dark):
        self.dark_theme = dark
        self.update()

    def paintEvent(self, _event):
        super().paintEvent(_event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor("#f1f3f7" if self.dark_theme else TEXT)
        painter.setPen(color)
        latin_font = QFont("Segoe UI", max(9, round(self.height() * 0.36)), QFont.Weight.DemiBold)
        painter.setFont(latin_font)
        painter.drawText(QRectF(4, 1, self.width() * 0.58, self.height() - 2), Qt.AlignmentFlag.AlignCenter, "A")
        japanese_font = QFont("Yu Gothic UI", max(8, round(self.height() * 0.31)), QFont.Weight.Medium)
        painter.setFont(japanese_font)
        painter.drawText(QRectF(self.width() * 0.38, self.height() * 0.28, self.width() * 0.58, self.height() * 0.68), Qt.AlignmentFlag.AlignCenter, "あ")


class ChevronComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.arrow_offset = 17
        self.arrow_up = False
        self.arrow_color = QColor(MUTED)
        self.arrow_width = 28
        self.current_scale = 1.0
        self.dark_theme = False
        self.popup_frame = None
        self.popup_list = None
        self.arrow_button = ChevronButton(self)
        self.arrow_button.pressed.connect(self.toggle_popup)
        self.setItemDelegate(FlatItemDelegate(self))
        self.view().setFocusPolicy(Qt.FocusPolicy.NoFocus)
        QApplication.instance().installEventFilter(self)

    def set_scale(self, scale):
        self.current_scale = scale
        self.arrow_offset = max(13, round(17 * scale))
        self.arrow_width = max(21, round(28 * scale))
        self.position_arrow_button()
        if self.popup_list is not None:
            self.popup_list.verticalScrollBar().set_scale(scale)
        self.update()

    def set_theme(self, dark):
        self.dark_theme = dark
        self.arrow_color = QColor("#a5abb6" if dark else MUTED)
        self.arrow_button.set_theme(dark)
        if self.popup_list is not None:
            self.popup_list.verticalScrollBar().set_theme(dark)
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.position_arrow_button()

    def position_arrow_button(self):
        self.arrow_button.setGeometry(self.width() - self.arrow_width, 0, self.arrow_width, self.height())
        self.arrow_button.raise_()

    def toggle_popup(self):
        if self.popup_frame is not None and self.popup_frame.isVisible():
            self.hidePopup()
        else:
            self.showPopup()

    def showPopup(self):
        if self.popup_frame is not None and self.popup_frame.isVisible():
            return
        host = self.window().centralWidget()
        if host is None:
            return
        if self.popup_frame is None or self.popup_frame.parent() is not host:
            self.popup_frame = QFrame(host)
            self.popup_frame.setObjectName("comboPopup")
            popup_layout = QVBoxLayout(self.popup_frame)
            popup_layout.setContentsMargins(0, 0, 0, 0)
            popup_layout.setSpacing(0)
            self.popup_list = QListWidget(self.popup_frame)
            self.popup_list.setObjectName("comboPopupList")
            self.popup_list.setFrameShape(QFrame.Shape.NoFrame)
            self.popup_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scrollbar = MinimalVerticalScrollBar(self.popup_list)
            scrollbar.set_scale(self.current_scale)
            scrollbar.set_theme(self.dark_theme)
            self.popup_list.setVerticalScrollBar(scrollbar)
            self.popup_list.itemClicked.connect(self.popup_item_clicked)
            popup_layout.addWidget(self.popup_list)
        self.popup_list.clear()
        row_height = max(26, self.height())
        for index in range(self.count()):
            item = QListWidgetItem(self.itemText(index))
            item.setSizeHint(QSize(max(1, self.width() - 2), row_height))
            self.popup_list.addItem(item)
        if self.currentIndex() >= 0:
            self.popup_list.setCurrentRow(self.currentIndex())
        short_list = self.count() <= self.maxVisibleItems()
        self.popup_list.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff if short_list
            else Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        position = self.mapTo(host, QPoint(0, self.height() - 1))
        desired_height = min(max(1, self.count()), self.maxVisibleItems()) * row_height + 6
        available_height = max(row_height + 2, host.height() - position.y())
        popup_height = min(desired_height, available_height)
        self.popup_frame.setGeometry(position.x(), position.y(), self.width(), popup_height)
        self.arrow_up = True
        self.arrow_button.set_direction(True)
        self.popup_frame.raise_()
        self.popup_frame.show()
        self.update()

    def hidePopup(self):
        if self.popup_frame is not None:
            self.popup_frame.hide()
        self.arrow_up = False
        self.arrow_button.set_direction(False)
        self.update()

    def popup_item_clicked(self, item):
        row = self.popup_list.row(item)
        self.hidePopup()
        self.setCurrentIndex(row)
        self.setFocus()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.popup_frame is not None and self.popup_frame.isVisible():
                self.hidePopup()
            else:
                self.showPopup()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def eventFilter(self, watched, event):
        if (
            self.popup_frame is not None
            and self.popup_frame.isVisible()
            and event.type() == QEvent.Type.MouseButtonPress
        ):
            global_position = event.globalPosition().toPoint()
            inside_combo = self.rect().contains(self.mapFromGlobal(global_position))
            inside_popup = self.popup_frame.rect().contains(self.popup_frame.mapFromGlobal(global_position))
            if not inside_combo and not inside_popup:
                self.hidePopup()
        return super().eventFilter(watched, event)

    def paintEvent(self, event):
        super().paintEvent(event)


class DownloadManager(QWidget):
    progress_changed = pyqtSignal(float, str, str, str)
    state_changed = pyqtSignal(str, str)
    finished = pyqtSignal(bool)
    PROGRESS_RE = re.compile(
        r"__YTDL__\|(?P<format_id>[^|]*)\|(?P<status>[^|]*)\|(?P<downloaded>[^|]*)"
        r"\|(?P<total>[^|]*)\|(?P<estimate>[^|]*)"
    )
    FFMPEG_TIME_RE = re.compile(r"time=\s*(?P<hours>\d+):(?P<minutes>\d+):(?P<seconds>[\d.]+)")
    FFMPEG_SPEED_RE = re.compile(r"speed=\s*(?P<speed>[\d.]+)x")

    def __init__(self, url, selector, output, merge_ext, cover, section=None, overwrite=False,
                 progress_components=None, parent=None):
        super().__init__(parent)
        self.url, self.selector, self.output_path = url, selector, str(output)
        self.merge_ext, self.download_cover, self.section = merge_ext, cover, section
        self.overwrite = overwrite
        self.state, self.process, self.output_log, self.stop_reason = "waiting", None, "", None
        self.last_percent = 0.0
        self.output_buffer = ""
        self.ffmpeg_speed = 0.0
        self.smoothed_speed = 0.0
        self.last_speed_sample_time = 0.0
        self.last_speed_sample_bytes = 0.0
        self.last_progress_emit = 0.0
        self.component_totals = {
            str(component.get("format_id")): float(component.get("size") or 0)
            for component in (progress_components or []) if component.get("format_id")
        }
        self.component_order = list(self.component_totals)
        self.component_downloaded = {format_id: 0.0 for format_id in self.component_totals}
        self.finished_components = set()
        output_path = Path(self.output_path)
        self.preexisting_files = {
            item.resolve() for item in output_path.parent.iterdir() if item.is_file()
        } if output_path.parent.exists() else set()

    def command(self):
        exe = bundled_path("yt_dlp.exe")
        args = [self.url, "--no-playlist", "--continue", "--newline", "--no-color", "--no-warnings",
                "--format", self.selector, "--output", self.output_path, "--concurrent-fragments", "5",
                "--retries", "infinite", "--fragment-retries", "infinite", "--file-access-retries", "infinite",
                "--retry-sleep", "5", "--socket-timeout", "20",
                "--progress-template", "download:__YTDL__|%(info_dict.format_id)s|%(progress.status)s|%(progress.downloaded_bytes)s|%(progress.total_bytes)s|%(progress.total_bytes_estimate)s"]
        if self.overwrite:
            args += ["--force-overwrites"]
        if self.merge_ext:
            args += ["--merge-output-format", self.merge_ext]
        if self.download_cover:
            args += ["--write-thumbnail", "--convert-thumbnails", "jpg"]
        if self.section:
            args += [
                "--download-sections", f"*{self.section[0]:.3f}-{self.section[1]:.3f}",
                "--downloader", "ffmpeg", "--force-keyframes-at-cuts",
                "--downloader-args", "ffmpeg:-progress pipe:2 -nostats",
            ]
        if cookie_path():
            args += ["--cookies", str(cookie_path())]
        ffmpeg = bundled_path("ffmpeg.exe")
        if ffmpeg.exists():
            args += ["--ffmpeg-location", str(ffmpeg.parent)]
        return exe, args

    def start(self):
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            return
        exe, args = self.command()
        if not exe.exists():
            self.state = "failed"
            self.state_changed.emit("failed", "未找到下载引擎 yt_dlp.exe")
            self.finished.emit(False)
            return
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.finished.connect(self.process_finished)
        self.process.errorOccurred.connect(self.process_error)
        self.stop_reason, self.state = None, "running"
        self.last_speed_sample_time = time.monotonic()
        self.last_speed_sample_bytes = sum(self.component_downloaded.values())
        self.last_progress_emit = 0.0
        self.state_changed.emit("running", tr("connecting"))
        self.process.start(str(exe), args)

    def resolve_progress_component(self, reported_id, reported_total):
        if reported_id in self.component_totals:
            return reported_id
        if not self.component_totals:
            component_id = reported_id or "download"
            self.component_order.append(component_id)
            self.component_totals[component_id] = reported_total
            self.component_downloaded[component_id] = 0.0
            return component_id

        candidates = [
            component_id for component_id in self.component_order
            if component_id not in self.finished_components
        ]
        if not candidates:
            return self.component_order[-1] if self.component_order else None
        if reported_total > 0:
            sized_candidates = [
                component_id for component_id in candidates
                if self.component_totals.get(component_id, 0) > 0
            ]
            if sized_candidates:
                return min(
                    sized_candidates,
                    key=lambda component_id: abs(self.component_totals[component_id] - reported_total)
                    / max(self.component_totals[component_id], reported_total),
                )
        return candidates[0]

    def emit_download_progress(self, force=False):
        now = time.monotonic()
        downloaded = sum(self.component_downloaded.values())
        total = sum(self.component_totals.values())
        if total <= 0:
            return

        elapsed = now - self.last_speed_sample_time
        if elapsed >= 0.35:
            delta = max(0.0, downloaded - self.last_speed_sample_bytes)
            instant_speed = delta / elapsed
            if instant_speed > 0:
                alpha = 1.0 - pow(2.718281828, -elapsed / 10.0)
                self.smoothed_speed = (
                    instant_speed if self.smoothed_speed <= 0
                    else self.smoothed_speed + alpha * (instant_speed - self.smoothed_speed)
                )
            self.last_speed_sample_time = now
            self.last_speed_sample_bytes = downloaded

        percent = min(96.0, downloaded / total * 96.0)
        self.last_percent = max(self.last_percent, percent)
        if not force and now - self.last_progress_emit < 0.45:
            return
        self.last_progress_emit = now
        remaining = max(0.0, total - downloaded)
        eta = remaining / self.smoothed_speed if self.smoothed_speed > 0 else 0.0
        speed_text = f"{human_size(self.smoothed_speed)}/s" if self.smoothed_speed > 0 else tr("speed_estimating")
        eta_text = seconds_text(eta) if eta > 0 else ""
        size_text = f"{human_size(downloaded)} / {human_size(total)}"
        self.progress_changed.emit(self.last_percent, speed_text, eta_text, size_text)

    def read_output(self):
        text = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self.output_log = (self.output_log + text)[-8000:]
        combined = self.output_buffer + text
        lines = re.split(r"[\r\n]+", combined)
        self.output_buffer = lines.pop()[-1000:] if lines else ""
        for line in lines:
            match = self.PROGRESS_RE.search(line)
            if match and not self.section:
                reported_id = match.group("format_id").strip()
                downloaded = numeric_progress(match.group("downloaded"))
                reported_total = numeric_progress(match.group("total")) or numeric_progress(match.group("estimate"))
                component_id = self.resolve_progress_component(reported_id, reported_total)
                if component_id is None:
                    continue
                if self.component_totals.get(component_id, 0) <= 0 and reported_total > 0:
                    self.component_totals[component_id] = reported_total
                self.component_downloaded[component_id] = max(
                    self.component_downloaded.get(component_id, 0.0), downloaded
                )
                status = match.group("status").strip()
                if status == "finished":
                    if self.component_totals.get(component_id, 0) > 0:
                        self.component_downloaded[component_id] = max(
                            self.component_downloaded[component_id], self.component_totals[component_id]
                        )
                    self.finished_components.add(component_id)
                self.emit_download_progress(force=status == "finished")
                continue
            if self.section:
                speed_match = self.FFMPEG_SPEED_RE.search(line)
                if speed_match:
                    self.ffmpeg_speed = float(speed_match.group("speed"))
                ffmpeg_match = self.FFMPEG_TIME_RE.search(line)
                if ffmpeg_match:
                    elapsed = (
                        int(ffmpeg_match.group("hours")) * 3600
                        + int(ffmpeg_match.group("minutes")) * 60
                        + float(ffmpeg_match.group("seconds"))
                    )
                    duration = max(0.001, self.section[1] - self.section[0])
                    percent = min(96.0, elapsed / duration * 96.0)
                    self.last_percent = max(self.last_percent, percent)
                    raw_speed = self.ffmpeg_speed
                    if raw_speed > 0:
                        self.smoothed_speed = raw_speed if self.smoothed_speed <= 0 else self.smoothed_speed * 0.85 + raw_speed * 0.15
                    speed_value = self.smoothed_speed
                    eta_seconds = (duration - elapsed) / speed_value if speed_value > 0 else 0
                    speed_text = f"{speed_value:.1f}x" if speed_value else tr("processing")
                    eta_text = seconds_text(eta_seconds) if eta_seconds > 0 else ""
                    self.progress_changed.emit(self.last_percent, speed_text, eta_text, tr("clip_processing"))
                    continue
            if any(marker in line for marker in ("[Merger]", "[VideoRemuxer]", "[Fixup")):
                self.last_percent = max(self.last_percent, 98.0)
                self.progress_changed.emit(self.last_percent, tr("muxing"), "", tr("muxing_detail"))

    def process_finished(self, exit_code, _status):
        if self.stop_reason == "pause":
            self.state = "paused"
            self.state_changed.emit("paused", "已暂停，可继续断点下载")
            return
        if self.stop_reason == "clear":
            self.state = "cleared"
            return
        success = exit_code == 0
        self.state = "finished" if success else "failed"
        self.state_changed.emit(self.state, tr("finished") if success else self.last_error())
        self.finished.emit(success)

    def process_error(self, _error):
        if not self.stop_reason:
            self.state = "failed"
            self.state_changed.emit("failed", self.process.errorString())

    def last_error(self):
        lines = [x.strip() for x in self.output_log.splitlines() if x.strip()]
        errors = [x for x in lines if "ERROR:" in x]
        return (errors[-1] if errors else (lines[-1] if lines else "下载进程异常结束"))[:260]

    def stop_process(self, reason):
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            self.stop_reason = reason
            self.process.terminate()
            QTimer.singleShot(2500, self.kill_if_running)

    def kill_if_running(self):
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()

    def pause(self):
        if self.state == "running":
            self.stop_process("pause")
            self.state_changed.emit("running", "正在安全暂停...")

    def resume(self):
        if self.state == "paused":
            self.start()

    def open_folder(self):
        output = Path(self.output_path)
        folder = output.parent.resolve()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def clear_files(self):
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            self.stop_reason = "clear"
            self.process.kill()
            self.process.waitForFinished(3000)
        output, candidates = Path(self.output_path), []
        if output.parent.exists():
            for item in output.parent.iterdir():
                if not item.is_file():
                    continue
                related = item.name == output.name or item.name.startswith(output.stem + ".") or item.name.startswith(output.stem + " [")
                temporary = item.suffix.lower() in {".part", ".ytdl", ".tmp", ".temp"} or ".part-" in item.name
                media = item.suffix.lower() in {".mp4", ".webm", ".mkv", ".m4a", ".jpg", ".jpeg", ".webp", ".png"}
                if related and (temporary or media):
                    try:
                        resolved = item.resolve()
                    except OSError:
                        resolved = item
                    if resolved not in self.preexisting_files:
                        candidates.append(item)
        for item in candidates:
            try:
                item.unlink(missing_ok=True)
            except OSError:
                pass
        self.state = "cleared"

    def hide_and_discard_cache(self):
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            self.stop_reason = "clear"
            self.process.kill()
            self.process.waitForFinished(3000)
        output = Path(self.output_path)
        if output.parent.exists():
            for item in output.parent.iterdir():
                if not item.is_file():
                    continue
                try:
                    resolved = item.resolve()
                except OSError:
                    resolved = item
                if resolved in self.preexisting_files:
                    continue
                if item == output:
                    if self.state == "finished":
                        continue
                    try:
                        item.unlink(missing_ok=True)
                    except OSError:
                        pass
                    continue
                related = item.name.startswith(output.stem + ".") or item.name.startswith(output.stem + " [")
                temporary = item.suffix.lower() in {".part", ".ytdl", ".tmp", ".temp"} or ".part-" in item.name
                intermediate = related and re.search(r"\.f\d+\.(mp4|webm|m4a|opus)$", item.name, re.I)
                if related and (temporary or intermediate):
                    try:
                        item.unlink(missing_ok=True)
                    except OSError:
                        pass
        self.state = "hidden"


class DownloadTaskWidget(QFrame):
    removed = pyqtSignal(object)

    def __init__(self, manager, thumbnail, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setObjectName("taskCard")
        self.root_layout = QVBoxLayout(self)
        root = self.root_layout
        root.setContentsMargins(10, 7, 10, 7)
        root.setSpacing(4)
        top = QHBoxLayout()
        self.task_cover = QLabel()
        cover = self.task_cover
        cover.setFixedSize(60, 34)
        cover.setStyleSheet("background:#111318; border-radius:5px;")
        pixmap = QPixmap()
        self.task_pixmap = None
        if thumbnail and pixmap.loadFromData(thumbnail):
            self.task_pixmap = pixmap
            cover.setPixmap(pixmap.scaled(cover.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
        top.addWidget(cover)
        text = QVBoxLayout()
        self.name_label = QLabel(Path(manager.output_path).name)
        self.name_label.setToolTip(manager.output_path)
        self.name_label.setStyleSheet("font-weight:600;")
        self.last_state = manager.state
        self.detail_label = QLabel(tr("waiting"))
        self.detail_label.setObjectName("taskDetail")
        text.addWidget(self.name_label)
        text.addWidget(self.detail_label)
        top.addLayout(text, 1)
        root.addLayout(top)
        row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        row.addWidget(self.progress, 1)
        self.percent_label = QLabel("0%")
        self.percent_label.setFixedWidth(44)
        self.percent_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.percent_label)
        root.addLayout(row)
        buttons = QHBoxLayout()
        buttons.setSpacing(5)
        self.pause_btn = QPushButton(tr("pause"))
        self.open_btn = QPushButton(tr("open_folder"))
        self.clear_btn = QPushButton(tr("clear"))
        self.hide_btn = QPushButton(tr("hide_task"))
        for button in (self.pause_btn, self.open_btn, self.clear_btn, self.hide_btn):
            button.setObjectName("taskSmall")
            button.setFixedHeight(25)
        self.clear_btn.setObjectName("danger")
        self.pause_btn.clicked.connect(self.pause_or_resume)
        self.open_btn.clicked.connect(manager.open_folder)
        self.clear_btn.clicked.connect(self.request_clear)
        self.hide_btn.clicked.connect(self.request_hide)
        buttons.addWidget(self.pause_btn)
        buttons.addWidget(self.open_btn)
        buttons.addWidget(self.clear_btn)
        buttons.addStretch()
        buttons.addWidget(self.hide_btn)
        root.addLayout(buttons)
        manager.progress_changed.connect(self.update_progress)
        manager.state_changed.connect(self.update_state)
        manager.finished.connect(self.download_finished)
        self.set_scale(1.0)

    def set_scale(self, scale):
        self.setMaximumHeight(max(86, round(116 * scale)))
        self.root_layout.setContentsMargins(
            round(10 * scale), round(7 * scale), round(10 * scale), round(7 * scale)
        )
        self.root_layout.setSpacing(max(2, round(4 * scale)))
        self.task_cover.setFixedSize(max(44, round(60 * scale)), max(25, round(34 * scale)))
        self.percent_label.setFixedWidth(max(34, round(44 * scale)))
        if self.task_pixmap:
            self.task_cover.setPixmap(self.task_pixmap.scaled(
                self.task_cover.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            ))
        for button in (self.pause_btn, self.open_btn, self.clear_btn, self.hide_btn):
            button.setFixedHeight(max(20, round(25 * scale)))

    def update_progress(self, percent, speed, eta, size):
        self.progress.setValue(int(max(0, min(100, percent)) * 10))
        self.percent_label.setText(f"{percent:.1f}%")
        parts = [x for x in (size, speed, tr("remaining", value=eta) if eta and eta != "NA" else "") if x and x != "NA"]
        self.detail_label.setText(" · ".join(parts) or tr("downloading"))

    def update_state(self, state, detail):
        self.last_state = state
        self.detail_label.setText(detail or state)
        self.pause_btn.setText(tr("resume") if state == "paused" else tr("pause"))
        if state in ("finished", "failed", "cleared"):
            self.pause_btn.setEnabled(False)

    def download_finished(self, success):
        if success:
            self.progress.setValue(1000)
            self.percent_label.setText("100%")

    def pause_or_resume(self):
        self.manager.resume() if self.manager.state == "paused" else self.manager.pause()

    def retranslate_ui(self):
        self.pause_btn.setText(tr("resume") if self.manager.state == "paused" else tr("pause"))
        self.open_btn.setText(tr("open_folder"))
        self.clear_btn.setText(tr("clear"))
        self.hide_btn.setText(tr("hide_task"))
        if self.manager.state == "waiting":
            self.detail_label.setText(tr("waiting"))
        elif self.manager.state == "finished":
            self.detail_label.setText(tr("finished"))

    def request_clear(self):
        answer = QMessageBox.question(self, "清除任务", "将停止任务，并删除成品、未完成文件及相关临时文件。是否继续？",
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self.manager.clear_files()
            self.removed.emit(self)

    def request_hide(self):
        if self.manager.state in ("running", "paused"):
            answer = QMessageBox.question(
                self, "隐藏任务", "将停止任务并删除未完成缓存，但不会删除已经保存好的文件。是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.manager.hide_and_discard_cache()
        self.removed.emit(self)


class YoutubeDownloader(QMainWindow):
    def __init__(self):
        global CURRENT_LANGUAGE
        super().__init__()
        self.settings = QSettings(ORG_NAME, APP_NAME)
        saved_language = str(self.settings.value("language", "zh"))
        CURRENT_LANGUAGE = saved_language if saved_language in LANGUAGE_CODES else "zh"
        self.info, self.thumbnail_bytes, self.pending_download = None, b"", None
        self.info_worker = None
        self.tasks = []
        self.clip_start = self.clip_end = 0.0
        self.clip_applied = False
        self.ui_scale = 0.0
        self._aspect_adjusting = False
        self._pending_aspect_size = None
        self._aspect_timer = QTimer(self)
        self._aspect_timer.setSingleShot(True)
        self._aspect_timer.timeout.connect(self.apply_pending_aspect_size)
        self.dark_mode = self.settings.value("theme", "light") == "dark"
        self.section_labels = []
        self.setWindowTitle(APP_NAME)
        app_icon = bundled_path("icon.ico")
        if app_icon.exists():
            self.setWindowIcon(QIcon(str(app_icon)))
        self.resize(1020, 830)
        self.setMinimumSize(860, 700)
        self.build_ui()
        self.apply_responsive_scale(force=True)

    def section_label(self, text):
        label = QLabel(text)
        label.setObjectName("sectionTitle")
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.section_labels.append(label)
        return label

    def _button_icon(self, name):
        color = "#f1f3f7" if self.dark_mode else TEXT
        if qta is not None:
            try:
                return qta.icon(name, color=color)
            except Exception:
                pass
        standard_icons = {
            "fa5s.play": QStyle.StandardPixmap.SP_MediaPlay,
            "fa5s.pause": QStyle.StandardPixmap.SP_MediaPause,
        }
        return self.style().standardIcon(standard_icons.get(name, QStyle.StandardPixmap.SP_FileIcon))

    def set_play_button_state(self, playing):
        icon = self._button_icon("fa5s.pause") if playing else self._button_icon("fa5s.play")
        self.play_btn.setIcon(icon)
        self.play_btn.setToolTip(tr("pause") if playing else tr("play"))

    def sync_clip_control_sizes(self, scale):
        for button in self.clip_control_buttons:
            button.setMinimumSize(0, 0)
            button.setMaximumSize(16777215, 16777215)
            button.ensurePolished()
        reference = self.frame_back_btn.sizeHint()
        width = max(44, reference.width())
        height = max(26, reference.height())
        icon_size = max(12, round(15 * scale))
        for button in self.clip_control_buttons:
            button.setFixedSize(width, height)
            button.setIconSize(QSize(icon_size, icon_size))

    def build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        page = QVBoxLayout(root)
        self.page_layout = page
        page.setContentsMargins(24, 18, 24, 20)
        page.setSpacing(12)
        header = QHBoxLayout()
        brand = QVBoxLayout()
        brand.setContentsMargins(0, 0, 0, 0)
        brand.setSpacing(2)
        title, subtitle = QLabel("YouTube Downloader"), QLabel("Designed by Solveil")
        self.brand_title, self.brand_subtitle = title, subtitle
        title.setObjectName("appTitle")
        subtitle.setObjectName("brandSubtitle")
        brand.addWidget(title)
        brand.addWidget(subtitle)
        header.addLayout(brand)
        header.addStretch()
        self.language_btn = LanguageButton()
        self.language_btn.setToolTip(tr("language_tip"))
        self.language_btn.clicked.connect(self.show_language_menu)
        self.language_menu = QMenu(self)
        self.language_actions = {}
        for code in LANGUAGE_CODES:
            action = QAction(LANGUAGE_NAMES[code], self.language_menu)
            action.setCheckable(True)
            action.triggered.connect(lambda _checked=False, language=code: self.set_language(language))
            self.language_menu.addAction(action)
            self.language_actions[code] = action
        header.addWidget(self.language_btn, 0, Qt.AlignmentFlag.AlignTop)
        self.theme_btn = QPushButton("☾" if self.dark_mode else "☀")
        self.theme_btn.setObjectName("themeSwitch")
        self.theme_btn.setToolTip(tr("theme_tip"))
        self.theme_btn.clicked.connect(self.toggle_theme)
        header.addWidget(self.theme_btn, 0, Qt.AlignmentFlag.AlignTop)
        page.addLayout(header)

        url_card = QFrame()
        url_card.setObjectName("card")
        url_layout = QHBoxLayout(url_card)
        self.url_layout = url_layout
        url_layout.setContentsMargins(14, 14, 14, 14)
        url_layout.setSpacing(8)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText(tr("url_placeholder"))
        self.url_edit.setClearButtonEnabled(True)
        self.url_edit.returnPressed.connect(self.parse_current_url)
        self.parse_btn = QPushButton(tr("paste_parse"))
        self.parse_btn.setObjectName("primary")
        self.parse_btn.clicked.connect(self.paste_and_parse)
        self.loading_spinner = LoadingSpinner()
        url_layout.addWidget(self.url_edit, 1)
        url_layout.addWidget(self.parse_btn)
        url_layout.addWidget(self.loading_spinner)
        page.addWidget(url_card)

        body = QHBoxLayout()
        self.body_layout = body
        body.setSpacing(16)
        left_card = QFrame()
        left_card.setObjectName("card")
        left = QVBoxLayout(left_card)
        self.left_layout = left
        left.setContentsMargins(16, 16, 16, 16)
        left.setSpacing(9)
        self.cover_label = CoverLabel(tr("no_cover"))
        self.cover_label.setObjectName("cover")
        self.cover_frame = AspectRatioContainer(self.cover_label)
        left.addWidget(self.cover_frame)
        self.video_title = QLabel(tr("title_placeholder"))
        self.video_title.setWordWrap(True)
        self.video_title.setObjectName("videoTitle")
        self.video_title.setMaximumHeight(48)
        left.addWidget(self.video_title)
        self.meta_label = QLabel("—")
        self.meta_label.setObjectName("subtitle")
        left.addWidget(self.meta_label)
        cover_actions = QHBoxLayout()
        self.cover_check, self.save_cover_btn = QCheckBox(tr("cover_with_video")), QPushButton(tr("save_cover"))
        self.save_cover_btn.setEnabled(False)
        self.save_cover_btn.clicked.connect(self.save_cover)
        cover_actions.addWidget(self.cover_check)
        cover_actions.addStretch()
        cover_actions.addWidget(self.save_cover_btn)
        left.addLayout(cover_actions)
        body.addWidget(left_card, 5)

        right_card = QFrame()
        right_card.setObjectName("card")
        right = QVBoxLayout(right_card)
        self.right_layout = right
        right.setContentsMargins(16, 16, 16, 16)
        right.setSpacing(10)
        self.format_section = self.section_label(tr("download_format"))
        right.addWidget(self.format_section)
        self.format_combo = ChevronComboBox()
        self.format_combo.setEnabled(False)
        self.format_combo.setMaxVisibleItems(14)
        right.addWidget(self.format_combo)
        right.addSpacing(4)
        self.filename_section = self.section_label(tr("filename"))
        right.addWidget(self.filename_section)
        self.filename_edit = QLineEdit()
        self.filename_edit.setPlaceholderText(tr("filename_placeholder"))
        right.addWidget(self.filename_edit)
        right.addSpacing(4)
        self.range_section = self.section_label(tr("download_range"))
        right.addWidget(self.range_section)
        self.range_combo = ChevronComboBox()
        self.range_combo.addItems([tr("full_video"), tr("select_clip")])
        self.range_combo.currentIndexChanged.connect(self.range_mode_changed)
        right.addWidget(self.range_combo)
        self.range_label = QLabel(tr("full_video_info"))
        self.range_label.setObjectName("subtitle")
        self.range_label.setWordWrap(True)
        right.addWidget(self.range_label)
        right.addStretch()
        self.audio_combo = ChevronComboBox()
        self.audio_combo.addItem(tr("download_audio"), None)
        self.audio_combo.setEnabled(False)
        self.audio_combo.setMaxVisibleItems(8)
        self.audio_combo.currentIndexChanged.connect(self.audio_quality_selected)
        right.addWidget(self.audio_combo)
        self.download_btn = QPushButton(tr("add_task"))
        self.download_btn.setObjectName("primary")
        self.download_btn.setMinimumHeight(42)
        self.download_btn.setEnabled(False)
        self.download_btn.clicked.connect(self.prepare_download)
        right.addWidget(self.download_btn)
        body.addWidget(right_card, 4)
        page.addLayout(body)

        bottom = QHBoxLayout()
        self.bottom_layout = bottom
        bottom.setSpacing(16)
        task_card = QFrame()
        task_card.setObjectName("card")
        task_box = QVBoxLayout(task_card)
        self.task_box_layout = task_box
        task_box.setContentsMargins(14, 12, 14, 12)
        task_header = QHBoxLayout()
        self.tasks_section = self.section_label(tr("tasks"))
        task_header.addWidget(self.tasks_section)
        task_header.addStretch()
        self.task_count = QLabel("0 / 5")
        self.task_count.setObjectName("subtitle")
        task_header.addWidget(self.task_count)
        task_box.addLayout(task_header)
        self.task_scroll = QScrollArea()
        self.task_scroll.setWidgetResizable(True)
        self.task_scroll.setMinimumHeight(210)
        self.task_scroll.setFrameShape(QFrame.Shape.NoFrame)
        host = QWidget()
        self.task_layout = QVBoxLayout(host)
        self.task_layout.setContentsMargins(0, 0, 0, 0)
        self.task_layout.setSpacing(8)
        self.task_layout.addStretch()
        self.task_scroll.setWidget(host)
        task_box.addWidget(self.task_scroll, 1)
        bottom.addWidget(task_card, 5)

        self.clip_panel = QFrame()
        self.clip_panel.setObjectName("card")
        clip_box = QVBoxLayout(self.clip_panel)
        self.clip_box_layout = clip_box
        clip_box.setContentsMargins(14, 12, 14, 12)
        clip_box.setSpacing(7)
        clip_header = QHBoxLayout()
        self.clip_section = self.section_label(tr("clip_panel"))
        clip_header.addWidget(self.clip_section)
        clip_header.addStretch()
        self.preview_spinner = LoadingSpinner()
        clip_header.addWidget(self.preview_spinner)
        self.clip_time_label = QLabel("00:00.000 / 00:00.000")
        self.clip_time_label.setObjectName("subtitle")
        clip_header.addWidget(self.clip_time_label)
        clip_box.addLayout(clip_header)
        self.clip_video = ClickableVideoWidget()
        self.clip_video.setMinimumHeight(170)
        self.clip_video.setStyleSheet("background:#090a0d; border-radius:8px;")
        self.clip_video.setToolTip(tr("preview_tip"))
        self.clip_video.clicked.connect(self.toggle_preview)
        self.clip_video_frame = AspectRatioContainer(self.clip_video)
        clip_box.addWidget(self.clip_video_frame, 1)
        self.clip_timeline = RangeTimeline()
        self.clip_timeline.seek_requested.connect(self.seek_preview)
        clip_box.addWidget(self.clip_timeline)
        clip_controls = QHBoxLayout()
        self.play_btn = QPushButton()
        self.play_btn.setIcon(self._button_icon("fa5s.pause"))
        self.frame_back_btn = QPushButton(tr("frame_back"))
        self.frame_forward_btn = QPushButton(tr("frame_forward"))
        self.play_btn.setToolTip(tr("play"))
        self.play_btn.clicked.connect(self.toggle_preview)
        self.frame_back_btn.clicked.connect(lambda: self.step_preview_frame(-1))
        self.frame_forward_btn.clicked.connect(lambda: self.step_preview_frame(1))
        self.left_boundary_btn = QPushButton("[")
        self.right_boundary_btn = QPushButton("]")
        self.left_boundary_btn.setObjectName("clipBoundary")
        self.right_boundary_btn.setObjectName("clipBoundary")
        self.cancel_clip_btn = QPushButton(tr("cancel"))
        self.apply_clip_btn = QPushButton(tr("apply"))
        self.apply_clip_btn.setObjectName("primary")
        self.left_boundary_btn.clicked.connect(self.set_clip_start)
        self.right_boundary_btn.clicked.connect(self.set_clip_end)
        self.cancel_clip_btn.clicked.connect(lambda: self.cancel_clip_selection(True))
        self.apply_clip_btn.clicked.connect(self.apply_clip_selection)
        clip_controls.addWidget(self.frame_back_btn)
        clip_controls.addWidget(self.frame_forward_btn)
        clip_controls.addWidget(self.play_btn)
        clip_controls.addWidget(self.left_boundary_btn)
        clip_controls.addWidget(self.right_boundary_btn)
        clip_controls.addStretch()
        clip_controls.addWidget(self.cancel_clip_btn)
        clip_controls.addWidget(self.apply_clip_btn)
        self.clip_control_buttons = [
            self.frame_back_btn, self.frame_forward_btn, self.play_btn,
            self.left_boundary_btn, self.right_boundary_btn,
            self.cancel_clip_btn, self.apply_clip_btn,
        ]
        clip_box.addLayout(clip_controls)
        self.clip_panel.hide()
        bottom.addWidget(self.clip_panel, 4)
        page.addLayout(bottom, 1)

        self.preview_player = None
        self.preview_audio = None
        self.preview_frame_signal_supported = False

    def ensure_preview_player(self):
        if self.preview_player is not None:
            return True
        try:
            self.preview_player = QMediaPlayer(self)
            self.preview_audio = QAudioOutput(self)
            self.preview_audio.setVolume(0.45)
            self.preview_player.setAudioOutput(self.preview_audio)
            self.preview_player.setVideoOutput(self.clip_video)
            self.preview_player.positionChanged.connect(self.preview_position_changed)
            self.preview_player.playbackStateChanged.connect(self.preview_state_changed)
            self.preview_player.mediaStatusChanged.connect(self.preview_media_status_changed)
            self.preview_player.errorOccurred.connect(self.preview_error)
            video_sink_method = getattr(self.clip_video, "videoSink", None)
            if callable(video_sink_method):
                video_sink = video_sink_method()
                if video_sink is not None and hasattr(video_sink, "videoFrameChanged"):
                    video_sink.videoFrameChanged.connect(self.preview_frame_ready)
                    self.preview_frame_signal_supported = True
            return True
        except Exception as exc:
            self.preview_player = None
            self.preview_audio = None
            QMessageBox.warning(self, "预览初始化失败", f"Qt 视频预览组件无法初始化：\n{exc}")
            return False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "page_layout"):
            self.apply_responsive_scale()
        if self._aspect_adjusting or self.isMaximized() or not event.oldSize().isValid():
            return
        old_size, new_size = event.oldSize(), event.size()
        width_change = abs(new_size.width() - old_size.width()) / max(1, old_size.width())
        height_change = abs(new_size.height() - old_size.height()) / max(1, old_size.height())
        if width_change >= height_change:
            target_width = max(860, new_size.width())
            target_height = max(700, round(target_width / WINDOW_ASPECT_RATIO))
        else:
            target_height = max(700, new_size.height())
            target_width = max(860, round(target_height * WINDOW_ASPECT_RATIO))
        if abs(target_width - new_size.width()) > 1 or abs(target_height - new_size.height()) > 1:
            self._pending_aspect_size = (target_width, target_height)
            self._aspect_timer.start(0)

    def apply_pending_aspect_size(self):
        if self.isMaximized() or not self._pending_aspect_size:
            return
        width, height = self._pending_aspect_size
        self._pending_aspect_size = None
        self._aspect_adjusting = True
        self.resize(width, height)
        self._aspect_adjusting = False

    def apply_responsive_scale(self, force=False):
        scale = round(max(0.72, min(1.0, self.width() / 1180, self.height() / 960)), 2)
        if not force and scale == self.ui_scale:
            return
        self.ui_scale = scale

        def margins(layout, values):
            layout.setContentsMargins(*(max(0, round(value * scale)) for value in values))

        margins(self.page_layout, (24, 18, 24, 20))
        self.page_layout.setSpacing(max(8, round(12 * scale)))
        margins(self.url_layout, (14, 14, 14, 14))
        self.url_layout.setSpacing(max(5, round(8 * scale)))
        self.body_layout.setSpacing(max(10, round(16 * scale)))
        margins(self.left_layout, (16, 16, 16, 16))
        self.left_layout.setSpacing(max(6, round(9 * scale)))
        margins(self.right_layout, (16, 16, 16, 16))
        self.right_layout.setSpacing(max(7, round(10 * scale)))
        self.bottom_layout.setSpacing(max(10, round(16 * scale)))
        margins(self.task_box_layout, (14, 12, 14, 12))
        margins(self.clip_box_layout, (14, 12, 14, 12))
        self.clip_box_layout.setSpacing(max(5, round(7 * scale)))
        self.task_layout.setSpacing(max(5, round(8 * scale)))

        self.cover_frame.set_scale(scale)
        self.clip_video_frame.set_scale(scale)
        self.video_title.setMaximumHeight(max(35, round(48 * scale)))
        self.brand_title.setMinimumHeight(max(34, round(44 * scale)))
        self.brand_subtitle.setMinimumHeight(max(17, round(20 * scale)))
        self.task_scroll.setMinimumHeight(max(150, round(210 * scale)))
        self.download_btn.setMinimumHeight(max(31, round(42 * scale)))
        self.clip_video.setMinimumHeight(max(122, round(170 * scale)))
        self.clip_timeline.set_scale(scale)
        self.loading_spinner.set_scale(scale)
        self.preview_spinner.set_scale(scale)
        self.format_combo.set_scale(scale)
        self.range_combo.set_scale(scale)
        self.audio_combo.set_scale(scale)
        for label in self.section_labels:
            label.setMinimumHeight(max(20, round(26 * scale)))
        for _manager, card in self.tasks:
            card.set_scale(scale)
        self.apply_style(scale)

    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self.settings.setValue("theme", "dark" if self.dark_mode else "light")
        self.theme_btn.setText("☾" if self.dark_mode else "☀")
        self.apply_style(self.ui_scale or 1.0)

    def show_language_menu(self):
        for code, action in self.language_actions.items():
            action.setChecked(code == CURRENT_LANGUAGE)
        position = self.language_btn.mapToGlobal(QPoint(0, self.language_btn.height() + 2))
        self.language_menu.popup(position)

    def set_language(self, language):
        global CURRENT_LANGUAGE
        if language not in LANGUAGE_CODES or language == CURRENT_LANGUAGE:
            return
        CURRENT_LANGUAGE = language
        self.settings.setValue("language", language)
        self.apply_language()

    def apply_language(self):
        self.language_btn.setToolTip(tr("language_tip"))
        self.theme_btn.setToolTip(tr("theme_tip"))
        self.url_edit.setPlaceholderText(tr("url_placeholder"))
        self.parse_btn.setText(tr("paste_parse"))
        if not self.thumbnail_bytes:
            self.cover_label.setText(tr("no_cover"))
        if not self.info:
            self.video_title.setText(tr("title_placeholder"))
        self.cover_check.setText(tr("cover_with_video"))
        self.save_cover_btn.setText(tr("save_cover"))
        self.format_section.setText(tr("download_format"))
        self.filename_section.setText(tr("filename"))
        self.filename_edit.setPlaceholderText(tr("filename_placeholder"))
        self.range_section.setText(tr("download_range"))
        range_index = self.range_combo.currentIndex()
        self.range_combo.blockSignals(True)
        self.range_combo.clear()
        self.range_combo.addItems([tr("full_video"), tr("select_clip")])
        self.range_combo.setCurrentIndex(max(0, range_index))
        self.range_combo.blockSignals(False)
        if range_index == 0:
            self.range_label.setText(tr("full_video_info"))
        elif self.clip_applied:
            value = f"{seconds_text_ms(self.clip_start)} – {seconds_text_ms(self.clip_end)}"
            self.range_label.setText(tr("selected_range", value=value))
        else:
            value = f"{seconds_text_ms(self.clip_start)} – {seconds_text_ms(self.clip_end)}"
            self.range_label.setText(tr("choosing_range", value=value))
        self.download_btn.setText(tr("add_task"))
        self.tasks_section.setText(tr("tasks"))
        self.clip_section.setText(tr("clip_panel"))
        self.clip_video.setToolTip(tr("preview_tip"))
        self.frame_back_btn.setText(tr("frame_back"))
        self.frame_forward_btn.setText(tr("frame_forward"))
        self.cancel_clip_btn.setText(tr("cancel"))
        self.apply_clip_btn.setText(tr("apply"))
        playing = bool(self.preview_player and self.preview_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState)
        self.set_play_button_state(playing)
        if self.info:
            self.fill_audio_formats(self.info)
        else:
            self.audio_combo.blockSignals(True)
            self.audio_combo.clear()
            self.audio_combo.addItem(tr("download_audio"), None)
            self.audio_combo.blockSignals(False)
        for _manager, card in self.tasks:
            card.retranslate_ui()
        self.sync_clip_control_sizes(self.ui_scale or 1.0)

    def apply_style(self, scale=1.0):
        px = lambda value, minimum=1: max(minimum, round(value * scale))
        if self.dark_mode:
            bg, card, text, muted = "#15171c", "#1d2027", "#f1f3f7", "#a5abb6"
            border, accent, accent_hover = "#343842", "#7987ff", "#6878ef"
            field, button, button_hover = "#242832", "#2b303a", "#363c48"
            disabled, progress_track, popup_hover = "#22252c", "#343943", "#343a4b"
            danger_bg = "#3a252a"
        else:
            bg, card, text, muted = BG, CARD, TEXT, MUTED
            border, accent, accent_hover = BORDER, ACCENT, ACCENT_HOVER
            field, button, button_hover = "#fbfcfd", "#eef0f4", "#e3e6eb"
            disabled, progress_track, popup_hover = "#f0f1f3", "#e7e9ee", "#eef0ff"
            danger_bg = "#fff0f1"
        self.format_combo.set_theme(self.dark_mode)
        self.range_combo.set_theme(self.dark_mode)
        self.audio_combo.set_theme(self.dark_mode)
        self.clip_timeline.set_theme(self.dark_mode)
        self.language_btn.set_theme(self.dark_mode)
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{ background:{bg}; color:{text}; font-family:'Segoe UI','Microsoft YaHei UI'; font-size:{px(13, 10)}px; }}
            QFrame#card, QFrame#taskCard {{ background:{card}; border:1px solid {border}; border-radius:{px(12, 8)}px; }}
            QLabel#appTitle {{ font-family:'Eras Demi ITC'; font-size:{px(31, 23)}px; font-weight:400; }}
            QLabel#brandSubtitle {{ color:{muted}; font-family:'Palatino Linotype'; font-size:{px(13, 11)}px; font-style:italic; font-weight:600; letter-spacing:{px(1)}px; padding-left:{px(3, 2)}px; }}
            QLabel#subtitle, QLabel#taskDetail {{ color:{muted}; }}
            QLabel#cover {{ background:#101218; color:#90949d; border-radius:{px(9, 6)}px; }}
            QLabel#videoTitle {{ font-size:{px(16, 12)}px; font-weight:650; }}
            QLabel#sectionTitle {{ background:{button}; font-size:{px(14, 11)}px; font-weight:700; padding-left:{px(5, 3)}px; border-radius:{px(4, 3)}px; }}
            QLineEdit, QComboBox {{ background:{field}; border:1px solid {border}; border-radius:{px(7, 5)}px; padding:{px(8, 5)}px {px(10, 7)}px; min-height:{px(20, 15)}px; }}
            QLineEdit:focus, QComboBox:focus {{ border:1px solid {accent}; }}
            QComboBox {{ padding-right:{px(30, 22)}px; }}
            QComboBox::drop-down {{ subcontrol-origin:padding; subcontrol-position:top right; width:{px(28, 21)}px; border:0; background:transparent; }}
            QComboBox::down-arrow {{ image:none; width:0; height:0; }}
            QPushButton#comboArrowButton, QPushButton#comboArrowButton:hover {{ background:transparent; border:0; padding:0; margin:0; }}
            QPushButton#clipBoundary {{ padding:0; margin:0; text-align:center; font-family:'Segoe UI Symbol'; }}
            QComboBox QAbstractItemView {{ background:{card}; border:1px solid {border}; outline:0; margin:0; padding:{px(3, 2)}px; selection-background-color:{popup_hover}; selection-color:{text}; }}
            QComboBox QAbstractItemView::item {{ border:0; outline:0; padding:{px(7, 5)}px; min-height:{px(24, 18)}px; }}
            QComboBox QAbstractItemView::item:hover {{ background:{popup_hover}; }}
            QFrame#comboPopup {{ background:{card}; border:1px solid {border}; margin:0; padding:0; }}
            QListWidget#comboPopupList {{ background:{card}; color:{text}; border:0; outline:0; margin:0; padding:{px(2, 1)}px; }}
            QListWidget#comboPopupList::item {{ border:0; outline:0; margin:0; padding:0 {px(7, 5)}px; }}
            QListWidget#comboPopupList::item:hover, QListWidget#comboPopupList::item:selected {{ background:{popup_hover}; color:{text}; border:0; outline:0; }}
            QPushButton {{ background:{button}; border:0; border-radius:{px(7, 5)}px; padding:{px(8, 5)}px {px(13, 9)}px; font-weight:600; }}
            QPushButton:hover {{ background:{button_hover}; }} QPushButton:disabled {{ color:#8e949f; background:{disabled}; }}
            QPushButton#primary {{ color:white; background:{accent}; }} QPushButton#primary:hover {{ background:{accent_hover}; }}
            QPushButton#danger {{ color:{DANGER}; background:{danger_bg}; }}
            QPushButton#themeSwitch {{ font-family:'Segoe UI Symbol'; font-size:{px(17, 13)}px; min-width:{px(22, 17)}px; padding:{px(6, 4)}px; }}
            QPushButton#languageSwitch {{ min-width:{px(31, 24)}px; min-height:{px(25, 20)}px; padding:{px(3, 2)}px; }}
            QMenu {{ background:{card}; color:{text}; border:1px solid {border}; padding:{px(5, 3)}px; }}
            QMenu::item {{ padding:{px(7, 5)}px {px(22, 16)}px; border-radius:{px(4, 3)}px; }}
            QMenu::item:selected {{ background:{popup_hover}; }}
            QPushButton#taskSmall, QPushButton#danger {{ padding:{px(3, 2)}px {px(7, 5)}px; min-height:{px(18, 14)}px; font-size:{px(11, 9)}px; }}
            QProgressBar {{ border:0; background:{progress_track}; border-radius:{px(4, 3)}px; min-height:{px(8, 6)}px; max-height:{px(8, 6)}px; }}
            QProgressBar::chunk {{ background:{accent}; border-radius:{px(4, 3)}px; }} QScrollArea {{ background:transparent; }}
            QSlider::groove:horizontal {{ height:{px(5, 4)}px; background:{progress_track}; border-radius:{px(2)}px; }}
            QSlider::handle:horizontal {{ width:{px(15, 11)}px; margin:-{px(5, 4)}px 0; background:{accent}; border-radius:{px(7, 5)}px; }}
        """)
        if hasattr(self, "play_btn"):
            playing = bool(
                self.preview_player is not None
                and self.preview_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
            )
            self.set_play_button_state(playing)
            self.sync_clip_control_sizes(scale)

    def paste_and_parse(self):
        self.url_edit.setText(QApplication.clipboard().text().strip())
        self.parse_current_url()

    def parse_current_url(self):
        url = self.url_edit.text().strip()
        if not is_supported_url(url):
            QMessageBox.warning(self, "链接无效", "请输入有效的 YouTube 视频链接")
            return
        self.parse_btn.setEnabled(False)
        self.download_btn.setEnabled(False)
        self.audio_combo.setEnabled(False)
        self.loading_spinner.start()
        self.info_worker = InfoWorker(url)
        self.info_worker.result.connect(self.info_ready)
        self.info_worker.failed.connect(self.info_failed)
        self.info_worker.finished.connect(self.parsing_finished)
        self.info_worker.start()

    def parsing_finished(self):
        self.parse_btn.setEnabled(True)
        self.loading_spinner.stop()

    def info_ready(self, info, thumbnail):
        self.info, self.thumbnail_bytes = info, thumbnail
        self.video_title.setText(info.get("title") or "未命名视频")
        duration = info.get("duration") or 0
        self.clip_start, self.clip_end = 0, float(duration)
        uploader = info.get("uploader") or info.get("channel") or "未知频道"
        self.meta_label.setText(f"{uploader}  ·  {seconds_text(duration)}")
        self.filename_edit.setText(clean_filename(info.get("title")))
        self.filename_edit.setToolTip(self.filename_edit.text())
        self.filename_edit.setCursorPosition(0)
        self.fill_formats(info)
        self.fill_audio_formats(info)
        self.refresh_cover()
        self.save_cover_btn.setEnabled(bool(thumbnail))
        self.download_btn.setEnabled(self.format_combo.count() > 0)
        self.range_label.setText(tr("full_video_info"))
        self.range_combo.blockSignals(True)
        self.range_combo.setCurrentIndex(0)
        self.range_combo.blockSignals(False)
        self.cancel_clip_selection(reset_combo=False)

    def info_failed(self, message):
        QMessageBox.critical(self, "解析失败", message)

    def fill_formats(self, info):
        self.format_combo.clear()
        formats = [
            f for f in info.get("formats", [])
            if f.get("vcodec") not in (None, "none", "images")
            and f.get("format_id")
            and is_direct_media_format(f)
        ]
        max_height = max((quality_height(f) for f in formats), default=0)
        if max_height >= 1080:
            formats = [f for f in formats if quality_height(f) >= 1080]
        audio_formats = [
            f for f in info.get("formats", [])
            if f.get("vcodec") == "none"
            and f.get("acodec") not in (None, "none")
            and f.get("format_id")
            and is_direct_media_format(f)
        ]
        formats.sort(key=default_format_key, reverse=True)
        for fmt in formats:
            ext = (fmt.get("ext") or "").lower()
            has_audio = fmt.get("acodec") not in (None, "none")
            if ext not in {"mp4", "webm", "mkv"}:
                continue

            compatible_audio = []
            if not has_audio:
                for audio in audio_formats:
                    audio_ext = str(audio.get("ext") or "").lower()
                    audio_codec = str(audio.get("acodec") or "").lower()
                    if ext == "mp4" and audio_ext == "m4a" and audio_codec.startswith(("mp4a", "aac", "alac")):
                        compatible_audio.append(audio)
                    elif ext == "webm" and audio_ext == "webm" and audio_codec.startswith(("opus", "vorbis")):
                        compatible_audio.append(audio)
                    elif ext == "mkv":
                        compatible_audio.append(audio)
                if not compatible_audio:
                    continue

            best_audio = max(compatible_audio, key=lambda f: f.get("abr") or f.get("tbr") or 0, default={})
            audio_size = best_audio.get("filesize") or best_audio.get("filesize_approx") or 0
            if not audio_size and best_audio.get("tbr") and info.get("duration"):
                audio_size = float(best_audio["tbr"]) * float(info["duration"]) * 1000 / 8
            video_size = estimated_size_bytes(fmt, info.get("duration"), 0)
            if has_audio:
                selector = str(fmt["format_id"])
                progress_components = [{"format_id": str(fmt["format_id"]), "size": video_size}]
            else:
                selector = f"{fmt['format_id']}+{best_audio['format_id']}"
                progress_components = [
                    {"format_id": str(fmt["format_id"]), "size": video_size},
                    {"format_id": str(best_audio["format_id"]), "size": audio_size},
                ]
            data = dict(fmt)
            data["selector"] = selector
            data["merge_ext"] = ext
            data["progress_components"] = progress_components
            data["estimated_bytes"] = estimated_size_bytes(
                fmt, info.get("duration"), 0 if has_audio else audio_size
            )
            self.format_combo.addItem(format_label(fmt, info.get("duration"), audio_size), data)
        self.format_combo.setEnabled(self.format_combo.count() > 0)

    def fill_audio_formats(self, info):
        self.audio_combo.blockSignals(True)
        self.audio_combo.clear()
        self.audio_combo.addItem(tr("download_audio"), None)
        candidates = [
            fmt for fmt in info.get("formats", [])
            if fmt.get("format_id")
            and fmt.get("vcodec") == "none"
            and fmt.get("acodec") not in (None, "none")
            and is_direct_media_format(fmt)
        ]
        candidates.sort(key=lambda fmt: (fmt.get("abr") or fmt.get("tbr") or 0, fmt.get("filesize") or 0), reverse=True)
        seen = set()
        for fmt in candidates:
            ext = (fmt.get("ext") or "m4a").lower()
            bitrate = float(fmt.get("abr") or fmt.get("tbr") or 0)
            quality_key = (ext, round(bitrate))
            if quality_key in seen:
                continue
            seen.add(quality_key)
            size = estimated_size_bytes(fmt, info.get("duration"))
            bitrate_text = f"{bitrate:.0f} kbps" if bitrate else "音质未知"
            label = f"{ext.upper()} · {bitrate_text} · {human_size(size)}"
            data = dict(fmt)
            data.update({
                "selector": str(fmt["format_id"]),
                "merge_ext": None,
                "audio_ext": ext,
                "estimated_bytes": size,
            })
            self.audio_combo.addItem(label, data)
        self.audio_combo.setCurrentIndex(0)
        self.audio_combo.setEnabled(self.audio_combo.count() > 1)
        self.audio_combo.blockSignals(False)

    def refresh_cover(self):
        self.cover_label.set_image(self.thumbnail_bytes)

    def save_cover(self):
        if not self.thumbnail_bytes:
            return
        initial = self.settings.value("last_folder", str(Path.home()))
        path, _ = QFileDialog.getSaveFileName(self, "保存封面", str(Path(initial) / (clean_filename(self.filename_edit.text()) + ".jpg")), "JPEG 图片 (*.jpg)")
        if path:
            if not path.lower().endswith((".jpg", ".jpeg")):
                path += ".jpg"
            try:
                Path(path).write_bytes(self.thumbnail_bytes)
                self.settings.setValue("last_folder", str(Path(path).parent))
                QMessageBox.information(self, "保存成功", "封面已保存")
            except OSError as exc:
                QMessageBox.warning(self, "保存失败", str(exc))

    def range_mode_changed(self, index):
        if index == 0:
            if self.preview_player is not None:
                self.preview_player.stop()
            self.clip_panel.hide()
            self.clip_applied = False
            self.restore_full_video_filename()
            self.range_label.setText(tr("full_video_info"))
            return
        if not self.info:
            self.range_combo.blockSignals(True)
            self.range_combo.setCurrentIndex(0)
            self.range_combo.blockSignals(False)
            QMessageBox.warning(self, "尚未解析", "请先解析视频")
            return
        self.show_clip_selector()

    def preview_stream_url(self):
        if not self.info:
            return None
        progressive = [f for f in self.info.get("formats", []) if f.get("url") and f.get("vcodec") not in (None, "none") and f.get("acodec") not in (None, "none")]
        pool = [f for f in progressive if f.get("ext") == "mp4"] or progressive
        if not pool:
            pool = [f for f in self.info.get("formats", []) if f.get("url") and f.get("vcodec") not in (None, "none")]
        if not pool:
            return None
        selected = max(pool, key=lambda f: (int((f.get("height") or 0) <= 720), f.get("height") or 0, f.get("fps") or 0))
        self.preview_fps = float(selected.get("fps") or 30)
        return selected.get("url")

    def show_clip_selector(self):
        url = self.preview_stream_url()
        if not url:
            QMessageBox.warning(self, "无法预览", "当前视频没有可用的预览流")
            self.range_combo.blockSignals(True)
            self.range_combo.setCurrentIndex(0)
            self.range_combo.blockSignals(False)
            return
        if not self.ensure_preview_player():
            self.range_combo.blockSignals(True)
            self.range_combo.setCurrentIndex(0)
            self.range_combo.blockSignals(False)
            return
        duration_ms = max(1, int((self.info.get("duration") or 1) * 1000))
        self.clip_start, self.clip_end = 0.0, duration_ms / 1000
        self.clip_applied = False
        self.clip_timeline.set_duration(duration_ms)
        self.clip_timeline.set_selection(0, duration_ms, False)
        self.clip_panel.show()
        self.preview_spinner.start()
        self.preview_player.setSource(QUrl(url))
        self.preview_player.play()
        self.set_play_button_state(True)
        value = f"{seconds_text_ms(self.clip_start)} – {seconds_text_ms(self.clip_end)}"
        self.range_label.setText(tr("choosing_range", value=value))

    def seek_preview(self, milliseconds):
        if self.preview_player is None:
            return
        self.preview_spinner.start()
        self.preview_player.setPosition(milliseconds)

    def toggle_preview(self):
        if self.preview_player is None:
            return
        if self.preview_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.preview_player.pause()
        else:
            self.preview_player.play()

    def preview_state_changed(self, state):
        self.set_play_button_state(state == QMediaPlayer.PlaybackState.PlayingState)

    def preview_media_status_changed(self, status):
        if status in (
            QMediaPlayer.MediaStatus.LoadingMedia,
            QMediaPlayer.MediaStatus.BufferingMedia,
            QMediaPlayer.MediaStatus.StalledMedia,
        ):
            self.preview_spinner.start()
        elif not self.preview_frame_signal_supported and status in (
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        ):
            self.preview_spinner.stop()

    def preview_frame_ready(self, frame):
        if frame.isValid():
            self.preview_spinner.stop()

    def step_preview_frame(self, direction):
        if self.preview_player is None:
            return
        self.preview_player.pause()
        self.preview_spinner.start()
        frame_ms = max(1, round(1000 / max(1.0, getattr(self, "preview_fps", 30.0))))
        duration = max(self.clip_timeline.duration, self.preview_player.duration())
        position = max(0, min(duration, self.preview_player.position() + direction * frame_ms))
        self.preview_player.setPosition(position)

    def preview_position_changed(self, milliseconds):
        self.clip_timeline.set_position(milliseconds)
        duration = max(self.clip_timeline.duration, self.preview_player.duration())
        self.clip_time_label.setText(f"{seconds_text_ms(milliseconds / 1000)} / {seconds_text_ms(duration / 1000)}")

    def preview_error(self, _error, message):
        self.preview_spinner.stop()
        if message:
            self.clip_time_label.setText("预览加载失败")

    def set_clip_start(self):
        if self.preview_player is None:
            return
        current = self.preview_player.position() / 1000
        if current >= self.clip_end:
            QMessageBox.warning(self, "边界无效", "左边界必须早于右边界")
            return
        self.clip_start = current
        self.clip_applied = False
        self.restore_full_video_filename()
        self.clip_timeline.set_selection(self.clip_start * 1000, self.clip_end * 1000, False)
        value = f"{seconds_text_ms(self.clip_start)} – {seconds_text_ms(self.clip_end)}"
        self.range_label.setText(tr("pending_range", value=value))

    def set_clip_end(self):
        if self.preview_player is None:
            return
        current = self.preview_player.position() / 1000
        if current <= self.clip_start:
            QMessageBox.warning(self, "边界无效", "右边界必须晚于左边界")
            return
        self.clip_end = current
        self.clip_applied = False
        self.restore_full_video_filename()
        self.clip_timeline.set_selection(self.clip_start * 1000, self.clip_end * 1000, False)
        value = f"{seconds_text_ms(self.clip_start)} – {seconds_text_ms(self.clip_end)}"
        self.range_label.setText(tr("pending_range", value=value))

    def cancel_clip_selection(self, reset_combo=True):
        if self.preview_player is not None:
            self.preview_player.stop()
        if hasattr(self, "preview_spinner"):
            self.preview_spinner.stop()
        if hasattr(self, "clip_panel"):
            self.clip_panel.hide()
        self.clip_applied = False
        self.restore_full_video_filename()
        if reset_combo and hasattr(self, "range_combo"):
            self.range_combo.blockSignals(True)
            self.range_combo.setCurrentIndex(0)
            self.range_combo.blockSignals(False)
            self.range_label.setText(tr("full_video_info"))

    def restore_full_video_filename(self):
        if not hasattr(self, "filename_edit"):
            return
        restored = strip_time_suffix(self.filename_edit.text())
        self.filename_edit.setText(restored)
        self.filename_edit.setToolTip(restored)
        self.filename_edit.setCursorPosition(0)

    def apply_clip_selection(self):
        if self.clip_end <= self.clip_start:
            QMessageBox.warning(self, "区间无效", "请先用 [ 和 ] 设置有效区间")
            return
        self.clip_applied = True
        self.clip_timeline.set_selection(self.clip_start * 1000, self.clip_end * 1000, True)
        base = strip_time_suffix(self.filename_edit.text())
        suffix = f"[{filename_time(self.clip_start)}~{filename_time(self.clip_end)}]"
        selected_name = clean_filename(f"{base} {suffix}")
        self.filename_edit.setText(selected_name)
        self.filename_edit.setToolTip(selected_name)
        self.filename_edit.setCursorPosition(0)
        value = f"{seconds_text_ms(self.clip_start)} – {seconds_text_ms(self.clip_end)}"
        self.range_label.setText(tr("selected_range", value=value))

    def resolve_existing_file(self, path):
        target = Path(path)
        if not target.exists():
            return str(target), False
        dialog = QMessageBox(self)
        dialog.setWindowTitle("文件已存在")
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setText(f"目标文件已经存在：\n{target.name}")
        overwrite_button = dialog.addButton("覆盖", QMessageBox.ButtonRole.AcceptRole)
        cancel_button = dialog.addButton("取消下载", QMessageBox.ButtonRole.RejectRole)
        number_button = dialog.addButton("添加序号", QMessageBox.ButtonRole.ActionRole)
        dialog.setDefaultButton(number_button)
        dialog.exec()
        clicked = dialog.clickedButton()
        if clicked is overwrite_button:
            return str(target), True
        if clicked is number_button:
            index = 1
            while True:
                candidate = target.with_name(f"{target.stem}（{index}）{target.suffix}")
                if not candidate.exists():
                    return str(candidate), False
                index += 1
        if clicked is cancel_button:
            return None
        return None

    def ensure_disk_space(self, path, estimated_bytes, section=None):
        if not estimated_bytes:
            return True
        required = float(estimated_bytes)
        if section and self.info and self.info.get("duration"):
            ratio = max(0.0, min(1.0, (section[1] - section[0]) / float(self.info["duration"])))
            required *= ratio
        required = max(1, int(required * 1.05))
        try:
            free = shutil.disk_usage(Path(path).parent).free
        except OSError:
            return True
        if free >= required:
            return True
        QMessageBox.warning(
            self,
            "磁盘空间不足",
            f"预计至少需要 {human_size(required)}，目标磁盘当前可用 {human_size(free)}。\n请更换保存位置或释放空间。",
        )
        return False

    def audio_quality_selected(self, index):
        if index <= 0:
            return
        audio_format = self.audio_combo.itemData(index)
        self.audio_combo.blockSignals(True)
        self.audio_combo.setCurrentIndex(0)
        self.audio_combo.blockSignals(False)
        if not self.info or not audio_format:
            return
        if len(self.tasks) >= MAX_TASKS:
            QMessageBox.warning(self, "任务已满", "最多同时保留 5 个下载任务，请先清除一个任务")
            return
        section = None
        if self.range_combo.currentIndex() == 1:
            if not self.clip_applied or self.clip_end <= self.clip_start:
                QMessageBox.warning(self, "区间未应用", "请先在右下角设置并应用视频区间")
                return
            section = (self.clip_start, self.clip_end)
        ext = audio_format.get("audio_ext") or audio_format.get("ext") or "m4a"
        name = clean_filename(self.filename_edit.text())
        initial = Path(self.settings.value("last_folder", str(Path.home())))
        path, _ = QFileDialog.getSaveFileName(
            self, "保存音频", str(initial / f"{name}.{ext}"),
            f"{ext.upper()} 音频 (*.{ext});;所有文件 (*)", options=QFileDialog.Option.DontConfirmOverwrite,
        )
        if not path:
            return
        if Path(path).suffix.lower() != f".{ext}":
            path = str(Path(path).with_suffix(f".{ext}"))
        resolved = self.resolve_existing_file(path)
        if not resolved:
            return
        path, overwrite = resolved
        if not self.ensure_disk_space(path, audio_format.get("estimated_bytes"), section):
            return
        self.settings.setValue("last_folder", str(Path(path).parent))
        self.pending_download = {
            "format": audio_format, "path": path, "cover": False,
            "overwrite": overwrite,
        }
        self.create_task(section)

    def prepare_download(self):
        if not self.info or self.format_combo.currentIndex() < 0:
            return
        if len(self.tasks) >= MAX_TASKS:
            QMessageBox.warning(self, "任务已满", "最多同时保留 5 个下载任务，请先清除一个任务")
            return
        fmt, name = self.format_combo.currentData(), clean_filename(self.filename_edit.text())
        ext = fmt.get("merge_ext") or "mp4"
        initial = Path(self.settings.value("last_folder", str(Path.home())))
        path, _ = QFileDialog.getSaveFileName(
            self, "保存视频", str(initial / f"{name}.{ext}"),
            f"{ext.upper()} 视频 (*.{ext});;所有文件 (*)", options=QFileDialog.Option.DontConfirmOverwrite,
        )
        if not path:
            return
        if Path(path).suffix.lower() != f".{ext}":
            path = str(Path(path).with_suffix(f".{ext}"))
        resolved = self.resolve_existing_file(path)
        if not resolved:
            return
        path, overwrite = resolved
        section = None
        if self.range_combo.currentIndex() == 1:
            if not self.clip_applied or self.clip_end <= self.clip_start:
                QMessageBox.warning(self, "区间未应用", "请先在右下角设置并应用视频区间")
                return
            section = (self.clip_start, self.clip_end)
        if not self.ensure_disk_space(path, fmt.get("estimated_bytes"), section):
            return
        self.settings.setValue("last_folder", str(Path(path).parent))
        self.pending_download = {
            "format": fmt, "path": path, "cover": self.cover_check.isChecked(),
            "overwrite": overwrite,
        }
        self.create_task(section)

    def create_task(self, section):
        pending, self.pending_download = self.pending_download, None
        if not pending:
            return
        fmt = pending["format"]
        manager = DownloadManager(
            self.url_edit.text().strip(), fmt["selector"], pending["path"],
            fmt.get("merge_ext"), pending["cover"], section=section,
            overwrite=pending.get("overwrite", False),
            progress_components=fmt.get("progress_components"), parent=self,
        )
        card = DownloadTaskWidget(manager, self.thumbnail_bytes)
        card.set_scale(self.ui_scale or 1.0)
        card.removed.connect(self.remove_task)
        self.tasks.append((manager, card))
        self.task_layout.insertWidget(0, card)
        self.update_task_count()
        manager.start()

    def remove_task(self, card):
        for index, (manager, widget) in enumerate(list(self.tasks)):
            if widget is card:
                self.tasks.pop(index)
                widget.deleteLater()
                manager.deleteLater()
                break
        self.update_task_count()

    def update_task_count(self):
        self.task_count.setText(f"{len(self.tasks)} / {MAX_TASKS}")

    def closeEvent(self, event):
        active = [manager for manager, _ in self.tasks if manager.state == "running"]
        if active:
            answer = QMessageBox.question(self, "退出程序", "仍有下载任务运行。退出会暂停任务并保留断点文件，是否退出？",
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            for manager in active:
                manager.pause()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setStyle("Fusion")
    try:
        window = YoutubeDownloader()
    except Exception:
        details = traceback.format_exc()
        try:
            (runtime_dir() / "ytdl_startup_error.log").write_text(details, encoding="utf-8")
        except OSError:
            pass
        QMessageBox.critical(None, "启动失败", f"程序初始化失败，详细信息已写入 ytdl_startup_error.log。\n\n{details[-1200:]}")
        sys.exit(1)
    window.show()
    sys.exit(app.exec())
