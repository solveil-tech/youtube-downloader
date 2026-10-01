import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock, Event
from pathlib import Path
from datetime import datetime, timezone
from idol_search import IdolCatalogue, make_search_plan, member_display_name, normalize as normalize_idol, rank_results, search_url, flatten_search_entries
from media_library import LibraryScanner, duplicate_matches, remember_download
from youtube_search import search_short_pages, complete_short_metadata

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

from PyQt6.QtCore import QEvent, QPoint, QProcess, QRectF, QSettings, QSize, Qt, QThread, QTimer, QUrl, QStringListModel, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QCursor, QDesktopServices, QFont, QIcon, QImage, QPainter, QPen, QPixmap
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QCompleter, QFileDialog, QFrame, QHBoxLayout, QInputDialog,
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
MAX_TASKS = 10
MAX_AUTO_RETRIES = 3
AUTO_RETRY_DELAYS_MS = (2000, 5000, 10000)
DEFAULT_CONCURRENT_DOWNLOADS = 3
MAX_CONCURRENT_DOWNLOADS = 5
PREVIEW_CACHE_MAX_FILES = 10
PREVIEW_CACHE_MAX_BYTES = 500 * 1024 * 1024
WINDOW_ASPECT_RATIO = 860 / 700
BG, CARD, TEXT, MUTED = "#f5f6f8", "#ffffff", "#17191d", "#737984"
ACCENT, ACCENT_HOVER, BORDER, DANGER = "#5668e9", "#4658d8", "#dde1e8", "#d94b54"

LANGUAGE_CODES = ("zh", "en", "ja", "ko", "fr", "de", "ru", "it", "es", "ar")
LANGUAGE_NAMES = {
    "zh": "中文", "en": "English", "ja": "日本語", "ko": "한국어", "fr": "Français",
    "de": "Deutsch", "ru": "Русский", "it": "Italiano", "es": "Español", "ar": "العربية",
}
CURRENT_LANGUAGE = "zh"

SEARCH_TEXTS = {
    "batch_parse": ("解析所选（{count}）", "Parse selected ({count})", "選択を解析（{count}）", "선택 분석 ({count})", "Analyser ({count})", "Auswahl analysieren ({count})", "Разобрать ({count})", "Analizza ({count})", "Analizar ({count})", "تحليل المحدد ({count})"),
    "select_all": ("全选", "Select all", "すべて選択", "전체 선택", "Tout sélectionner", "Alle auswählen", "Выбрать все", "Seleziona tutto", "Seleccionar todo", "تحديد الكل"),
    "save_all_covers": ("保存全部封面", "Save all covers", "すべてのカバーを保存", "모든 표지 저장", "Enregistrer les couvertures", "Alle Cover speichern", "Сохранить все обложки", "Salva tutte le copertine", "Guardar todas las portadas", "حفظ كل الأغلفة"),
    "batch_loading": ("批量解析 {done}/{total}", "Parsing batch {done}/{total}", "一括解析 {done}/{total}", "일괄 분석 {done}/{total}", "Analyse {done}/{total}", "Analyse {done}/{total}", "Разбор {done}/{total}", "Analisi {done}/{total}", "Análisis {done}/{total}", "تحليل {done}/{total}"),
    "batch_ready": ("{count} 个视频 · 默认格式与文件名", "{count} videos · default formats and filenames", "{count} 本 · 既定形式と名前", "{count}개 · 기본 형식 및 파일명", "{count} vidéos · formats et noms par défaut", "{count} Videos · Standardformate und Namen", "{count} видео · форматы и имена по умолчанию", "{count} video · formati e nomi predefiniti", "{count} vídeos · formatos y nombres predeterminados", "{count} فيديو · التنسيقات والأسماء الافتراضية"),
    "downloaded_source": ("已下载同源视频", "Downloaded source video", "同じソースをダウンロード済み", "동일 원본 다운로드됨", "Source déjà téléchargée", "Quelle bereits heruntergeladen", "Источник уже скачан", "Sorgente già scaricata", "Fuente ya descargada", "تم تنزيل المصدر"),
    "possible_duplicate": ("疑似重复（内嵌标题和时长匹配）", "Possible duplicate (embedded title and duration)", "重複の可能性（タイトルと長さ）", "중복 가능성 (내장 제목 및 길이)", "Doublon possible (titre intégré et durée)", "Mögliches Duplikat (Titel und Dauer)", "Возможный дубликат (название и длительность)", "Possibile duplicato (titolo e durata)", "Posible duplicado (título y duración)", "تكرار محتمل (العنوان والمدة)"),
    "duplicate_clip": ("片段", "Clip", "区間", "클립", "Extrait", "Ausschnitt", "Фрагмент", "Clip", "Fragmento", "مقطع"),
    "duplicate_advisory": ("仅提示，不影响下载。", "Advisory only; downloading remains available.", "参考情報のみ。ダウンロード可能です。", "참고용이며 다운로드에 영향을 주지 않습니다.", "Information uniquement, téléchargement disponible.", "Nur ein Hinweis, Download weiterhin möglich.", "Только подсказка, загрузка доступна.", "Solo un avviso, download disponibile.", "Solo aviso, la descarga sigue disponible.", "تنبيه فقط، لا يمنع التنزيل."),
    "search": ("搜索", "Search", "検索", "검색", "Rechercher", "Suchen", "Поиск", "Cerca", "Buscar", "بحث"),
    "group": ("组合（可选）", "Group (optional)", "グループ（任意）", "그룹 (선택)", "Groupe (facultatif)", "Gruppe (optional)", "Группа (необязательно)", "Gruppo (facoltativo)", "Grupo (opcional)", "المجموعة (اختياري)"),
    "member": ("成员名字（可选）", "Member (optional)", "メンバー（任意）", "멤버 (선택)", "Membre (facultatif)", "Mitglied (optional)", "Участница (необязательно)", "Membro (facoltativo)", "Integrante (opcional)", "العضوة (اختياري)"),
    "date": ("日期 YYMMDD（必填）", "Date YYMMDD (required)", "日付 YYMMDD（必須）", "날짜 YYMMDD (필수)", "Date AAMMJJ (requise)", "Datum JJMMTT (Pflicht)", "Дата ГГММДД (обязательно)", "Data AAMMGG (obbligatoria)", "Fecha AAMMDD (obligatoria)", "التاريخ YYMMDD (مطلوب)"),
    "choose_identity": ("请选择成员身份", "Choose member identity", "メンバーを選択", "멤버를 선택하세요", "Choisir le membre", "Mitglied auswählen", "Выберите участницу", "Scegli il membro", "Elige integrante", "اختر العضوة"),
    "identity_error": ("请从候选中确认组合或成员；至少填写其中一项。", "Select a matching group or member; at least one is required.", "候補からグループかメンバーを選択してください。", "그룹 또는 멤버를 후보에서 선택하세요.", "Sélectionnez un groupe ou un membre.", "Gruppe oder Mitglied aus den Vorschlägen wählen.", "Выберите группу или участницу из списка.", "Seleziona un gruppo o un membro.", "Selecciona un grupo o una integrante.", "اختر مجموعة أو عضوة من الاقتراحات."),
    "date_error": ("日期必须是有效的六位 YYMMDD，例如 260919。", "Enter a valid six-digit YYMMDD date, e.g. 260919.", "有効な6桁の日付 YYMMDD を入力してください。", "올바른 6자리 YYMMDD 날짜를 입력하세요.", "Date valide à six chiffres AAMMJJ requise.", "Gültiges sechsstelliges Datum JJMMTT eingeben.", "Введите действительную дату ГГММДД из шести цифр.", "Inserisci una data valida a sei cifre AAMMGG.", "Introduce una fecha válida de seis cifras AAMMDD.", "أدخل تاريخاً صالحاً من ستة أرقام YYMMDD."),
    "pending_chinese": ("待核对", "Unverified", "未確認", "미확인", "Non vérifié", "Ungeprüft", "Не проверено", "Non verificato", "Sin verificar", "غير مؤكد"),
    "search_results": ("搜索结果", "Search results", "検索結果", "검색 결과", "Résultats", "Suchergebnisse", "Результаты", "Risultati", "Resultados", "نتائج البحث"),
    "search_progress": ("检索 {done}/{total} · {count} 条结果", "Searching {done}/{total} · {count} results", "検索 {done}/{total} · {count} 件", "검색 {done}/{total} · {count}개", "Recherche {done}/{total} · {count} résultats", "Suche {done}/{total} · {count} Ergebnisse", "Поиск {done}/{total} · {count} результатов", "Ricerca {done}/{total} · {count} risultati", "Buscando {done}/{total} · {count} resultados", "بحث {done}/{total} · {count} نتيجة"),
    "search_summary": ("{count} 条结果 · {failed} 项查询失败 · 发布时间带 ≈ 为估计值", "{count} results · {failed} failed queries · ≈ means estimated upload date", "{count} 件 · 失敗 {failed} · ≈ は推定公開日", "{count}개 · 실패 {failed} · ≈는 추정 게시일", "{count} résultats · {failed} échecs · ≈ date estimée", "{count} Ergebnisse · {failed} Fehler · ≈ geschätztes Upload-Datum", "{count} результатов · ошибок {failed} · ≈ примерная дата публикации", "{count} risultati · {failed} errori · ≈ data stimata", "{count} resultados · {failed} fallos · ≈ fecha estimada", "{count} نتيجة · {failed} استعلامات فاشلة · ≈ تاريخ نشر تقديري"),
    "search_download": ("下载", "Download", "ダウンロード", "다운로드", "Télécharger", "Herunterladen", "Скачать", "Scarica", "Descargar", "تنزيل"),
    "related_result": ("近似匹配", "Related match", "関連結果", "유사 결과", "Résultat proche", "Ähnlicher Treffer", "Похожий результат", "Risultato simile", "Coincidencia aproximada", "نتيجة مشابهة"),
}


def search_tr(key, **values):
    options = SEARCH_TEXTS[key]
    value = options[LANGUAGE_CODES.index(CURRENT_LANGUAGE)].format(**values)
    return value.rsplit(" · ", 1)[0] if key == "search_summary" else value

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
    "retry": ("重试", "Retry", "再試行", "다시 시도", "Réessayer", "Erneut versuchen", "Повторить", "Riprova", "Reintentar", "إعادة المحاولة"),
    "copy_link": ("复制视频链接", "Copy video link", "動画リンクをコピー", "동영상 링크 복사", "Copier le lien vidéo", "Videolink kopieren", "Копировать ссылку", "Copia link video", "Copiar enlace del vídeo", "نسخ رابط الفيديو"),
    "open_video": ("打开视频页面", "Open video page", "動画ページを開く", "동영상 페이지 열기", "Ouvrir la page vidéo", "Videoseite öffnen", "Открыть страницу видео", "Apri pagina video", "Abrir página del vídeo", "فتح صفحة الفيديو"),
    "half_speed": ("0.5 倍速", "0.5× speed", "0.5倍速", "0.5배속", "Vitesse 0,5×", "0,5-fache Geschwindigkeit", "Скорость 0,5×", "Velocità 0,5×", "Velocidad 0,5×", "سرعة 0.5×"),
    "double_speed": ("2 倍速", "2× speed", "2倍速", "2배속", "Vitesse 2×", "2-fache Geschwindigkeit", "Скорость 2×", "Velocità 2×", "Velocidad 2×", "سرعة 2×"),
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
    "concurrent_downloads": ("并行任务数", "Parallel tasks", "並行タスク数", "병렬 작업 수", "Tâches parallèles", "Parallele Aufgaben", "Параллельные задачи", "Attività parallele", "Tareas paralelas", "المهام المتوازية"),
    "check_engine_update": ("检查下载引擎更新", "Check downloader engine update", "ダウンロードエンジンを更新", "다운로드 엔진 업데이트 확인", "Vérifier le moteur", "Downloader aktualisieren", "Проверить обновление движка", "Aggiorna motore", "Actualizar motor", "التحقق من تحديث المحرك"),
    "error_details": ("错误详情", "Error details", "エラー詳細", "오류 세부정보", "Détails de l’erreur", "Fehlerdetails", "Подробности ошибки", "Dettagli errore", "Detalles del error", "تفاصيل الخطأ"),
    "copy_error": ("复制错误", "Copy error", "エラーをコピー", "오류 복사", "Copier l’erreur", "Fehler kopieren", "Копировать ошибку", "Copia errore", "Copiar error", "نسخ الخطأ"),
    "clear_task_title": ("清除任务", "Clear task", "タスクを消去", "작업 지우기", "Effacer la tâche", "Aufgabe löschen", "Очистить задачу", "Cancella attività", "Borrar tarea", "مسح المهمة"),
    "clear_task_message": ("将停止任务，并删除成品、未完成文件及相关临时文件。是否继续？", "Stop the task and delete completed, partial, and temporary files?", "タスクを停止し、完成・未完成・一時ファイルを削除しますか？", "작업을 중지하고 완성본, 미완성 및 임시 파일을 삭제할까요?", "Arrêter la tâche et supprimer les fichiers terminés, partiels et temporaires ?", "Aufgabe stoppen und fertige, unvollständige sowie temporäre Dateien löschen?", "Остановить задачу и удалить готовые, неполные и временные файлы?", "Interrompere e eliminare file completi, parziali e temporanei?", "¿Detener y eliminar archivos completos, parciales y temporales?", "هل تريد إيقاف المهمة وحذف الملفات المكتملة والجزئية والمؤقتة؟"),
    "hide_task_title": ("隐藏任务", "Hide task", "タスクを隠す", "작업 숨기기", "Masquer la tâche", "Aufgabe ausblenden", "Скрыть задачу", "Nascondi attività", "Ocultar tarea", "إخفاء المهمة"),
    "hide_task_message": ("将停止任务并删除未完成缓存，但不会删除已经保存好的文件。是否继续？", "Stop the task and delete partial cache while keeping completed files?", "タスクを停止して未完了キャッシュを削除し、完成ファイルは保持しますか？", "작업을 중지하고 미완성 캐시는 삭제하되 완료 파일은 유지할까요?", "Arrêter la tâche et supprimer le cache partiel en conservant les fichiers terminés ?", "Aufgabe stoppen und unvollständigen Cache löschen, fertige Dateien behalten?", "Остановить задачу и удалить незавершённый кэш, сохранив готовые файлы?", "Interrompere ed eliminare la cache incompleta mantenendo i file completi?", "¿Detener y borrar la caché parcial conservando los archivos terminados?", "هل تريد إيقاف المهمة وحذف التخزين الجزئي مع الاحتفاظ بالملفات المكتملة؟"),
    "invalid_link_title": ("链接无效", "Invalid link", "無効なリンク", "잘못된 링크", "Lien invalide", "Ungültiger Link", "Недопустимая ссылка", "Link non valido", "Enlace no válido", "رابط غير صالح"),
    "invalid_link_message": ("请输入有效的 YouTube 视频链接", "Enter a valid YouTube video link", "有効なYouTube動画リンクを入力してください", "유효한 YouTube 동영상 링크를 입력하세요", "Saisissez un lien vidéo YouTube valide", "Gültigen YouTube-Videolink eingeben", "Введите действительную ссылку YouTube", "Inserisci un link YouTube valido", "Introduce un enlace de YouTube válido", "أدخل رابط فيديو YouTube صالحاً"),
    "parse_failed_title": ("解析失败", "Analysis failed", "解析に失敗", "분석 실패", "Échec de l’analyse", "Analyse fehlgeschlagen", "Ошибка анализа", "Analisi non riuscita", "Error de análisis", "فشل التحليل"),
    "not_parsed_title": ("尚未解析", "Not analyzed", "未解析", "분석되지 않음", "Non analysé", "Noch nicht analysiert", "Не проанализировано", "Non analizzato", "Sin analizar", "لم يتم التحليل"),
    "not_parsed_message": ("请先解析视频", "Analyze the video first", "先に動画を解析してください", "먼저 동영상을 분석하세요", "Analysez d’abord la vidéo", "Video zuerst analysieren", "Сначала проанализируйте видео", "Analizza prima il video", "Analiza primero el vídeo", "حلل الفيديو أولاً"),
    "preview_unavailable_title": ("无法预览", "Preview unavailable", "プレビュー不可", "미리보기 불가", "Aperçu indisponible", "Vorschau nicht verfügbar", "Предпросмотр недоступен", "Anteprima non disponibile", "Vista previa no disponible", "المعاينة غير متاحة"),
    "preview_unavailable_message": ("当前视频没有可用的预览流", "No usable preview stream is available", "利用可能なプレビュー映像がありません", "사용 가능한 미리보기 스트림이 없습니다", "Aucun flux d’aperçu utilisable", "Kein nutzbarer Vorschaustream", "Нет доступного потока предпросмотра", "Nessun flusso di anteprima disponibile", "No hay una transmisión de vista previa disponible", "لا يوجد بث معاينة متاح"),
    "boundary_invalid_title": ("边界无效", "Invalid boundary", "無効な境界", "잘못된 경계", "Limite invalide", "Ungültige Grenze", "Недопустимая граница", "Limite non valido", "Límite no válido", "حد غير صالح"),
    "start_boundary_message": ("左边界必须早于右边界", "The start must be before the end", "開始位置は終了位置より前にしてください", "시작 지점은 종료 지점보다 앞이어야 합니다", "Le début doit précéder la fin", "Start muss vor Ende liegen", "Начало должно быть раньше конца", "L’inizio deve precedere la fine", "El inicio debe ser anterior al final", "يجب أن تكون البداية قبل النهاية"),
    "end_boundary_message": ("右边界必须晚于左边界", "The end must be after the start", "終了位置は開始位置より後にしてください", "종료 지점은 시작 지점보다 뒤여야 합니다", "La fin doit suivre le début", "Ende muss nach Start liegen", "Конец должен быть позже начала", "La fine deve seguire l’inizio", "El final debe ser posterior al inicio", "يجب أن تكون النهاية بعد البداية"),
    "range_invalid_title": ("区间无效", "Invalid range", "無効な範囲", "잘못된 구간", "Plage invalide", "Ungültiger Bereich", "Недопустимый диапазон", "Intervallo non valido", "Rango no válido", "نطاق غير صالح"),
    "range_invalid_message": ("请先用 [ 和 ] 设置有效区间", "Set a valid range with [ and ] first", "[ と ] で有効な範囲を設定してください", "[ 및 ]로 유효한 구간을 먼저 설정하세요", "Définissez d’abord une plage avec [ et ]", "Zuerst mit [ und ] einen gültigen Bereich setzen", "Сначала задайте диапазон кнопками [ и ]", "Imposta prima un intervallo con [ e ]", "Define primero un rango con [ y ]", "حدد نطاقاً صالحاً باستخدام [ و ] أولاً"),
    "range_not_applied_title": ("区间未应用", "Range not applied", "範囲未適用", "구간 미적용", "Plage non appliquée", "Bereich nicht angewendet", "Диапазон не применён", "Intervallo non applicato", "Rango no aplicado", "لم يتم تطبيق النطاق"),
    "range_not_applied_message": ("请先设置并应用视频区间", "Set and apply the video range first", "先に動画範囲を設定して適用してください", "먼저 동영상 구간을 설정하고 적용하세요", "Définissez et appliquez d’abord la plage vidéo", "Videobereich zuerst festlegen und anwenden", "Сначала задайте и примените диапазон", "Imposta e applica prima l’intervallo", "Define y aplica primero el rango", "حدد نطاق الفيديو وطبقه أولاً"),
    "file_exists_title": ("文件已存在", "File already exists", "ファイルは既に存在します", "파일이 이미 존재함", "Le fichier existe", "Datei existiert", "Файл уже существует", "File già esistente", "El archivo ya existe", "الملف موجود بالفعل"),
    "file_exists_message": ("目标文件已经存在：\n{value}", "The target file already exists:\n{value}", "対象ファイルは既に存在します：\n{value}", "대상 파일이 이미 존재합니다:\n{value}", "Le fichier cible existe déjà :\n{value}", "Die Zieldatei existiert bereits:\n{value}", "Целевой файл уже существует:\n{value}", "Il file di destinazione esiste già:\n{value}", "El archivo de destino ya existe:\n{value}", "الملف الهدف موجود بالفعل:\n{value}"),
    "overwrite": ("覆盖", "Overwrite", "上書き", "덮어쓰기", "Écraser", "Überschreiben", "Перезаписать", "Sovrascrivi", "Sobrescribir", "استبدال"),
    "cancel_download": ("取消下载", "Cancel download", "ダウンロードを中止", "다운로드 취소", "Annuler le téléchargement", "Download abbrechen", "Отменить загрузку", "Annulla download", "Cancelar descarga", "إلغاء التنزيل"),
    "add_number": ("添加序号", "Add number", "番号を追加", "번호 추가", "Ajouter un numéro", "Nummer hinzufügen", "Добавить номер", "Aggiungi numero", "Añadir número", "إضافة رقم"),
    "disk_space_title": ("磁盘空间不足", "Not enough disk space", "ディスク容量不足", "디스크 공간 부족", "Espace disque insuffisant", "Nicht genug Speicherplatz", "Недостаточно места", "Spazio su disco insufficiente", "Espacio insuficiente", "مساحة القرص غير كافية"),
    "disk_space_message": ("预计至少需要 {required}，目标磁盘可用 {free}。\n请更换位置或释放空间。", "At least {required} is needed; {free} is available.\nChoose another location or free space.", "少なくとも {required} 必要で、空きは {free} です。\n保存先を変更するか空きを確保してください。", "최소 {required}이 필요하며 {free}을 사용할 수 있습니다.\n위치를 변경하거나 공간을 확보하세요.", "Au moins {required} sont requis ; {free} sont disponibles.\nChangez d’emplacement ou libérez de l’espace.", "Mindestens {required} benötigt; {free} verfügbar.\nAnderen Ort wählen oder Speicher freigeben.", "Нужно не менее {required}; доступно {free}.\nВыберите другое место или освободите пространство.", "Servono almeno {required}; disponibili {free}.\nCambia posizione o libera spazio.", "Se necesitan al menos {required}; hay {free} disponibles.\nCambia la ubicación o libera espacio.", "يلزم {required} على الأقل والمتاح {free}.\nاختر موقعاً آخر أو وفر مساحة."),
    "exit_title": ("退出程序", "Exit application", "アプリを終了", "앱 종료", "Quitter l’application", "Anwendung beenden", "Выйти из приложения", "Esci dall’app", "Salir de la aplicación", "إنهاء التطبيق"),
    "exit_message": ("仍有下载任务运行。退出会暂停任务并保留断点文件，是否退出？", "Downloads are still running. Exiting will pause them and keep partial files. Exit?", "ダウンロード中です。終了すると一時停止し、途中ファイルを保持します。終了しますか？", "다운로드가 진행 중입니다. 종료하면 일시 중지되고 부분 파일은 유지됩니다. 종료할까요?", "Des téléchargements sont actifs. Quitter les mettra en pause en conservant les fichiers partiels. Quitter ?", "Downloads laufen. Beim Beenden werden sie pausiert und Teildateien behalten. Beenden?", "Идут загрузки. При выходе они будут приостановлены, частичные файлы сохранятся. Выйти?", "Sono in corso download. Uscendo verranno sospesi e i file parziali mantenuti. Uscire?", "Hay descargas activas. Al salir se pausarán y se conservarán los archivos parciales. ¿Salir?", "لا تزال هناك تنزيلات. سيؤدي الخروج إلى إيقافها مؤقتاً والاحتفاظ بالملفات الجزئية. هل تريد الخروج؟"),
    "format_unavailable_title": ("所选格式不可用", "Selected format unavailable", "選択形式は利用不可", "선택한 형식 사용 불가", "Format indisponible", "Format nicht verfügbar", "Формат недоступен", "Formato non disponibile", "Formato no disponible", "التنسيق غير متاح"),
    "format_unavailable_message": ("视频格式可能已经变化。请重新解析链接并重新选择格式。", "Available formats may have changed. Analyze the link again and reselect a format.", "形式が変更された可能性があります。リンクを再解析して形式を選び直してください。", "사용 가능한 형식이 변경되었을 수 있습니다. 링크를 다시 분석하고 형식을 선택하세요.", "Les formats ont peut-être changé. Analysez à nouveau le lien et choisissez un format.", "Formate haben sich möglicherweise geändert. Link erneut analysieren und Format wählen.", "Форматы могли измениться. Повторно проанализируйте ссылку и выберите формат.", "I formati potrebbero essere cambiati. Analizza di nuovo il link e scegli il formato.", "Los formatos pueden haber cambiado. Analiza de nuevo el enlace y elige un formato.", "ربما تغيرت التنسيقات. حلل الرابط مجدداً واختر التنسيق."),
    "update_available_title": ("发现引擎更新", "Engine update available", "エンジン更新あり", "엔진 업데이트 있음", "Mise à jour disponible", "Engine-Update verfügbar", "Доступно обновление", "Aggiornamento disponibile", "Actualización disponible", "يتوفر تحديث للمحرك"),
    "update_available_message": ("当前版本：{current}\n最新版本：{latest}\n是否下载并安装？", "Current: {current}\nLatest: {latest}\nDownload and install?", "現在：{current}\n最新：{latest}\nダウンロードして更新しますか？", "현재: {current}\n최신: {latest}\n다운로드하고 설치할까요?", "Actuelle : {current}\nDernière : {latest}\nTélécharger et installer ?", "Aktuell: {current}\nNeu: {latest}\nHerunterladen und installieren?", "Текущая: {current}\nНовая: {latest}\nСкачать и установить?", "Attuale: {current}\nUltima: {latest}\nScaricare e installare?", "Actual: {current}\nÚltima: {latest}\n¿Descargar e instalar?", "الحالي: {current}\nالأحدث: {latest}\nهل تريد التنزيل والتثبيت؟"),
    "up_to_date_title": ("已是最新版本", "Up to date", "最新版です", "최신 버전", "À jour", "Aktuell", "Уже обновлено", "Aggiornato", "Actualizado", "محدث"),
    "up_to_date_message": ("当前下载引擎已是最新版本：{value}", "The downloader engine is up to date: {value}", "ダウンロードエンジンは最新版です：{value}", "다운로드 엔진이 최신 버전입니다: {value}", "Le moteur est à jour : {value}", "Downloader ist aktuell: {value}", "Движок загрузки обновлён: {value}", "Il motore è aggiornato: {value}", "El motor está actualizado: {value}", "محرك التنزيل محدث: {value}"),
    "update_success_title": ("更新完成", "Update complete", "更新完了", "업데이트 완료", "Mise à jour terminée", "Update abgeschlossen", "Обновление завершено", "Aggiornamento completato", "Actualización completada", "اكتمل التحديث"),
    "update_success_message": ("下载引擎已更新至 {value}", "Downloader engine updated to {value}", "ダウンロードエンジンを {value} に更新しました", "다운로드 엔진이 {value}(으)로 업데이트되었습니다", "Moteur mis à jour vers {value}", "Downloader auf {value} aktualisiert", "Движок обновлён до {value}", "Motore aggiornato a {value}", "Motor actualizado a {value}", "تم تحديث المحرك إلى {value}"),
    "update_failed_title": ("更新失败", "Update failed", "更新失敗", "업데이트 실패", "Échec de la mise à jour", "Update fehlgeschlagen", "Ошибка обновления", "Aggiornamento non riuscito", "Error de actualización", "فشل التحديث"),
    "update_busy_message": ("请先等待所有下载停止后再更新引擎。", "Stop all downloads before updating the engine.", "すべてのダウンロードを停止してから更新してください。", "모든 다운로드를 중지한 후 엔진을 업데이트하세요.", "Arrêtez tous les téléchargements avant la mise à jour.", "Vor dem Update alle Downloads stoppen.", "Остановите все загрузки перед обновлением.", "Interrompi tutti i download prima dell’aggiornamento.", "Detén todas las descargas antes de actualizar.", "أوقف جميع التنزيلات قبل تحديث المحرك."),
    "preview_cache_ready": ("本地预览缓存已就绪", "Local preview cache ready", "ローカルプレビュー準備完了", "로컬 미리보기 캐시 준비됨", "Cache d’aperçu prêt", "Lokale Vorschau bereit", "Локальный предпросмотр готов", "Cache anteprima pronta", "Caché de vista previa lista", "ذاكرة المعاينة المحلية جاهزة"),
    "preview_cache_loading": ("正在后台缓存片段预览", "Caching clip preview in the background", "クリッププレビューをキャッシュ中", "클립 미리보기를 캐시하는 중", "Mise en cache de l’aperçu", "Clip-Vorschau wird zwischengespeichert", "Кэширование предпросмотра", "Cache anteprima in corso", "Guardando vista previa en caché", "جارٍ تخزين معاينة المقطع"),
    "paused_state": ("已暂停，可继续断点下载", "Paused — resume is available", "一時停止中（再開可能）", "일시 중지됨 — 이어받기 가능", "En pause — reprise possible", "Pausiert — Fortsetzen möglich", "Приостановлено — можно продолжить", "In pausa — ripresa disponibile", "En pausa — se puede reanudar", "متوقف مؤقتاً — يمكن المتابعة"),
    "pausing_state": ("正在安全暂停...", "Pausing safely...", "安全に一時停止中...", "안전하게 일시 중지 중...", "Mise en pause...", "Wird sicher pausiert...", "Безопасная приостановка...", "Pausa sicura...", "Pausando de forma segura...", "جارٍ الإيقاف المؤقت بأمان..."),
    "engine_missing": ("未找到下载引擎 yt_dlp.exe", "Downloader engine yt_dlp.exe was not found", "yt_dlp.exe が見つかりません", "yt_dlp.exe 다운로드 엔진을 찾을 수 없습니다", "Moteur yt_dlp.exe introuvable", "yt_dlp.exe wurde nicht gefunden", "Движок yt_dlp.exe не найден", "Motore yt_dlp.exe non trovato", "No se encontró yt_dlp.exe", "لم يتم العثور على yt_dlp.exe"),
    "process_failed": ("下载进程异常结束", "Download process ended unexpectedly", "ダウンロード処理が異常終了しました", "다운로드 프로세스가 비정상 종료됨", "Le téléchargement s’est arrêté", "Downloadprozess wurde unerwartet beendet", "Процесс загрузки завершился с ошибкой", "Il processo di download è terminato in modo anomalo", "El proceso de descarga terminó inesperadamente", "انتهت عملية التنزيل بشكل غير متوقع"),
    "untitled_video": ("未命名视频", "Untitled video", "無題の動画", "제목 없는 동영상", "Vidéo sans titre", "Unbenanntes Video", "Видео без названия", "Video senza titolo", "Vídeo sin título", "فيديو بلا عنوان"),
    "unknown_channel": ("未知频道", "Unknown channel", "不明なチャンネル", "알 수 없는 채널", "Chaîne inconnue", "Unbekannter Kanal", "Неизвестный канал", "Canale sconosciuto", "Canal desconocido", "قناة غير معروفة"),
    "preview_init_title": ("预览初始化失败", "Preview initialization failed", "プレビュー初期化失敗", "미리보기 초기화 실패", "Échec de l’aperçu", "Vorschau konnte nicht gestartet werden", "Ошибка инициализации предпросмотра", "Inizializzazione anteprima non riuscita", "Error al iniciar la vista previa", "فشل تهيئة المعاينة"),
    "preview_init_message": ("Qt 视频预览组件无法初始化：\n{value}", "Qt video preview could not initialize:\n{value}", "Qt動画プレビューを初期化できません：\n{value}", "Qt 동영상 미리보기를 초기화할 수 없습니다:\n{value}", "Impossible d’initialiser l’aperçu Qt :\n{value}", "Qt-Vorschau konnte nicht initialisiert werden:\n{value}", "Не удалось инициализировать Qt-предпросмотр:\n{value}", "Impossibile inizializzare l’anteprima Qt:\n{value}", "No se pudo iniciar la vista previa Qt:\n{value}", "تعذر تهيئة معاينة Qt:\n{value}"),
    "save_success_title": ("保存成功", "Saved", "保存完了", "저장 완료", "Enregistré", "Gespeichert", "Сохранено", "Salvato", "Guardado", "تم الحفظ"),
    "cover_saved_message": ("封面已保存", "Thumbnail saved", "サムネイルを保存しました", "썸네일 저장됨", "Miniature enregistrée", "Vorschaubild gespeichert", "Обложка сохранена", "Miniatura salvata", "Miniatura guardada", "تم حفظ الصورة المصغرة"),
    "save_failed_title": ("保存失败", "Save failed", "保存失敗", "저장 실패", "Échec de l’enregistrement", "Speichern fehlgeschlagen", "Ошибка сохранения", "Salvataggio non riuscito", "Error al guardar", "فشل الحفظ"),
    "unknown": ("未知", "Unknown", "不明", "알 수 없음", "Inconnu", "Unbekannt", "Неизвестно", "Sconosciuto", "Desconocido", "غير معروف"),
    "unknown_resolution": ("未知分辨率", "Unknown resolution", "解像度不明", "해상도 알 수 없음", "Résolution inconnue", "Unbekannte Auflösung", "Разрешение неизвестно", "Risoluzione sconosciuta", "Resolución desconocida", "دقة غير معروفة"),
    "unknown_fps": ("帧率未知", "Unknown frame rate", "フレームレート不明", "프레임 속도 알 수 없음", "Fréquence inconnue", "Unbekannte Bildrate", "Частота кадров неизвестна", "Frame rate sconosciuto", "Fotogramas desconocidos", "معدل إطارات غير معروف"),
    "unknown_audio_quality": ("音质未知", "Unknown audio quality", "音質不明", "음질 알 수 없음", "Qualité audio inconnue", "Unbekannte Audioqualität", "Качество звука неизвестно", "Qualità audio sconosciuta", "Calidad de audio desconocida", "جودة صوت غير معروفة"),
    "preview_load_failed": ("预览加载失败", "Preview failed to load", "プレビュー読込失敗", "미리보기 로드 실패", "Échec du chargement", "Vorschau konnte nicht geladen werden", "Ошибка загрузки предпросмотра", "Caricamento anteprima non riuscito", "Error al cargar la vista previa", "فشل تحميل المعاينة"),
    "save_cover_dialog": ("保存封面", "Save thumbnail", "サムネイルを保存", "썸네일 저장", "Enregistrer la miniature", "Vorschaubild speichern", "Сохранить обложку", "Salva miniatura", "Guardar miniatura", "حفظ الصورة المصغرة"),
    "save_audio_dialog": ("保存音频", "Save audio", "音声を保存", "오디오 저장", "Enregistrer l’audio", "Audio speichern", "Сохранить аудио", "Salva audio", "Guardar audio", "حفظ الصوت"),
    "save_video_dialog": ("保存视频", "Save video", "動画を保存", "동영상 저장", "Enregistrer la vidéo", "Video speichern", "Сохранить видео", "Salva video", "Guardar vídeo", "حفظ الفيديو"),
    "all_files": ("所有文件", "All files", "すべてのファイル", "모든 파일", "Tous les fichiers", "Alle Dateien", "Все файлы", "Tutti i file", "Todos los archivos", "كل الملفات"),
    "info_parse_failed": ("视频信息解析失败", "Video analysis failed", "動画情報の解析に失敗", "동영상 정보 분석 실패", "Échec de l’analyse vidéo", "Videoanalyse fehlgeschlagen", "Ошибка анализа видео", "Analisi video non riuscita", "Error al analizar el vídeo", "فشل تحليل معلومات الفيديو"),
    "preview_cache_failed": ("预览缓存失败", "Preview cache failed", "プレビューキャッシュ失敗", "미리보기 캐시 실패", "Échec du cache d’aperçu", "Vorschau-Cache fehlgeschlagen", "Ошибка кэша предпросмотра", "Cache anteprima non riuscita", "Error de caché de vista previa", "فشل تخزين المعاينة"),
    "process_start_failed": ("下载进程启动失败", "Download process failed to start", "ダウンロード処理を開始できません", "다운로드 프로세스 시작 실패", "Impossible de démarrer le téléchargement", "Downloadprozess konnte nicht starten", "Не удалось запустить загрузку", "Impossibile avviare il download", "No se pudo iniciar la descarga", "فشل بدء عملية التنزيل"),
    "update_in_progress_message": ("下载引擎正在检查或更新，请完成后再退出。", "The downloader engine is being checked or updated. Wait before exiting.", "エンジンの確認または更新中です。完了後に終了してください。", "다운로드 엔진을 확인하거나 업데이트하는 중입니다. 완료 후 종료하세요.", "Le moteur est en cours de vérification ou de mise à jour. Attendez avant de quitter.", "Downloader wird geprüft oder aktualisiert. Bitte vor dem Beenden warten.", "Идёт проверка или обновление движка. Дождитесь завершения.", "Il motore è in verifica o aggiornamento. Attendi prima di uscire.", "El motor se está comprobando o actualizando. Espera antes de salir.", "جارٍ فحص محرك التنزيل أو تحديثه. انتظر قبل الخروج."),
    "startup_failed_title": ("启动失败", "Startup failed", "起動失敗", "시작 실패", "Échec du démarrage", "Start fehlgeschlagen", "Ошибка запуска", "Avvio non riuscito", "Error de inicio", "فشل التشغيل"),
    "startup_failed_message": ("程序初始化失败，详细信息已写入 ytdl_startup_error.log。\n\n{value}", "Initialization failed. Details were written to ytdl_startup_error.log.\n\n{value}", "初期化に失敗しました。詳細は ytdl_startup_error.log に保存されました。\n\n{value}", "초기화에 실패했습니다. 자세한 내용은 ytdl_startup_error.log에 저장되었습니다.\n\n{value}", "Échec de l’initialisation. Détails dans ytdl_startup_error.log.\n\n{value}", "Initialisierung fehlgeschlagen. Details stehen in ytdl_startup_error.log.\n\n{value}", "Ошибка инициализации. Подробности записаны в ytdl_startup_error.log.\n\n{value}", "Inizializzazione non riuscita. Dettagli in ytdl_startup_error.log.\n\n{value}", "Falló la inicialización. Detalles en ytdl_startup_error.log.\n\n{value}", "فشل التهيئة. تم حفظ التفاصيل في ytdl_startup_error.log.\n\n{value}"),
    "time_format_error": ("请使用 HH:MM:SS 或 MM:SS 格式", "Use HH:MM:SS or MM:SS format", "HH:MM:SS または MM:SS 形式を使用してください", "HH:MM:SS 또는 MM:SS 형식을 사용하세요", "Utilisez le format HH:MM:SS ou MM:SS", "Format HH:MM:SS oder MM:SS verwenden", "Используйте формат HH:MM:SS или MM:SS", "Usa il formato HH:MM:SS o MM:SS", "Usa el formato HH:MM:SS o MM:SS", "استخدم تنسيق HH:MM:SS أو MM:SS"),
    "engine_version_read_failed": ("无法读取 yt-dlp 版本", "Could not read the yt-dlp version", "yt-dlp のバージョンを取得できません", "yt-dlp 버전을 읽을 수 없습니다", "Impossible de lire la version de yt-dlp", "yt-dlp-Version konnte nicht gelesen werden", "Не удалось прочитать версию yt-dlp", "Impossibile leggere la versione di yt-dlp", "No se pudo leer la versión de yt-dlp", "تعذرت قراءة إصدار yt-dlp"),
    "engine_asset_missing": ("最新版本中未找到 yt-dlp.exe", "The latest release does not contain yt-dlp.exe", "最新リリースに yt-dlp.exe がありません", "최신 릴리스에 yt-dlp.exe가 없습니다", "La dernière version ne contient pas yt-dlp.exe", "Die neueste Version enthält keine yt-dlp.exe", "В последнем выпуске нет yt-dlp.exe", "L’ultima versione non contiene yt-dlp.exe", "La última versión no contiene yt-dlp.exe", "لا يحتوي أحدث إصدار على yt-dlp.exe"),
    "engine_validation_failed": ("新版 yt-dlp 验证失败", "The new yt-dlp executable failed validation", "新しい yt-dlp の検証に失敗しました", "새 yt-dlp 실행 파일 검증에 실패했습니다", "La validation du nouveau yt-dlp a échoué", "Die neue yt-dlp-Datei konnte nicht validiert werden", "Не удалось проверить новый файл yt-dlp", "La verifica del nuovo yt-dlp non è riuscita", "Falló la validación del nuevo yt-dlp", "فشل التحقق من ملف yt-dlp الجديد"),
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


def engine_path():
    external = runtime_dir() / "yt_dlp.exe"
    return external if external.exists() else bundled_path("yt_dlp.exe")


def preview_cache_dir():
    base = Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir())
    return base / ORG_NAME / APP_NAME.replace(" ", "") / "preview-cache"


def select_preview_format(info):
    pool = [
        fmt for fmt in (info or {}).get("formats", [])
        if is_direct_media_format(fmt)
        and fmt.get("format_id")
        and fmt.get("vcodec") not in (None, "none", "images")
    ]
    if not pool:
        return None
    # Resolution takes priority over a lower-resolution progressive stream.
    # preview_package retains audio when the 720p video is a separate stream.
    below_cap = [fmt for fmt in pool if 0 < int(fmt.get("height") or 0) <= 720]
    if below_cap:
        height = max(int(fmt["height"]) for fmt in below_cap)
        pool = [fmt for fmt in below_cap if int(fmt["height"]) == height]
    else:
        known = [fmt for fmt in pool if fmt.get("height")]
        if known:
            height = min(int(fmt["height"]) for fmt in known)
            pool = [fmt for fmt in known if int(fmt["height"]) == height]
    return max(pool, key=lambda fmt: (
        str(fmt.get("vcodec") or "").lower().startswith(("avc", "h264")),
        fmt.get("ext") == "mp4", fmt.get("acodec") not in (None, "none"),
        float(fmt.get("fps") or 0), float(fmt.get("tbr") or 0)))


def cover_thumbnail_urls(info):
    """Try the largest original cover first; retain lower-resolution fallbacks."""
    thumbnails = [dict(item) for item in info.get("thumbnails", []) if item.get("url")]
    preferred = info.get("thumbnail")
    if preferred and not any(item["url"] == preferred for item in thumbnails):
        thumbnails.append({"url": preferred})
    thumbnails.sort(key=lambda item: (
        "maxres" in item["url"],
        item["url"] == preferred and not (item.get("width") and item.get("height")),
        float(item.get("width") or 0) * float(item.get("height") or 0),
        float(item.get("preference") or 0), item["url"] == preferred), reverse=True)
    return list(dict.fromkeys(item["url"] for item in thumbnails))


def fetch_best_cover(info, cancelled=None):
    """Compare decoded pixels rather than trusting incomplete thumbnail metadata."""
    best, best_rank, best_url = b"", (-1, -1, -1), None
    urls = cover_thumbnail_urls(info)
    preferred = info.get("thumbnail")
    candidates = list(dict.fromkeys(urls[:5] + ([preferred] if preferred else [])))
    for url in candidates:
        if cancelled is not None and cancelled.is_set():
            break
        try:
            response = requests.get(url, timeout=8)
            response.raise_for_status()
            data = response.content
            image = QImage.fromData(data)
            if image.isNull():
                continue
            rank = (image.width() * image.height(), "maxres" in url, url == preferred)
            if rank > best_rank:
                best, best_rank, best_url = data, rank, url
        except requests.RequestException:
            continue
    if best_url:
        info["thumbnail"] = best_url
    return best


def preview_package(info):
    video = select_preview_format(info)
    if not video:
        return None
    result = dict(video)
    result["selector"] = str(video["format_id"])
    result["merge_ext"] = video.get("ext") or "mp4"
    if video.get("acodec") not in (None, "none"):
        return result
    audio_formats = [f for f in (info or {}).get("formats", [])
                     if is_direct_media_format(f) and f.get("format_id") and f.get("vcodec") == "none"
                     and f.get("acodec") not in (None, "none")]
    ext = result["merge_ext"]
    compatible = [f for f in audio_formats if
                  (ext == "mp4" and str(f.get("acodec", "")).startswith(("mp4a", "aac", "alac"))) or
                  (ext == "webm" and str(f.get("acodec", "")).startswith(("opus", "vorbis")))]
    audio = max(compatible or audio_formats, key=lambda f: f.get("abr") or f.get("tbr") or 0, default=None)
    if audio:
        result["selector"] += "+" + str(audio["format_id"])
        if not compatible:
            result["merge_ext"] = "mkv"
    return result


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
        return tr("unknown")
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return tr("unknown")


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
        raise ValueError(tr("time_format_error"))
    total = 0
    for part in parts:
        total = total * 60 + int(part)
    return float(total)


def estimated_size(fmt, duration, audio_size=0):
    size = estimated_size_bytes(fmt, duration, audio_size)
    return human_size(size) if size else tr("unknown")


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
    resolution = f"{display_height}p" if display_height else (fmt.get("resolution") or tr("unknown_resolution"))
    if width and height:
        resolution += f" ({width}×{height})"
    fps_text = f"{fps:g}fps" if fps else tr("unknown_fps")
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
    ext = str(fmt.get("ext") or "").lower()
    return (
        quality_height(fmt),
        int(ext == "mp4"),
        int(ext == "webm"),
        fmt.get("fps") or 0,
        fmt.get("tbr") or 0,
    )


class InfoWorker(QThread):
    result = pyqtSignal(dict, bytes)
    failed = pyqtSignal(str)

    def __init__(self, url):
        super().__init__()
        self.url = url

    @staticmethod
    def fetch(url, cancelled=None):
            engine = engine_path()
            if not engine.exists():
                raise RuntimeError(tr("engine_missing"))
            command = [str(engine), "--dump-single-json", "--skip-download", "--no-playlist", "--no-warnings"]
            cookie = cookie_path()
            if cookie:
                command += ["--cookies", str(cookie)]
            command.append(url)
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8", errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            started = time.monotonic()
            try:
                while True:
                    if (cancelled is not None and cancelled.is_set()) or time.monotonic() - started > 120:
                        raise RuntimeError("Metadata parsing cancelled or timed out")
                    try:
                        stdout, stderr = process.communicate(timeout=.25)
                        break
                    except subprocess.TimeoutExpired:
                        continue
                if process.returncode:
                    raise RuntimeError(stderr.strip() or tr("info_parse_failed"))
                info = json.loads(stdout)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
            thumb = fetch_best_cover(info, cancelled)
            return info, thumb

    def run(self):
        try:
            info, thumb = self.fetch(self.url)
            self.result.emit(info, thumb)
        except Exception as exc:
            self.failed.emit(str(exc))


class BatchInfoWorker(QThread):
    ready = pyqtSignal(list, list)
    progress = pyqtSignal(int, int)

    def __init__(self, entries, parent=None):
        super().__init__(parent)
        self.entries = entries
        self.cancelled = Event()

    def run(self):
        records, errors = {}, []
        with ThreadPoolExecutor(max_workers=3) as pool:
            jobs = {pool.submit(InfoWorker.fetch, entry["webpage_url"], self.cancelled): (index, entry)
                    for index, entry in enumerate(self.entries)}
            for done, job in enumerate(as_completed(jobs), 1):
                if self.cancelled.is_set():
                    for pending in jobs:
                        pending.cancel()
                    break
                index, entry = jobs[job]
                try:
                    info, thumbnail = job.result()
                    records[index] = {"info": info, "thumbnail": thumbnail, "url": entry["webpage_url"]}
                except Exception as exc:
                    errors.append(f"{entry.get('title', entry['id'])}: {exc}")
                self.progress.emit(done, len(jobs))
        if not self.cancelled.is_set():
            self.ready.emit([records[index] for index in sorted(records)], errors)


class IdolSearchWorker(QThread):
    results = pyqtSignal(list)
    progress = pyqtSignal(int, int)
    failed = pyqtSignal(str)

    def __init__(self, plan):
        super().__init__()
        self.plan = plan
        self.failed_queries = 0
        self.processes = set()
        self.process_lock = Lock()

    def cancel(self):
        self.requestInterruption()
        with self.process_lock:
            for process in self.processes:
                if process.poll() is None:
                    try:
                        process.kill()
                    except OSError:
                        pass

    def query(self, query, shorts=False):
        if self.isInterruptionRequested():
            return []
        if shorts:
            return search_short_pages(query, self.isInterruptionRequested)
        target = search_url(query, True) if shorts else "ytsearch60:" + query
        command = [str(engine_path()), "--ignore-config", "--flat-playlist", "--dump-single-json",
                   "--skip-download", "--no-warnings", "--socket-timeout", "12", "--retries", "1",
                   "--playlist-end", "60", "--extractor-args", "youtubetab:approximate_date", target]
        cookie = cookie_path()
        if cookie:
            command[1:1] = ["--cookies", str(cookie)]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        with self.process_lock:
            self.processes.add(process)
        started = time.monotonic()
        try:
            while True:
                if self.isInterruptionRequested() or time.monotonic() - started > 45:
                    process.kill()
                    process.communicate()
                    if self.isInterruptionRequested():
                        return []
                    raise TimeoutError("Search query timed out")
                try:
                    stdout, stderr = process.communicate(timeout=0.5)
                    break
                except subprocess.TimeoutExpired:
                    continue
            if self.isInterruptionRequested():
                return []
            if process.returncode:
                raise RuntimeError(stderr.strip()[-1200:] or "YouTube search failed")
            entries = flatten_search_entries(json.loads(stdout))
            return [{**entry, "_date_approximate": True} for entry in entries]
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
            with self.process_lock:
                self.processes.discard(process)

    def run(self):
        entries, errors, success = [], [], 0
        short_metadata = {}
        try:
            if not engine_path().is_file():
                raise RuntimeError(tr("engine_missing"))
            with ThreadPoolExecutor(max_workers=5) as pool, ThreadPoolExecutor(max_workers=4) as metadata_pool:
                # Include the date in Shorts queries so recent clips are not
                # crowded out by years of popular, unrelated-date Shorts.
                requests = [(query, shorts) for query in self.plan["queries"] for shorts in (False, True)]
                requests += [(query + " shorts", False) for query in self.plan.get("short_queries", [])]
                jobs = [pool.submit(self.query, query, shorts) for query, shorts in requests]
                for done, future in enumerate(as_completed(jobs), 1):
                    if self.isInterruptionRequested():
                        for job in jobs:
                            job.cancel()
                        break
                    try:
                        entries.extend(future.result())
                        success += 1
                        # Only enrich locally name/date-matched Shorts, once per ID.
                        # Search cards omit these fields; querying media formats for
                        # every result would be unnecessarily slow.
                        candidates = rank_results(entries, self.plan, require_context=False)[:300]
                        missing = [entry for entry in candidates if entry.get("_is_short")
                                   and entry["id"] not in short_metadata]
                        metadata_jobs = {metadata_pool.submit(complete_short_metadata, entry,
                                                             self.isInterruptionRequested): entry for entry in missing}
                        for metadata_job in as_completed(metadata_jobs):
                            entry = metadata_jobs[metadata_job]
                            if self.isInterruptionRequested():
                                break
                            try:
                                completed = metadata_job.result()
                            except Exception:
                                try:
                                    completed = complete_short_metadata(entry, self.isInterruptionRequested)
                                except Exception:
                                    completed = entry
                            short_metadata[entry["id"]] = completed
                        visible = [short_metadata.get(entry["id"], entry) for entry in candidates]
                        # Do not present a nameless/duration-less Shorts card as a
                        # successfully parsed result, or guess another person's identity.
                        visible = [entry for entry in visible if not entry.get("_is_short")
                                   or entry.get("_metadata_complete")]
                        self.results.emit(rank_results(visible, self.plan)[:300])
                    except Exception as exc:
                        errors.append(str(exc))
                    self.failed_queries = len(errors)
                    self.progress.emit(done, len(jobs))
            if not self.isInterruptionRequested() and not success:
                raise RuntimeError(errors[-1] if errors else "YouTube search failed")
        except Exception as exc:
            if not self.isInterruptionRequested():
                self.failed.emit(str(exc))


class LibraryWorker(QThread):
    ready = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, scanner, parent=None):
        super().__init__(parent)
        self.scanner = scanner

    def run(self):
        try:
            records = self.scanner.scan()
            if not self.scanner.cancelled.is_set():
                self.ready.emit(records)
        except Exception as exc:
            self.failed.emit(str(exc))


class SearchResultsPopup(QFrame):
    closed = pyqtSignal()

    def __init__(self, owner):
        super().__init__(owner, Qt.WindowType.Popup)
        self.owner = owner
        self.setObjectName("card")

    def hideEvent(self, event):
        arrow = self.owner.search_results_arrow
        self.owner._suppress_results_reopen = bool(
            QApplication.mouseButtons() & Qt.MouseButton.LeftButton
            and arrow.rect().contains(arrow.mapFromGlobal(QCursor.pos())))
        self.closed.emit()
        super().hideEvent(event)


class PreviewCacheWorker(QThread):
    ready = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, url, format_id, target):
        super().__init__()
        self.url = url
        self.format_id = str(format_id)
        self.target = Path(target)
        self.process = None
        self.stop_requested = False

    def request_stop(self):
        self.stop_requested = True
        process = self.process
        if process is not None and process.poll() is None:
            try:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   timeout=3, creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    process.terminate()
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                except OSError:
                    pass
            except OSError:
                pass

    def clean_cache(self):
        folder = self.target.parent
        files = [item for item in folder.iterdir() if item.is_file() and ".part" not in item.name]
        files.sort(key=lambda item: item.stat().st_mtime, reverse=True)
        total = 0
        for index, item in enumerate(files):
            try:
                size = item.stat().st_size
            except OSError:
                continue
            total += size
            if item == self.target:
                continue
            if index >= PREVIEW_CACHE_MAX_FILES or total > PREVIEW_CACHE_MAX_BYTES:
                try:
                    item.unlink(missing_ok=True)
                except OSError:
                    pass

    def run(self):
        try:
            self.target.parent.mkdir(parents=True, exist_ok=True)
            if self.target.exists() and self.target.stat().st_size > 0:
                self.clean_cache()
                self.ready.emit(str(self.target))
                return
            command = [
                str(engine_path()), self.url, "--no-playlist", "--no-warnings", "--no-color",
                "--continue", "--format", self.format_id, "--output", str(self.target),
                "--retries", "2", "--fragment-retries", "2", "--socket-timeout", "20",
            ]
            if "+" in self.format_id:
                command += ["--merge-output-format", self.target.suffix.lstrip(".")]
            ffmpeg = bundled_path("ffmpeg.exe")
            if ffmpeg.is_file():
                command += ["--ffmpeg-location", str(ffmpeg.parent)]
            cookie = cookie_path()
            if cookie:
                command += ["--cookies", str(cookie)]
            self.process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            _stdout, stderr = self.process.communicate()
            if self.stop_requested:
                return
            if self.process.returncode != 0 or not self.target.exists():
                raise RuntimeError((stderr or tr("preview_cache_failed")).strip()[-500:])
            self.clean_cache()
            self.ready.emit(str(self.target))
        except Exception as exc:
            if not self.stop_requested:
                self.failed.emit(str(exc))
        finally:
            self.process = None


class EngineCheckWorker(QThread):
    result = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def run(self):
        try:
            current = subprocess.run(
                [str(engine_path()), "--version"], capture_output=True, text=True, timeout=20,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            if current.returncode:
                raise RuntimeError(current.stderr.strip() or tr("engine_version_read_failed"))
            response = requests.get(
                "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest",
                headers={"Accept": "application/vnd.github+json", "User-Agent": APP_NAME}, timeout=20,
            )
            response.raise_for_status()
            release = response.json()
            asset = next((item for item in release.get("assets", []) if item.get("name") == "yt-dlp.exe"), None)
            if not asset or not asset.get("browser_download_url"):
                raise RuntimeError(tr("engine_asset_missing"))
            self.result.emit({
                "current": current.stdout.strip(),
                "latest": str(release.get("tag_name") or "").lstrip("v"),
                "url": asset["browser_download_url"],
            })
        except Exception as exc:
            self.failed.emit(str(exc))


class EngineUpdateWorker(QThread):
    succeeded = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, download_url, expected_version, parent=None):
        super().__init__(parent)
        self.download_url = download_url
        self.expected_version = expected_version

    def run(self):
        target = runtime_dir() / "yt_dlp.exe"
        backup = runtime_dir() / "yt_dlp.exe.backup"
        temporary = runtime_dir() / "yt_dlp-update.exe"
        replaced = False
        try:
            response = requests.get(self.download_url, stream=True, timeout=60)
            response.raise_for_status()
            with temporary.open("wb") as stream:
                for chunk in response.iter_content(1024 * 1024):
                    if chunk:
                        stream.write(chunk)
            validation = subprocess.run(
                [str(temporary), "--version"], capture_output=True, text=True, timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            version = validation.stdout.strip()
            if validation.returncode or not version:
                raise RuntimeError(validation.stderr.strip() or tr("engine_validation_failed"))
            source = target if target.exists() else engine_path()
            if source.exists():
                shutil.copy2(source, backup)
            os.replace(temporary, target)
            replaced = True
            self.succeeded.emit(version or self.expected_version)
        except Exception as exc:
            if replaced and backup.exists():
                try:
                    shutil.copy2(backup, target)
                except OSError:
                    pass
            self.failed.emit(str(exc))
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


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


class SearchResultCard(QWidget):
    clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.click_origin = None
        self.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self.click_origin = event.globalPosition().toPoint()
        elif event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            origin, self.click_origin = self.click_origin, None
            if origin is not None and (event.globalPosition().toPoint() - origin).manhattanLength() < QApplication.startDragDistance():
                self.clicked.emit()
                return True
        return super().eventFilter(watched, event)


class CoverLabel(QLabel):
    activated = pyqtSignal(int)

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.source_pixmap = None
        self.stack_entries = []
        self.stack_order = []
        self.layer_rects = []
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_image(self, data):
        self.stack_entries = []
        self.stack_order = []
        self.setCursor(Qt.CursorShape.ArrowCursor)
        pixmap = QPixmap()
        self.source_pixmap = pixmap if data and pixmap.loadFromData(data) else None
        if self.source_pixmap:
            self.setText("")
        else:
            self.clear()
            self.setText(tr("no_cover"))
        self.refresh()

    def set_stack(self, entries):
        if len(entries) == 1:
            self.set_image(entries[0].get("thumbnail", b""))
            return
        self.stack_entries = entries
        self.source_pixmap = None
        self.stack_order = list(range(len(entries)))
        self.clear()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update()

    def paintEvent(self, event):
        if not self.stack_entries:
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        visible = self.stack_order[:5]
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        step_x = max(18, min(28, self.width() // 16))
        step_y = max(10, min(16, self.height() // 14))
        width = max(1, self.width() - step_x * (len(visible) - 1) - 12)
        height = max(1, min(self.height() - step_y * (len(visible) - 1) - 12, width * 9 / 16))
        width = height * 16 / 9
        self.layer_rects = []
        for depth in reversed(range(len(visible))):
            index = visible[depth]
            rect = QRectF(6 + depth * step_x, 6 + depth * step_y, width, height)
            painter.setPen(QPen(QColor("#aab2c5"), 1))
            painter.setBrush(QColor("#242832"))
            painter.drawRoundedRect(rect, 5, 5)
            pixmap = QPixmap()
            if pixmap.loadFromData(self.stack_entries[index].get("thumbnail", b"")):
                scale = min((width - 4) / pixmap.width(), (height - 4) / pixmap.height())
                target_width, target_height = pixmap.width() * scale, pixmap.height() * scale
                target = QRectF(rect.center().x() - target_width / 2, rect.center().y() - target_height / 2,
                                target_width, target_height)
                painter.drawPixmap(target, pixmap, QRectF(pixmap.rect()))
            self.layer_rects.append((index, rect))
        if visible:
            rect = self.layer_rects[-1][1]
            painter.setPen(QColor("#ffffff"))
            painter.fillRect(QRectF(rect.x() + 5, rect.bottom() - 24, 58, 20), QColor("#333333"))
            painter.drawText(QRectF(rect.x() + 5, rect.bottom() - 24, 58, 20), Qt.AlignmentFlag.AlignCenter,
                             f"{visible[0] + 1}/{len(self.stack_entries)}")

    def raise_cover(self, index):
        if index in self.stack_order:
            self.stack_order.remove(index)
            self.stack_order.insert(0, index)
            self.activated.emit(index)
            self.update()

    def mousePressEvent(self, event):
        if self.stack_entries and event.button() == Qt.MouseButton.LeftButton:
            for index, rect in reversed(self.layer_rects):
                if rect.contains(event.position()):
                    self.raise_cover(index)
                    event.accept()
                    return
        super().mousePressEvent(event)

    def wheelEvent(self, event):
        if len(self.stack_order) > 1:
            if event.angleDelta().y() < 0:
                self.stack_order.append(self.stack_order.pop(0))
            else:
                self.stack_order.insert(0, self.stack_order.pop())
            self.activated.emit(self.stack_order[0])
            self.update()
            event.accept()
        else:
            super().wheelEvent(event)

    def refresh(self):
        if self.stack_entries:
            self.update()
            return
        if self.source_pixmap:
            ratio = self.devicePixelRatioF()
            scaled = self.source_pixmap.scaled(
                QSize(round(self.width() * ratio), round(self.height() * ratio)), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            scaled.setDevicePixelRatio(ratio)
            self.setPixmap(scaled)

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
    seek_started = pyqtSignal()
    seek_requested = pyqtSignal(int)
    seek_finished = pyqtSignal(int)

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
        if event.button() == Qt.MouseButton.LeftButton:
            self.seek_started.emit()
            self.seek_requested.emit(self.value_from_x(event.position().x()))
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.seek_requested.emit(self.value_from_x(event.position().x()))
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.seek_finished.emit(self.value_from_x(event.position().x()))
            event.accept()

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


class ClickableLabel(QLabel):
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class FlatItemDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        clean_option = QStyleOptionViewItem(option)
        clean_option.state &= ~QStyle.StateFlag.State_HasFocus
        super().paint(painter, clean_option, index)


class CompletionItemDelegate(FlatItemDelegate):
    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        return QSize(size.width(), max(32, round(38 * getattr(self.parent().window(), "ui_scale", 1))))


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
        self.overlay_popup = False
        self._suppress_popup_reopen = False
        self._intentional_popup_hide = False
        self.arrow_button = ChevronButton(self)
        self.arrow_button.pressed.connect(self.toggle_popup)
        self.setItemDelegate(FlatItemDelegate(self))
        self.view().setFocusPolicy(Qt.FocusPolicy.NoFocus)
        QApplication.instance().installEventFilter(self)

    def set_overlay_popup(self, enabled):
        self.overlay_popup = bool(enabled)

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
        if self._suppress_popup_reopen:
            self._suppress_popup_reopen = False
            return
        if self.popup_frame is not None and self.popup_frame.isVisible():
            self.hidePopup()
        else:
            self.showPopup()

    def showPopup(self):
        if self._suppress_popup_reopen:
            self._suppress_popup_reopen = False
            return
        if self.popup_frame is not None and self.popup_frame.isVisible():
            return
        host = self.window().centralWidget()
        if host is None:
            return
        popup_parent = self.window() if self.overlay_popup else host
        if self.popup_frame is None or self.popup_frame.parent() is not popup_parent:
            if self.popup_frame is not None:
                self.popup_frame.deleteLater()
            if self.overlay_popup:
                flags = Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
                self.popup_frame = QFrame(popup_parent, flags)
            else:
                self.popup_frame = QFrame(popup_parent)
            self.popup_frame.setObjectName("comboPopup")
            if self.overlay_popup:
                self.popup_frame.setStyleSheet(self.window().styleSheet())
            self.popup_frame.installEventFilter(self)
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
        position = (
            self.mapToGlobal(QPoint(0, self.height() - 1))
            if self.overlay_popup else self.mapTo(host, QPoint(0, self.height() - 1))
        )
        desired_height = min(max(1, self.count()), self.maxVisibleItems()) * row_height + 6
        if self.overlay_popup:
            screen = QApplication.screenAt(position) or QApplication.primaryScreen()
            available_bottom = screen.availableGeometry().bottom() if screen else position.y() + desired_height
            available_height = max(row_height + 2, available_bottom - position.y() + 1)
        else:
            available_height = max(row_height + 2, host.height() - position.y())
        popup_height = min(desired_height, available_height)
        self.popup_frame.setGeometry(position.x(), position.y(), self.width(), popup_height)
        self.arrow_up = True
        self.arrow_button.set_direction(True)
        self.popup_frame.raise_()
        self.popup_frame.show()
        self.update()

    def hidePopup(self):
        self._intentional_popup_hide = True
        if self.popup_frame is not None:
            self.popup_frame.hide()
        self._intentional_popup_hide = False
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
        if watched is self.popup_frame and event.type() == QEvent.Type.Hide:
            if self.overlay_popup and not self._intentional_popup_hide:
                global_position = QCursor.pos()
                over_combo = self.rect().contains(self.mapFromGlobal(global_position))
                left_pressed = bool(QApplication.mouseButtons() & Qt.MouseButton.LeftButton)
                self._suppress_popup_reopen = over_combo and left_pressed
            self.arrow_up = False
            self.arrow_button.set_direction(False)
            self.update()
        if (
            self.popup_frame is not None
            and self.popup_frame.isVisible()
            and event.type() == QEvent.Type.MouseButtonPress
        ):
            global_position = event.globalPosition().toPoint()
            inside_combo = self.rect().contains(self.mapFromGlobal(global_position))
            inside_popup = self.popup_frame.rect().contains(self.popup_frame.mapFromGlobal(global_position))
            if self.overlay_popup and inside_combo:
                self.hidePopup()
                return True
            if not inside_combo and not inside_popup:
                self.hidePopup()
        return super().eventFilter(watched, event)

    def paintEvent(self, event):
        super().paintEvent(event)


class DownloadManager(QWidget):
    progress_changed = pyqtSignal(float, str, str, str)
    state_changed = pyqtSignal(str, str)
    finished = pyqtSignal(bool)
    queue_requested = pyqtSignal()
    transient_failure = pyqtSignal(str)
    format_unavailable = pyqtSignal()
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
        self.auto_retry_count = 0
        self._attempt_resolved = False
        self._silent_restart = False
        self.retry_timer = QTimer(self)
        self.retry_timer.setSingleShot(True)
        self.retry_timer.timeout.connect(self.start)
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
        exe = engine_path()
        args = [self.url, "--no-playlist", "--continue", "--newline", "--no-color", "--no-warnings",
                "--format", self.selector, "--output", self.output_path, "--concurrent-fragments", "3",
                "--retries", "0", "--fragment-retries", "0", "--file-access-retries", "0",
                "--extractor-retries", "2", "--socket-timeout", "20",
                "--progress-template", "download:__YTDL__|%(info_dict.format_id)s|%(progress.status)s|%(progress.downloaded_bytes)s|%(progress.total_bytes)s|%(progress.total_bytes_estimate)s"]
        if self.overwrite:
            args += ["--force-overwrites"]
        if self.merge_ext:
            args += ["--merge-output-format", self.merge_ext]
        if self.download_cover:
            args += ["--write-thumbnail", "--convert-thumbnails", "jpg"]
        if self.section:
            # Keep the selected source streams intact and cut on nearby keyframes.
            # This follows the fast lossless path used by LosslessCut: stream copy
            # instead of yt-dlp's --force-keyframes-at-cuts full re-encode.
            args += [
                "--download-sections", f"*{self.section[0]:.3f}-{self.section[1]:.3f}",
                "--downloader", "ffmpeg", "--no-force-keyframes-at-cuts",
                "--downloader-args", "ffmpeg:-progress pipe:2 -nostats",
                "--downloader-args", "ffmpeg_o:-avoid_negative_ts make_zero",
                "--postprocessor-args", "Merger+ffmpeg_o:-avoid_negative_ts make_zero",
                "--fixup", "force",
            ]
            if self.merge_ext == "mp4":
                args += [
                    "--downloader-args", "ffmpeg_o:-movflags +faststart",
                    "--postprocessor-args", "Merger+ffmpeg_o:-movflags +faststart",
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
        self.retry_timer.stop()
        if self.process is not None:
            self.process.deleteLater()
            self.process = None
        exe, args = self.command()
        if not exe.exists():
            self.state = "failed"
            self.state_changed.emit("failed", tr("engine_missing"))
            self.finished.emit(False)
            return
        self.output_log = ""
        self.output_buffer = ""
        self._attempt_resolved = False
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.finished.connect(self.process_finished)
        self.process.errorOccurred.connect(self.process_error)
        self.stop_reason, self.state = None, "running"
        self.last_speed_sample_time = time.monotonic()
        self.last_speed_sample_bytes = sum(self.component_downloaded.values())
        self.last_progress_emit = 0.0
        silent_restart = self._silent_restart
        self._silent_restart = False
        if not silent_restart:
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
        if self.sender() is not None and self.sender() is not self.process:
            return
        if self._attempt_resolved:
            return
        self._attempt_resolved = True
        if self.stop_reason == "pause":
            self.state = "paused"
            self.state_changed.emit("paused", tr("paused_state"))
            return
        if self.stop_reason == "clear":
            self.state = "cleared"
            return
        if exit_code == 0:
            self.auto_retry_count = 0
            self.state = "finished"
            self.state_changed.emit("finished", tr("finished"))
            self.finished.emit(True)
            return
        self.handle_attempt_failure(self.last_error())

    def process_error(self, _error):
        if self.stop_reason or self._attempt_resolved:
            return
        if self.sender() is not None and self.sender() is not self.process:
            return
        self._attempt_resolved = True
        detail = self.process.errorString() if self.process is not None else tr("process_start_failed")
        if self.process is not None and self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()
        self.handle_attempt_failure(detail)

    def is_retryable_failure(self, detail):
        message = str(detail or "").lower()
        permanent_errors = (
            "no space left", "disk full", "permission denied", "access is denied",
            "requested format is not available", "unsupported url", "invalid url",
            "unable to open for writing", "file name too long",
        )
        return not any(marker in message for marker in permanent_errors)

    def handle_attempt_failure(self, detail):
        message = str(detail or "")
        lowered = message.lower()
        if "requested format is not available" in lowered:
            self.format_unavailable.emit()
        if any(marker in lowered for marker in ("403", "429", "timed out", "connection reset", "remote end closed")):
            self.transient_failure.emit(message)
        if self.is_retryable_failure(detail) and self.auto_retry_count < MAX_AUTO_RETRIES:
            delay = AUTO_RETRY_DELAYS_MS[min(self.auto_retry_count, len(AUTO_RETRY_DELAYS_MS) - 1)]
            self.auto_retry_count += 1
            self.state = "running"
            self._silent_restart = True
            self.retry_timer.start(delay)
            return
        self.state = "failed"
        self.state_changed.emit("failed", detail or self.last_error())
        self.finished.emit(False)

    def last_error(self):
        lines = [x.strip() for x in self.output_log.splitlines() if x.strip()]
        errors = [x for x in lines if "ERROR:" in x]
        return (errors[-1] if errors else (lines[-1] if lines else tr("process_failed")))[:260]

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
            if self.retry_timer.isActive():
                self.retry_timer.stop()
                self._silent_restart = False
                self.state = "paused"
                self.state_changed.emit("paused", tr("paused_state"))
                return
            self.stop_process("pause")
            self.state_changed.emit("running", tr("pausing_state"))

    def resume(self):
        if self.state == "paused":
            self.state = "waiting"
            self.state_changed.emit("waiting", tr("waiting"))
            self.queue_requested.emit()

    def retry(self):
        if self.state != "failed":
            return
        self.retry_timer.stop()
        self.auto_retry_count = 0
        self.stop_reason = None
        self._silent_restart = False
        self.state = "waiting"
        self.state_changed.emit("waiting", tr("waiting"))
        self.queue_requested.emit()

    def open_folder(self):
        output = Path(self.output_path)
        folder = output.parent.resolve()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def clear_files(self):
        self.retry_timer.stop()
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
        self.retry_timer.stop()
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
        self.detail_label = ClickableLabel(tr("waiting"))
        self.detail_label.setObjectName("taskDetail")
        self.detail_label.clicked.connect(self.toggle_error_details)
        text.addWidget(self.name_label)
        text.addWidget(self.detail_label)
        top.addLayout(text, 1)
        self.copy_link_btn = QPushButton()
        self.open_video_btn = QPushButton()
        self.copy_link_btn.setObjectName("taskIcon")
        self.open_video_btn.setObjectName("taskIcon")
        self.copy_link_btn.setToolTip(tr("copy_link"))
        self.open_video_btn.setToolTip(tr("open_video"))
        if qta is not None:
            try:
                self.copy_link_btn.setIcon(qta.icon("fa5s.copy", color=ACCENT))
                self.open_video_btn.setIcon(qta.icon("fa5s.external-link-alt", color=ACCENT))
            except Exception:
                self.copy_link_btn.setText("▣")
                self.open_video_btn.setText("↗")
        else:
            self.copy_link_btn.setText("▣")
            self.open_video_btn.setText("↗")
        self.copy_link_btn.clicked.connect(self.copy_video_link)
        self.open_video_btn.clicked.connect(self.open_video_link)
        top.addWidget(self.copy_link_btn)
        top.addWidget(self.open_video_btn)
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
        self.retry_btn = QPushButton(tr("retry"))
        self.open_btn = QPushButton(tr("open_folder"))
        self.clear_btn = QPushButton(tr("clear"))
        self.hide_btn = QPushButton(tr("hide_task"))
        for button in (self.pause_btn, self.retry_btn, self.open_btn, self.clear_btn, self.hide_btn):
            button.setObjectName("taskSmall")
            button.setFixedHeight(25)
        self.retry_btn.hide()
        self.clear_btn.setObjectName("danger")
        self.pause_btn.clicked.connect(self.pause_or_resume)
        self.retry_btn.clicked.connect(manager.retry)
        self.open_btn.clicked.connect(manager.open_folder)
        self.clear_btn.clicked.connect(self.request_clear)
        self.hide_btn.clicked.connect(self.request_hide)
        buttons.addWidget(self.pause_btn)
        buttons.addWidget(self.retry_btn)
        buttons.addWidget(self.open_btn)
        buttons.addWidget(self.clear_btn)
        buttons.addStretch()
        buttons.addWidget(self.hide_btn)
        root.addLayout(buttons)
        self.error_panel = QWidget()
        error_layout = QHBoxLayout(self.error_panel)
        error_layout.setContentsMargins(0, 2, 0, 0)
        error_layout.setSpacing(5)
        self.error_text = QLabel()
        self.error_text.setObjectName("errorDetail")
        self.error_text.setWordWrap(True)
        self.error_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.copy_error_btn = QPushButton(tr("copy_error"))
        self.copy_error_btn.setObjectName("taskSmall")
        self.copy_error_btn.clicked.connect(self.copy_error)
        error_layout.addWidget(self.error_text, 1)
        error_layout.addWidget(self.copy_error_btn, 0, Qt.AlignmentFlag.AlignTop)
        self.error_panel.hide()
        root.addWidget(self.error_panel)
        self.error_detail = ""
        self.error_expanded = False
        manager.progress_changed.connect(self.update_progress)
        manager.state_changed.connect(self.update_state)
        manager.finished.connect(self.download_finished)
        self.set_scale(1.0)

    def set_scale(self, scale):
        self.current_scale = scale
        self.update_card_height()
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
        icon_size = max(20, round(25 * scale))
        self.copy_link_btn.setFixedSize(icon_size, icon_size)
        self.open_video_btn.setFixedSize(icon_size, icon_size)
        self.copy_link_btn.setIconSize(QSize(max(11, round(13 * scale)), max(11, round(13 * scale))))
        self.open_video_btn.setIconSize(QSize(max(11, round(13 * scale)), max(11, round(13 * scale))))
        for button in (self.pause_btn, self.retry_btn, self.open_btn, self.clear_btn, self.hide_btn):
            button.setFixedHeight(max(20, round(25 * scale)))
        self.copy_error_btn.setFixedHeight(max(20, round(25 * scale)))

    def update_progress(self, percent, speed, eta, size):
        self.progress.setValue(int(max(0, min(100, percent)) * 10))
        self.percent_label.setText(f"{percent:.1f}%")
        parts = [x for x in (size, speed, tr("remaining", value=eta) if eta and eta != "NA" else "") if x and x != "NA"]
        detail = " · ".join(parts) or tr("downloading")
        self.detail_label.setText(detail)
        self.detail_label.setToolTip(detail)

    def update_state(self, state, detail):
        self.last_state = state
        self.detail_label.setText(detail or state)
        self.detail_label.setToolTip(detail or state)
        self.pause_btn.setText(tr("resume") if state == "paused" else tr("pause"))
        self.pause_btn.setEnabled(state in ("running", "paused"))
        self.retry_btn.setVisible(state == "failed")
        self.detail_label.setCursor(
            Qt.CursorShape.PointingHandCursor if state == "failed" else Qt.CursorShape.ArrowCursor
        )
        if state == "failed":
            self.error_detail = detail or state
            self.detail_label.setToolTip(f"{tr('error_details')}\n{self.error_detail}")
        else:
            self.error_detail = ""
            self.error_expanded = False
            self.error_panel.hide()
            self.update_card_height()
        self.setProperty("failed", state == "failed")
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def download_finished(self, success):
        if success:
            self.progress.setValue(1000)
            self.percent_label.setText("100%")

    def pause_or_resume(self):
        self.manager.resume() if self.manager.state == "paused" else self.manager.pause()

    def copy_video_link(self):
        QApplication.clipboard().setText(self.manager.url)

    def open_video_link(self):
        QDesktopServices.openUrl(QUrl(self.manager.url))

    def update_card_height(self):
        scale = getattr(self, "current_scale", 1.0)
        height = 210 if getattr(self, "error_expanded", False) else 116
        self.setMaximumHeight(max(86, round(height * scale)))

    def toggle_error_details(self):
        if self.manager.state != "failed" or not self.error_detail:
            return
        self.error_expanded = not self.error_expanded
        self.error_text.setText(self.error_detail)
        self.error_panel.setVisible(self.error_expanded)
        self.update_card_height()

    def copy_error(self):
        if self.error_detail:
            QApplication.clipboard().setText(self.error_detail)

    def retranslate_ui(self):
        self.pause_btn.setText(tr("resume") if self.manager.state == "paused" else tr("pause"))
        self.retry_btn.setText(tr("retry"))
        self.open_btn.setText(tr("open_folder"))
        self.clear_btn.setText(tr("clear"))
        self.hide_btn.setText(tr("hide_task"))
        self.copy_link_btn.setToolTip(tr("copy_link"))
        self.open_video_btn.setToolTip(tr("open_video"))
        self.copy_error_btn.setText(tr("copy_error"))
        if self.manager.state == "waiting":
            self.detail_label.setText(tr("waiting"))
        elif self.manager.state == "finished":
            self.detail_label.setText(tr("finished"))

    def request_clear(self):
        answer = QMessageBox.question(self, tr("clear_task_title"), tr("clear_task_message"),
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self.manager.clear_files()
            self.removed.emit(self)

    def request_hide(self):
        if self.manager.state in ("running", "paused"):
            answer = QMessageBox.question(
                self, tr("hide_task_title"), tr("hide_task_message"),
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
        self.batch_worker = None
        self.batch_items = []
        self.selected_search_ids = set()
        self.search_checks = {}
        self.search_worker = None
        self.library_worker = None
        self.library_records = []
        self.library_scanned_at = 0
        self.library_error = ""
        self.library_rescan_requested = False
        self.search_entries = []
        self.search_progress_value = (0, 0)
        self.search_failed_count = 0
        self.selected_idol_id = None
        self.idol_input_alias = ""
        self._suppress_results_reopen = False
        self.catalogue_error = ""
        try:
            self.idol_catalogue = IdolCatalogue(bundled_path("idol_names/idol_aliases.json"))
        except (OSError, ValueError, KeyError) as exc:
            self.idol_catalogue = None
            self.catalogue_error = str(exc)
        try:
            self.idol_preferences = json.loads(str(self.settings.value("idol_identity_preferences", "{}")))
            if not isinstance(self.idol_preferences, dict):
                self.idol_preferences = {}
        except (ValueError, TypeError):
            self.idol_preferences = {}
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
        saved_concurrency = int(self.settings.value("concurrent_downloads", DEFAULT_CONCURRENT_DOWNLOADS))
        self.max_concurrent_downloads = max(1, min(MAX_CONCURRENT_DOWNLOADS, saved_concurrency))
        self.adaptive_concurrency_cap = None
        self.recent_transient_failures = []
        self.adaptive_restore_timer = QTimer(self)
        self.adaptive_restore_timer.setSingleShot(True)
        self.adaptive_restore_timer.timeout.connect(self.restore_adaptive_concurrency)
        self.preview_cache_worker = None
        self.retired_preview_workers = set()
        self.preview_cache_path = None
        self.preview_cache_error = ""
        self.preview_waiting_cache = False
        self.preview_waiting_play = True
        self.preview_restore_after_load = None
        self.engine_check_worker = None
        self.engine_update_worker = None
        self.section_labels = []
        self.setWindowTitle(APP_NAME)
        app_icon = bundled_path("icon.ico")
        if app_icon.exists():
            self.setWindowIcon(QIcon(str(app_icon)))
        self.resize(1020, 830)
        self.setMinimumSize(860, 700)
        self.build_ui()
        self.preview_fps = 30.0
        self.preview_duration_ms = 1
        self.preview_target_ms = 0
        self.preview_last_position_ms = 0
        self.preview_seek_inflight = False
        self.preview_resume_after_seek = False
        self.preview_scrubbing = False
        self.preview_seek_retry_count = 0
        self.preview_seek_timer = QTimer(self)
        self.preview_seek_timer.setSingleShot(True)
        self.preview_seek_timer.setInterval(70)
        self.preview_seek_timer.timeout.connect(self.commit_preview_seek)
        self.preview_spinner_guard = QTimer(self)
        self.preview_spinner_guard.setSingleShot(True)
        self.preview_spinner_guard.timeout.connect(self.preview_spinner.stop)
        self.apply_responsive_scale(force=True)

    def build_search_ui(self, page):
        self.group_user_selected = False
        self.search_card = QFrame()
        self.search_card.setObjectName("card")
        row = QHBoxLayout(self.search_card)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(8)
        self.group_edit, self.idol_edit, self.search_date_edit = QLineEdit(), QLineEdit(), QLineEdit()
        for edit in (self.group_edit, self.idol_edit, self.search_date_edit):
            edit.setMinimumWidth(0)
            edit.setClearButtonEnabled(True)
        self.search_date_edit.setMaxLength(6)
        self.search_date_edit.setMaximumWidth(185)
        self.search_spinner = LoadingSpinner()
        row.addWidget(self.group_edit, 2)
        row.addWidget(self.idol_edit, 3)
        row.addWidget(self.search_date_edit, 2)
        row.addWidget(self.search_spinner)
        row.addWidget(self.search_results_arrow)
        self.search_clear_btn = QPushButton()
        self.search_clear_btn.clicked.connect(self.clear_search_inputs)
        row.addWidget(self.search_clear_btn)
        row.addWidget(self.search_btn)
        page.addWidget(self.search_card)
        self.group_model, self.member_model = QStringListModel(self), QStringListModel(self)
        self.group_completer, self.member_completer = QCompleter(self.group_model, self), QCompleter(self.member_model, self)
        for edit, completer in ((self.group_edit, self.group_completer), (self.idol_edit, self.member_completer)):
            completer.setCompletionMode(QCompleter.CompletionMode.UnfilteredPopupCompletion)
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setMaxVisibleItems(8)
            edit.setCompleter(completer)
            popup = completer.popup()
            popup.setParent(self, Qt.WindowType.Popup)
            popup.setTextElideMode(Qt.TextElideMode.ElideRight)
            popup.setMinimumWidth(0)
            popup.setUniformItemSizes(True)
            popup.setWordWrap(False)
            popup.setMouseTracking(True)
            popup.viewport().setMouseTracking(True)
            popup.setItemDelegate(CompletionItemDelegate(popup))
            popup.setVerticalScrollBar(MinimalVerticalScrollBar(popup))
            popup.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        QApplication.instance().applicationStateChanged.connect(self.completion_application_state)
        QApplication.instance().installEventFilter(self)
        self.member_labels = {}
        self.member_completion_ids = {
            member_display_name(m) + " · " + m["group"]: m["id"]
            for m in self.idol_catalogue.members
        } if self.idol_catalogue else {}
        self.member_resolve_timer = QTimer(self)
        self.member_resolve_timer.setSingleShot(True)
        self.member_resolve_timer.setInterval(250)
        self.member_resolve_timer.timeout.connect(lambda: self.resolve_remembered_member(format_input=False))
        self.group_edit.textEdited.connect(self.search_group_edited)
        self.group_completer.activated[str].connect(self.choose_search_group)
        self.group_edit.editingFinished.connect(self.resolve_search_group)
        self.idol_edit.textEdited.connect(self.search_member_edited)
        self.member_completer.activated[str].connect(self.choose_search_member_label)
        self.idol_edit.editingFinished.connect(self.resolve_remembered_member)
        self.idol_edit.installEventFilter(self)
        self.search_date_edit.returnPressed.connect(self.start_idol_search)
        self.results_popup = SearchResultsPopup(self)
        popup_layout = QVBoxLayout(self.results_popup)
        popup_layout.setContentsMargins(12, 10, 12, 10)
        popup_header = QHBoxLayout()
        self.results_status = QLabel()
        self.results_status.setWordWrap(True)
        self.results_close_btn = QPushButton("×")
        self.results_close_btn.setFixedWidth(30)
        self.results_close_btn.clicked.connect(self.results_popup.hide)
        popup_header.addWidget(self.results_status, 1)
        popup_header.addWidget(self.results_close_btn)
        popup_layout.addLayout(popup_header)
        self.results_list = QListWidget()
        self.results_list.setObjectName("comboPopupList")
        self.results_list.setVerticalScrollBar(MinimalVerticalScrollBar())
        self.results_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        popup_layout.addWidget(self.results_list)
        batch_row = QHBoxLayout()
        self.select_all_results = QCheckBox(search_tr("select_all"))
        self.select_all_results.toggled.connect(self.select_all_search_results)
        self.batch_parse_btn = QPushButton(search_tr("batch_parse", count=0))
        self.batch_parse_btn.clicked.connect(self.parse_selected_results)
        self.batch_parse_btn.setEnabled(False)
        batch_row.addWidget(self.select_all_results)
        batch_row.addStretch()
        batch_row.addWidget(self.batch_parse_btn)
        popup_layout.addLayout(batch_row)
        self.results_popup.closed.connect(lambda: self.search_results_arrow.set_direction(False))
        self.search_render_timer = QTimer(self)
        self.search_render_timer.setSingleShot(True)
        self.search_render_timer.setInterval(600)
        self.search_render_timer.timeout.connect(self.render_search_results)
        self.thumbnail_network = QNetworkAccessManager(self)
        self.search_thumbnails, self.thumbnail_replies, self.thumbnail_labels = {}, {}, {}
        self.translate_search_ui()

    def eventFilter(self, watched, event):
        if hasattr(self, "member_completer") and event.type() == QEvent.Type.MouseButtonPress:
            for edit, completer in ((self.group_edit, self.group_completer), (self.idol_edit, self.member_completer)):
                popup = completer.popup()
                inside_popup = watched is popup or (isinstance(watched, QWidget) and popup.isAncestorOf(watched))
                if watched is not edit and not inside_popup:
                    popup.hide()
        if hasattr(self, "idol_edit") and watched is self.idol_edit and event.type() == QEvent.Type.FocusIn:
            if event.reason() != Qt.FocusReason.PopupFocusReason:
                QTimer.singleShot(0, self.show_focused_member_candidates)
        return super().eventFilter(watched, event)

    def show_focused_member_candidates(self):
        if self.idol_edit.hasFocus():
            self.update_member_candidates(show=True)

    def completion_application_state(self, state):
        if state != Qt.ApplicationState.ApplicationActive:
            self.group_completer.popup().hide()
            self.member_completer.popup().hide()

    def hideEvent(self, event):
        if hasattr(self, "member_completer"):
            self.group_completer.popup().hide()
            self.member_completer.popup().hide()
        super().hideEvent(event)

    def size_completion_popup(self, edit, completer):
        completer.popup().setFixedWidth(max(100, edit.width()))

    def translate_search_ui(self):
        self.search_btn.setText(tr("cancel") if self.search_worker else search_tr("search"))
        self.search_clear_btn.setText("清空" if CURRENT_LANGUAGE == "zh" else tr("clear"))
        self.group_edit.setPlaceholderText(search_tr("group"))
        self.idol_edit.setPlaceholderText(search_tr("member"))
        self.search_date_edit.setPlaceholderText(search_tr("date"))
        self.search_results_arrow.setToolTip(search_tr("search_results"))
        if hasattr(self, "batch_parse_btn"):
            self.select_all_results.setText(search_tr("select_all"))
            self.update_batch_selection()
        if hasattr(self, "save_all_covers_btn"):
            self.save_all_covers_btn.setText(search_tr("save_all_covers"))
        self.update_search_status()
        if self.search_entries:
            self.render_search_results()

    def clear_search_inputs(self):
        self.member_resolve_timer.stop()
        for edit in (self.group_edit, self.idol_edit, self.search_date_edit):
            edit.blockSignals(True)
            edit.clear()
            edit.blockSignals(False)
        self.selected_idol_id = None
        self.idol_input_alias = ""
        self.group_user_selected = False
        self.group_completer.popup().hide()
        self.member_completer.popup().hide()
        self.member_model.setStringList([])
        self.member_labels = {}
        self.group_edit.setFocus()

    def search_group_edited(self, text):
        self.group_user_selected = bool(text)
        self.selected_idol_id = None
        if self.idol_catalogue:
            self.group_model.setStringList([g["name"] for g in self.idol_catalogue.group_matches(text)])
        self.size_completion_popup(self.group_edit, self.group_completer)
        self.update_member_candidates()

    def choose_search_group(self, text):
        self.group_edit.setText(text)
        self.group_user_selected = True
        self.selected_idol_id = None
        self.update_member_candidates()

    def resolve_search_group(self):
        if self.idol_catalogue and self.group_edit.text().strip():
            group = self.idol_catalogue.resolve_group(self.group_edit.text())
            if group:
                self.group_edit.setText(group["name"])

    def search_member_edited(self, text):
        completion_id = self.member_completion_ids.get(text.strip())
        if completion_id:
            self.choose_search_member(completion_id)
            QTimer.singleShot(0, lambda: self.finalize_member_completion(completion_id))
            return
        self.selected_idol_id = None
        self.idol_input_alias = text.strip()
        if text and not self.group_user_selected:
            self.group_edit.clear()
        self.update_member_candidates()
        self.member_resolve_timer.start()

    def update_member_candidates(self, show=False):
        if not self.idol_catalogue:
            return
        group = self.idol_catalogue.resolve_group(self.group_edit.text()) if self.group_edit.text() else None
        candidates = self.idol_catalogue.member_matches(self.idol_edit.text(), group["name"] if group else None)
        if self.group_edit.text().strip() and not group:
            allowed_groups = {g["name"] for g in self.idol_catalogue.group_matches(self.group_edit.text())}
            candidates = [m for m in candidates if m["group"] in allowed_groups]
        preferred = self.idol_preferences.get(normalize_idol(self.idol_edit.text()))
        candidates.sort(key=lambda m: (m["id"] != preferred, member_display_name(m).casefold(), m["group"]))
        self.member_labels = {member_display_name(m) + " · " + m["group"]: m["id"] for m in candidates}
        self.member_model.setStringList(list(self.member_labels))
        self.size_completion_popup(self.idol_edit, self.member_completer)
        if show and candidates and (group or self.idol_edit.text()):
            self.member_completer.complete()

    def choose_search_member_label(self, label):
        member_id = self.member_completion_ids.get(label)
        if member_id:
            self.choose_search_member(member_id)
            QTimer.singleShot(0, lambda: self.finalize_member_completion(member_id))

    def finalize_member_completion(self, member_id):
        member = self.idol_catalogue.by_id[member_id]
        name = member_display_name(member)
        if self.idol_edit.text().strip() in {name, name + " · " + member["group"]}:
            self.choose_search_member(member_id)
            self.member_completer.popup().hide()

    def choose_search_member(self, member_id, format_input=True):
        self.member_resolve_timer.stop()
        member = self.idol_catalogue.by_id[member_id]
        alias = self.idol_input_alias or self.idol_edit.text().strip()
        self.selected_idol_id = member_id
        if format_input:
            self.idol_edit.setText(member_display_name(member))
        self.group_edit.setText(member["group"])
        for name in (alias, member["stage_name"], member_display_name(member)):
            if name:
                self.idol_preferences[normalize_idol(name)] = member_id
        self.settings.setValue("idol_identity_preferences", json.dumps(self.idol_preferences, ensure_ascii=False))

    def resolve_remembered_member(self, format_input=True):
        if self.selected_idol_id or not self.idol_catalogue:
            return
        text = self.idol_edit.text().strip()
        group = self.idol_catalogue.resolve_group(self.group_edit.text()) if self.group_edit.text() else None
        if self.group_edit.text().strip() and not group:
            return
        completion_id = self.member_completion_ids.get(text)
        if completion_id:
            member = self.idol_catalogue.by_id[completion_id]
            if not group or member["group"] == group["name"]:
                self.choose_search_member(completion_id, format_input=format_input)
                return
        matches = self.idol_catalogue.member_matches(text, group["name"] if group else None, exact=True) if text else []
        preferred = self.idol_preferences.get(normalize_idol(text))
        member = next((m for m in matches if m["id"] == preferred), None)
        if member or len(matches) == 1:
            self.choose_search_member((member or matches[0])["id"], format_input=format_input)

    def start_idol_search(self):
        if self.search_worker:
            self.search_worker.cancel()
            self.search_btn.setEnabled(False)
            return
        if not self.idol_catalogue:
            QMessageBox.warning(self, search_tr("search"), self.catalogue_error)
            return
        try:
            from idol_search import date_variants
            date_variants(self.search_date_edit.text().strip())
        except ValueError:
            QMessageBox.warning(self, search_tr("search"), search_tr("date_error"))
            return
        self.resolve_search_group()
        if self.group_edit.text().strip() and not self.idol_catalogue.resolve_group(self.group_edit.text()):
            groups = self.idol_catalogue.group_matches(self.group_edit.text())
            if not groups:
                QMessageBox.warning(self, search_tr("search"), search_tr("identity_error"))
                return
            choice, accepted = QInputDialog.getItem(self, search_tr("group"), search_tr("group"), [g["name"] for g in groups], 0, False)
            if not accepted:
                return
            self.choose_search_group(choice)
        self.resolve_remembered_member()
        name = self.idol_edit.text().strip()
        group = self.idol_catalogue.resolve_group(self.group_edit.text()) if self.group_edit.text() else None
        member = self.idol_catalogue.by_id.get(self.selected_idol_id)
        if name and not member:
            matches = self.idol_catalogue.member_matches(name, group["name"] if group else None)
            labels = {member_display_name(m) + " · " + m["group"]: m["id"] for m in matches}
            if not labels:
                QMessageBox.warning(self, search_tr("search"), search_tr("identity_error"))
                return
            choice, accepted = QInputDialog.getItem(self, search_tr("choose_identity"), search_tr("choose_identity"), list(labels), 0, False)
            if not accepted:
                return
            self.choose_search_member(labels[choice])
            member = self.idol_catalogue.by_id[self.selected_idol_id]
            group = self.idol_catalogue.resolve_group(member["group"])
        if not group:
            QMessageBox.warning(self, search_tr("search"), search_tr("identity_error"))
            return
        plan = make_search_plan(member, group, self.idol_input_alias or name, self.search_date_edit.text().strip(), self.idol_catalogue)
        self.selected_search_ids.clear()
        self.search_entries = []
        self.search_progress_value = (0, len(plan["queries"]))
        self.search_failed_count = 0
        self.results_list.clear()
        self.thumbnail_labels.clear()
        for reply in list(self.thumbnail_replies.values()):
            reply.abort()
        self.search_results_arrow.show()
        self.search_spinner.start()
        self.search_worker = IdolSearchWorker(plan)
        self.search_worker.results.connect(self.receive_search_results)
        self.search_worker.progress.connect(self.search_progress_changed)
        self.search_worker.failed.connect(lambda message: QMessageBox.warning(self, search_tr("search"), message))
        self.search_worker.finished.connect(self.search_finished)
        self.search_btn.setText(tr("cancel"))
        self.update_search_status()
        self.show_search_results()
        self.search_worker.start()

    def receive_search_results(self, entries):
        self.search_entries = entries
        self.start_library_scan()
        if not self.search_render_timer.isActive():
            self.search_render_timer.start()

    def search_progress_changed(self, done, total):
        self.search_progress_value = (done, total)
        self.update_search_status()

    def update_search_status(self):
        if not hasattr(self, "results_status"):
            return
        if self.search_worker:
            done, total = self.search_progress_value
            text = search_tr("search_progress", done=done, total=total, count=len(self.search_entries))
        else:
            text = search_tr("search_summary", count=len(self.search_entries), failed=self.search_failed_count)
        self.results_status.setText(text)

    def search_finished(self):
        worker = self.search_worker
        if worker is not None:
            self.search_failed_count = worker.failed_queries
            self.search_worker = None
            worker.deleteLater()
        self.search_spinner.stop()
        self.search_btn.setEnabled(True)
        self.search_btn.setText(search_tr("search"))
        self.render_search_results()
        self.update_search_status()

    def toggle_search_results(self):
        if self._suppress_results_reopen:
            self._suppress_results_reopen = False
            return
        if self.results_popup.isVisible():
            self.results_popup.hide()
        else:
            self.show_search_results()

    def show_search_results(self):
        anchor = self.search_card
        self.results_popup.setStyleSheet(self.styleSheet())
        position = anchor.mapToGlobal(QPoint(0, anchor.height()))
        screen = self.screen().availableGeometry()
        height = min(max(220, int(self.height() * 0.56)), max(120, screen.bottom() - position.y()))
        self.results_popup.setGeometry(position.x(), position.y(), anchor.width(), height)
        self.results_popup.show()
        self.results_popup.raise_()
        self.search_results_arrow.set_direction(True)

    def render_search_results(self):
        scroll = self.results_list.verticalScrollBar().value()
        self.results_list.clear()
        self.thumbnail_labels.clear()
        self.search_checks.clear()
        action_icons = {name: self._button_icon(name) for name in ("fa5s.copy", "fa5s.external-link-alt")}
        for entry in self.search_entries:
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 100))
            self.results_list.addItem(item)
            card = SearchResultCard()
            row = QHBoxLayout(card)
            row.setContentsMargins(6, 6, 6, 6)
            checked = QCheckBox()
            checked.setChecked(entry["id"] in self.selected_search_ids)
            checked.toggled.connect(lambda state, video_id=entry["id"]: self.toggle_search_selection(video_id, state))
            self.search_checks[entry["id"]] = checked
            card.clicked.connect(checked.toggle)
            row.addWidget(checked)
            thumb = QLabel("—")
            thumb.setFixedSize(128, 72)
            thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.thumbnail_labels[entry["id"]] = thumb
            if entry["id"] in self.search_thumbnails:
                thumb.setPixmap(self.search_thumbnails[entry["id"]])
            else:
                self.request_search_thumbnail(entry)
            row.addWidget(thumb)
            text_column = QVBoxLayout()
            title = QLabel(entry.get("title") or "—")
            title.setWordWrap(True)
            title.setMaximumHeight(48)
            title.setToolTip(title.text())
            text_column.addWidget(title)
            upload = str(entry.get("upload_date") or "")
            if not upload and entry.get("timestamp"):
                try:
                    upload = datetime.fromtimestamp(float(entry["timestamp"]), timezone.utc).strftime("%Y%m%d")
                except (ValueError, TypeError, OSError, OverflowError):
                    pass
            if len(upload) == 8 and upload.isdigit():
                upload = upload[:4] + "-" + upload[4:6] + "-" + upload[6:]
            else:
                upload = "—"
            author = entry.get("uploader") or entry.get("channel") or "—"
            duration = seconds_text(entry["duration"]) if entry.get("duration") is not None else "—"
            meta = QLabel(f"{author} · {duration} · {upload}")
            meta.setToolTip(meta.text())
            meta.setObjectName("subtitle")
            meta.setWordWrap(True)
            text_column.addWidget(meta)
            row.addLayout(text_column, 1)
            tooltip = self.duplicate_tooltip(entry)
            if tooltip:
                warning = QLabel("!")
                warning.setFixedSize(22, 22)
                warning.setAlignment(Qt.AlignmentFlag.AlignCenter)
                warning.setStyleSheet("background:#fff0cf;color:#ae6a00;border-radius:11px;font-weight:700;")
                warning.setToolTip(tooltip)
                row.addWidget(warning)
            download = QPushButton(search_tr("search_download"))
            download.clicked.connect(lambda _checked=False, url=entry["webpage_url"]: self.parse_search_result(url))
            download.setEnabled(self.info_worker is None or not self.info_worker.isRunning())
            for name, tip, callback in (("fa5s.copy", "copy_link", self.copy_search_link),
                                         ("fa5s.external-link-alt", "open_video", self.open_search_link)):
                action = QPushButton()
                action.setObjectName("taskIcon")
                action.setFixedSize(26, 26)
                action.setIcon(action_icons[name])
                action.setIconSize(QSize(14, 14))
                action.setToolTip(tr(tip))
                action.clicked.connect(lambda _checked=False, url=entry["webpage_url"], fn=callback: fn(url))
                row.addWidget(action)
            row.addWidget(download)
            # Labels preserve hover tooltips; buttons/checkboxes keep their own
            # actions and must not also toggle selection through the card.
            for label in card.findChildren(QLabel):
                label.installEventFilter(card)
            self.results_list.setItemWidget(item, card)
        self.results_list.verticalScrollBar().setValue(scroll)
        self.update_search_status()
        self.update_batch_selection()

    def copy_search_link(self, url):
        QApplication.clipboard().setText(url)

    def open_search_link(self, url):
        QDesktopServices.openUrl(QUrl(url))

    def toggle_search_selection(self, video_id, checked):
        if checked:
            self.selected_search_ids.add(video_id)
        else:
            self.selected_search_ids.discard(video_id)
        self.update_batch_selection()

    def update_batch_selection(self):
        available = {entry["id"] for entry in self.search_entries}
        count = len(available & self.selected_search_ids)
        self.batch_parse_btn.setText(search_tr("batch_parse", count=count))
        self.batch_parse_btn.setEnabled(count > 0 and self.batch_worker is None
                                       and self.info_worker is None)
        self.select_all_results.blockSignals(True)
        self.select_all_results.setChecked(bool(available) and available <= self.selected_search_ids)
        self.select_all_results.blockSignals(False)

    def select_all_search_results(self, checked):
        for checkbox in list(self.search_checks.values()):
            checkbox.setChecked(checked)

    def parse_selected_results(self):
        if self.batch_worker is not None or self.info_worker is not None:
            return
        entries = [entry for entry in self.search_entries if entry["id"] in self.selected_search_ids]
        if not entries:
            return
        if len(entries) == 1:
            # One selected result is a normal video, not a one-item batch.
            # Reuse the full parsing lifecycle so audio, clipping, filename and
            # format controls stay identical to pasting/analysing a single URL.
            self.parse_search_result(entries[0]["webpage_url"])
            return
        self.results_popup.hide()
        self.cancel_clip_selection()
        self.stop_preview_cache()
        self.info = None
        self.refresh_duplicate_indicator()
        self.batch_items = []
        self.download_btn.setEnabled(False)
        self.parse_btn.setEnabled(False)
        self.loading_spinner.start()
        self.format_combo.setEnabled(False)
        self.range_combo.setEnabled(False)
        self.audio_combo.setEnabled(False)
        self.filename_edit.setEnabled(False)
        self.save_all_covers_btn.hide()
        self.save_cover_btn.setEnabled(False)
        self.batch_worker = BatchInfoWorker(entries, self)
        self.batch_worker.progress.connect(lambda done, total: self.range_label.setText(
            search_tr("batch_loading", done=done, total=total)))
        self.batch_worker.ready.connect(self.batch_info_ready)
        self.batch_worker.finished.connect(self.batch_parsing_finished)
        self.update_batch_selection()
        self.batch_worker.start()

    def batch_info_ready(self, records, errors):
        for record in records:
            formats = self.video_format_options(record["info"])
            if formats:
                record["format"] = formats[0][1]
                self.batch_items.append(record)
            else:
                errors.append(f"{record['info'].get('title', record['url'])}: {tr('preview_unavailable_message')}")
        self.cover_label.set_stack(self.batch_items)
        if self.batch_items:
            self.batch_cover_selected(0)
        self.save_all_covers_btn.setVisible(len(self.batch_items) > 1)
        self.format_combo.clear()
        self.format_combo.addItem(search_tr("batch_ready", count=len(self.batch_items)))
        self.range_label.setText(search_tr("batch_ready", count=len(self.batch_items)))
        self.filename_edit.setText(search_tr("batch_ready", count=len(self.batch_items)))
        self.filename_edit.setCursorPosition(0)
        self.download_btn.setEnabled(bool(self.batch_items))
        if errors:
            QMessageBox.warning(self, tr("parse_failed_title"), "\n\n".join(errors[:10]))

    def batch_parsing_finished(self):
        worker = self.batch_worker
        if worker is self.sender():
            self.batch_worker = None
            worker.deleteLater()
        self.loading_spinner.stop()
        self.parse_btn.setEnabled(True)
        self.update_batch_selection()

    def batch_cover_selected(self, index):
        if not 0 <= index < len(self.batch_items):
            return
        record = self.batch_items[index]
        info = record["info"]
        self.video_title.setText(info.get("title", ""))
        self.meta_label.setText(f"{info.get('uploader') or info.get('channel') or '—'} · {seconds_text(info.get('duration') or 0)}")
        self.save_cover_btn.setEnabled(bool(record.get("thumbnail")))
        self.cover_label.setToolTip(info.get("title", ""))

    def selected_cover(self):
        if len(self.batch_items) == 1:
            return self.batch_items[0]
        if self.batch_items and self.cover_label.stack_order:
            return self.batch_items[self.cover_label.stack_order[0]]
        return {"info": self.info or {}, "thumbnail": self.thumbnail_bytes}

    def request_search_thumbnail(self, entry):
        video_id = entry["id"]
        if video_id in self.thumbnail_replies:
            return
        thumbnails = entry.get("thumbnails") or []
        url = next((t.get("url") for t in reversed(thumbnails) if t.get("url")), None)
        url = url or "https://i.ytimg.com/vi/" + video_id + "/mqdefault.jpg"
        if QUrl(url).scheme() != "https":
            return
        request = QNetworkRequest(QUrl(url))
        request.setTransferTimeout(8000)
        reply = self.thumbnail_network.get(request)
        self.thumbnail_replies[video_id] = reply
        reply.finished.connect(lambda: self.search_thumbnail_finished(video_id, reply))

    def search_thumbnail_finished(self, video_id, reply):
        if self.thumbnail_replies.get(video_id) is reply:
            self.thumbnail_replies.pop(video_id, None)
        data = bytes(reply.readAll())
        reply.deleteLater()
        pixmap = QPixmap()
        if len(data) <= 2 * 1024 * 1024 and pixmap.loadFromData(data):
            pixmap = pixmap.scaled(128, 72, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.search_thumbnails[video_id] = pixmap
            if len(self.search_thumbnails) > 300:
                self.search_thumbnails.pop(next(iter(self.search_thumbnails)))
            label = self.thumbnail_labels.get(video_id)
            if label is not None:
                label.setPixmap(pixmap)

    def parse_search_result(self, url):
        if self.info_worker is not None and self.info_worker.isRunning():
            return
        self.results_popup.hide()
        self.url_edit.setText(url)
        self.parse_current_url()

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
            "fa5s.sync-alt": QStyle.StandardPixmap.SP_BrowserReload,
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
        speed_width = max(48, round(52 * scale))
        speed_height = max(24, round(26 * scale))
        self.half_speed_btn.setFixedSize(speed_width, speed_height)
        self.double_speed_btn.setFixedSize(speed_width, speed_height)

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
        self.engine_update_btn = QPushButton()
        self.engine_update_btn.setObjectName("headerIcon")
        self.engine_update_btn.setIcon(self._button_icon("fa5s.sync-alt"))
        self.engine_update_btn.setToolTip(tr("check_engine_update"))
        self.engine_update_btn.clicked.connect(self.check_engine_update)
        header.addWidget(self.engine_update_btn, 0, Qt.AlignmentFlag.AlignTop)
        self.language_btn = LanguageButton()
        self.language_btn.setToolTip(tr("language_tip"))
        self.language_btn.clicked.connect(self.show_language_menu)
        self.language_menu = QMenu(self)
        self._suppress_language_menu_reopen = False
        self.language_menu.aboutToHide.connect(self.language_menu_about_to_hide)
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
        self.search_results_arrow = ChevronButton()
        self.search_results_arrow.setFixedSize(26, 30)
        self.search_results_arrow.pressed.connect(self.toggle_search_results)
        self.search_results_arrow.hide()
        self.search_btn = QPushButton(search_tr("search"))
        self.search_btn.clicked.connect(self.start_idol_search)
        url_layout.addWidget(self.parse_btn)
        url_layout.addWidget(self.loading_spinner)
        page.addWidget(url_card)
        self.build_search_ui(page)

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
        self.cover_label.activated.connect(self.batch_cover_selected)
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
        meta_row = QHBoxLayout()
        meta_row.addWidget(self.meta_label, 1)
        self.duplicate_indicator = QLabel("!")
        self.duplicate_indicator.setObjectName("duplicateIndicator")
        self.duplicate_indicator.setFixedSize(22, 22)
        self.duplicate_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.duplicate_indicator.hide()
        meta_row.addWidget(self.duplicate_indicator)
        left.addLayout(meta_row)
        cover_actions = QHBoxLayout()
        self.cover_check, self.save_cover_btn = QCheckBox(tr("cover_with_video")), QPushButton(tr("save_cover"))
        self.save_cover_btn.setEnabled(False)
        self.save_cover_btn.clicked.connect(self.save_cover)
        cover_actions.addWidget(self.cover_check)
        cover_actions.addStretch()
        cover_actions.addWidget(self.save_cover_btn)
        left.addLayout(cover_actions)
        self.save_all_covers_btn = QPushButton(search_tr("save_all_covers"))
        self.save_all_covers_btn.clicked.connect(self.save_all_covers)
        self.save_all_covers_btn.hide()
        left.addWidget(self.save_all_covers_btn)
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
        self.audio_combo.set_overlay_popup(True)
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
        self.tasks_section.setProperty("plain", True)
        task_header.addWidget(self.tasks_section)
        task_header.addStretch()
        self.concurrent_label = QLabel(tr("concurrent_downloads"))
        self.concurrent_label.setObjectName("subtitle")
        self.concurrency_combo = ChevronComboBox()
        self.concurrency_combo.setObjectName("concurrencyCombo")
        self.concurrency_combo.setMaxVisibleItems(MAX_CONCURRENT_DOWNLOADS)
        for value in range(1, MAX_CONCURRENT_DOWNLOADS + 1):
            self.concurrency_combo.addItem(str(value), value)
        self.concurrency_combo.setCurrentIndex(self.max_concurrent_downloads - 1)
        self.concurrency_combo.setFixedWidth(58)
        self.concurrency_combo.currentIndexChanged.connect(self.concurrency_changed)
        task_header.addWidget(self.concurrent_label)
        task_header.addWidget(self.concurrency_combo)
        self.task_count = QLabel(f"0/{MAX_TASKS}")
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
        self.clip_section.setProperty("plain", True)
        clip_header.addWidget(self.clip_section)
        clip_header.addStretch()
        self.half_speed_btn = QPushButton("0.5×")
        self.double_speed_btn = QPushButton("2×")
        self.half_speed_btn.setObjectName("speedToggle")
        self.double_speed_btn.setObjectName("speedToggle")
        self.half_speed_btn.setCheckable(True)
        self.double_speed_btn.setCheckable(True)
        self.half_speed_btn.setToolTip(tr("half_speed"))
        self.double_speed_btn.setToolTip(tr("double_speed"))
        self.half_speed_btn.toggled.connect(lambda checked: self.toggle_preview_rate(0.5, checked))
        self.double_speed_btn.toggled.connect(lambda checked: self.toggle_preview_rate(2.0, checked))
        clip_header.addWidget(self.half_speed_btn)
        clip_header.addWidget(self.double_speed_btn)
        self.preview_spinner = LoadingSpinner()
        clip_header.addWidget(self.preview_spinner)
        self.clip_time_label = QLabel("00:00.000 / 00:00.000")
        self.clip_time_label.setObjectName("subtitle")
        clip_header.addWidget(self.clip_time_label)
        clip_box.addLayout(clip_header)
        self.clip_video = ClickableVideoWidget()
        self.clip_video.setMinimumHeight(170)
        self.clip_video.setStyleSheet("background:#090a0d; border-radius:8px;")
        self.clip_video.setToolTip("")
        self.clip_video.clicked.connect(self.toggle_preview)
        self.clip_video_frame = AspectRatioContainer(self.clip_video)
        clip_box.addWidget(self.clip_video_frame, 1)
        self.clip_timeline = RangeTimeline()
        self.clip_timeline.seek_started.connect(self.begin_preview_scrub)
        self.clip_timeline.seek_requested.connect(self.seek_preview)
        self.clip_timeline.seek_finished.connect(self.end_preview_scrub)
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
            self.preview_audio.setVolume(0.75)
            self.preview_audio.setMuted(False)
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
            QMessageBox.warning(self, tr("preview_init_title"), tr("preview_init_message", value=exc))
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
        self.search_spinner.set_scale(scale)
        self.preview_spinner.set_scale(scale)
        self.format_combo.set_scale(scale)
        self.range_combo.set_scale(scale)
        self.audio_combo.set_scale(scale)
        self.concurrency_combo.set_scale(scale)
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
        if self._suppress_language_menu_reopen:
            self._suppress_language_menu_reopen = False
            return
        if self.language_menu.isVisible():
            self.language_menu.hide()
            return
        for code, action in self.language_actions.items():
            action.setChecked(code == CURRENT_LANGUAGE)
        position = self.language_btn.mapToGlobal(QPoint(0, self.language_btn.height() + 2))
        self.language_menu.popup(position)

    def language_menu_about_to_hide(self):
        global_position = QCursor.pos()
        over_button = self.language_btn.rect().contains(self.language_btn.mapFromGlobal(global_position))
        left_pressed = bool(QApplication.mouseButtons() & Qt.MouseButton.LeftButton)
        self._suppress_language_menu_reopen = over_button and left_pressed

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
        self.engine_update_btn.setToolTip(tr("check_engine_update"))
        self.url_edit.setPlaceholderText(tr("url_placeholder"))
        self.parse_btn.setText(tr("paste_parse"))
        self.translate_search_ui()
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
        self.concurrent_label.setText(tr("concurrent_downloads"))
        self.clip_section.setText(tr("clip_panel"))
        self.clip_video.setToolTip("")
        self.frame_back_btn.setText(tr("frame_back"))
        self.frame_forward_btn.setText(tr("frame_forward"))
        self.half_speed_btn.setToolTip(tr("half_speed"))
        self.double_speed_btn.setToolTip(tr("double_speed"))
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
        if self.batch_items:
            self.batch_cover_selected(self.cover_label.stack_order[0])
            value = search_tr("batch_ready", count=len(self.batch_items))
            self.range_label.setText(value)
            self.filename_edit.setText(value)
            self.filename_edit.setCursorPosition(0)
            self.format_combo.setItemText(0, value)
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
        self.concurrency_combo.set_theme(self.dark_mode)
        self.clip_timeline.set_theme(self.dark_mode)
        self.language_btn.set_theme(self.dark_mode)
        self.engine_update_btn.setIcon(self._button_icon("fa5s.sync-alt"))
        self.search_results_arrow.set_theme(self.dark_mode)
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{ background:{bg}; color:{text}; font-family:'Segoe UI','Microsoft YaHei UI'; font-size:{px(13, 10)}px; }}
            QFrame#card, QFrame#taskCard {{ background:{card}; border:1px solid {border}; border-radius:{px(12, 8)}px; }}
            QFrame#taskCard[failed="true"] {{ background:{danger_bg}; border:1px solid {DANGER}; }}
            QFrame#taskCard[failed="true"] QLabel {{ background:transparent; }}
            QLabel#appTitle {{ font-family:'Eras Demi ITC'; font-size:{px(31, 23)}px; font-weight:400; }}
            QLabel#brandSubtitle {{ color:{muted}; font-family:'Palatino Linotype'; font-size:{px(13, 11)}px; font-style:italic; font-weight:600; letter-spacing:{px(1)}px; padding-left:{px(3, 2)}px; }}
            QLabel#subtitle, QLabel#taskDetail {{ color:{muted}; background:transparent; border:0; }}
            QLabel#cover {{ background:#101218; color:#90949d; border-radius:{px(9, 6)}px; }}
            QLabel#videoTitle {{ font-size:{px(16, 12)}px; font-weight:650; }}
            QLabel#sectionTitle {{ background:{button}; font-size:{px(14, 11)}px; font-weight:700; padding-left:{px(5, 3)}px; border-radius:{px(4, 3)}px; }}
            QLabel#sectionTitle[plain="true"] {{ background:transparent; }}
            QLineEdit, QComboBox {{ background:{field}; border:1px solid {border}; border-radius:{px(7, 5)}px; padding:{px(8, 5)}px {px(10, 7)}px; min-height:{px(20, 15)}px; }}
            QLineEdit:focus, QComboBox:focus {{ border:1px solid {accent}; }}
            QComboBox {{ padding-right:{px(30, 22)}px; }}
            QComboBox::drop-down {{ subcontrol-origin:padding; subcontrol-position:top right; width:{px(28, 21)}px; border:0; background:transparent; }}
            QComboBox::down-arrow {{ image:none; width:0; height:0; }}
            QComboBox#concurrencyCombo {{ padding-left:{px(8, 6)}px; padding-right:{px(28, 21)}px; }}
            QComboBox#concurrencyCombo::drop-down {{ width:0; }}
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
            QPushButton#speedToggle {{ padding:0 {px(4, 2)}px; }}
            QPushButton#speedToggle:checked {{ color:white; background:{accent}; }}
            QPushButton#taskIcon {{ background:transparent; padding:0; border-radius:{px(5, 4)}px; }}
            QPushButton#taskIcon:hover {{ background:{button_hover}; }}
            QPushButton#headerIcon {{ background:transparent; padding:{px(6, 4)}px; border-radius:{px(6, 4)}px; }}
            QPushButton#headerIcon:hover {{ background:{button_hover}; }}
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
        if self.audio_combo.popup_frame is not None:
            self.audio_combo.popup_frame.setStyleSheet(self.styleSheet())
        self.results_popup.setStyleSheet(self.styleSheet())
        for completer in (self.group_completer, self.member_completer):
            completer.popup().setStyleSheet(f"QListView {{ background:{card}; color:{text}; border:1px solid {border}; padding:0; }} QListView::item {{ padding:0 8px; border:0; margin:0; }} QListView::item:hover, QListView::item:selected {{ background:{popup_hover}; color:{text}; border:0; }}")
        self.duplicate_indicator.setStyleSheet("background:#fff0cf;color:#ae6a00;border-radius:11px;font-weight:700;")
        self.refresh_duplicate_indicator()
        if hasattr(self, "play_btn"):
            playing = bool(
                self.preview_player is not None
                and self.preview_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
            )
            self.set_play_button_state(playing)
            self.sync_clip_control_sizes(scale)

    def concurrency_changed(self, index):
        value = self.concurrency_combo.itemData(index)
        if not value:
            return
        self.max_concurrent_downloads = int(value)
        self.adaptive_concurrency_cap = None
        self.recent_transient_failures.clear()
        self.adaptive_restore_timer.stop()
        self.settings.setValue("concurrent_downloads", self.max_concurrent_downloads)
        self.schedule_tasks()

    def effective_concurrency(self):
        if self.adaptive_concurrency_cap is None:
            return self.max_concurrent_downloads
        return min(self.max_concurrent_downloads, self.adaptive_concurrency_cap)

    def schedule_tasks(self):
        if self.engine_update_worker is not None and self.engine_update_worker.isRunning():
            return
        active = sum(1 for manager, _card in self.tasks if manager.state == "running")
        available = max(0, self.effective_concurrency() - active)
        if available <= 0:
            return
        for manager, _card in self.tasks:
            if manager.state != "waiting":
                continue
            manager.start()
            available -= 1
            if available <= 0:
                break

    def handle_transient_failure(self, _detail):
        now = time.monotonic()
        self.recent_transient_failures = [stamp for stamp in self.recent_transient_failures if now - stamp <= 60]
        self.recent_transient_failures.append(now)
        if len(self.recent_transient_failures) >= 2:
            current_cap = self.adaptive_concurrency_cap or self.max_concurrent_downloads
            self.adaptive_concurrency_cap = max(1, current_cap - 1)
            self.recent_transient_failures.clear()
            self.adaptive_restore_timer.start(5 * 60 * 1000)

    def restore_adaptive_concurrency(self):
        self.adaptive_concurrency_cap = None
        self.recent_transient_failures.clear()
        self.schedule_tasks()

    def format_became_unavailable(self):
        QMessageBox.warning(self, tr("format_unavailable_title"), tr("format_unavailable_message"))

    @staticmethod
    def version_tuple(value):
        return tuple(int(part) for part in re.findall(r"\d+", str(value)))

    def check_engine_update(self):
        if any(manager.state in ("running", "waiting") for manager, _card in self.tasks):
            QMessageBox.warning(self, tr("update_failed_title"), tr("update_busy_message"))
            return
        if self.engine_check_worker is not None and self.engine_check_worker.isRunning():
            return
        self.engine_update_btn.setEnabled(False)
        worker = EngineCheckWorker(self)
        self.engine_check_worker = worker
        worker.result.connect(self.engine_check_result)
        worker.failed.connect(lambda message: QMessageBox.warning(self, tr("update_failed_title"), message))
        worker.finished.connect(self.engine_check_finished)
        worker.start()

    def engine_check_result(self, result):
        current, latest = result.get("current", ""), result.get("latest", "")
        if self.version_tuple(current) >= self.version_tuple(latest):
            QMessageBox.information(self, tr("up_to_date_title"), tr("up_to_date_message", value=current))
            return
        answer = QMessageBox.question(
            self, tr("update_available_title"),
            tr("update_available_message", current=current, latest=latest),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        worker = EngineUpdateWorker(result["url"], latest, self)
        self.engine_update_worker = worker
        worker.succeeded.connect(self.engine_update_succeeded)
        worker.failed.connect(lambda message: QMessageBox.warning(self, tr("update_failed_title"), message))
        worker.finished.connect(self.engine_update_finished)
        worker.start()

    def engine_check_finished(self):
        worker = self.engine_check_worker
        self.engine_check_worker = None
        if worker is not None:
            worker.deleteLater()
        if self.engine_update_worker is None:
            self.engine_update_btn.setEnabled(True)

    def engine_update_succeeded(self, version):
        QMessageBox.information(self, tr("update_success_title"), tr("update_success_message", value=version))

    def engine_update_finished(self):
        worker = self.engine_update_worker
        self.engine_update_worker = None
        if worker is not None:
            worker.deleteLater()
        self.engine_update_btn.setEnabled(True)
        self.schedule_tasks()

    def stop_preview_cache(self):
        worker = self.preview_cache_worker
        if worker is None:
            return
        self.preview_cache_worker = None
        try:
            worker.disconnect()
        except TypeError:
            pass
        if worker.isRunning():
            self.retired_preview_workers.add(worker)
            worker.finished.connect(lambda w=worker: self.retire_preview_worker(w))
            worker.request_stop()
            if not worker.isRunning():
                self.retire_preview_worker(worker)
        else:
            worker.deleteLater()

    def retire_preview_worker(self, worker):
        if worker not in self.retired_preview_workers:
            return
        self.retired_preview_workers.discard(worker)
        worker.deleteLater()

    def start_preview_cache(self):
        self.stop_preview_cache()
        self.preview_cache_path = None
        self.preview_cache_error = ""
        fmt = preview_package(self.info)
        if not fmt:
            return
        video_id = clean_filename((self.info or {}).get("id") or "preview")
        format_id = clean_filename(fmt["selector"])
        ext = str(fmt["merge_ext"]).lower()
        target = preview_cache_dir() / f"{video_id}-{format_id}-av2.{ext}"
        if target.exists() and target.stat().st_size > 0:
            self.preview_cache_path = target
            self.range_label.setToolTip(tr("preview_cache_ready"))
            return
        self.range_label.setToolTip(tr("preview_cache_loading"))
        worker = PreviewCacheWorker(self.url_edit.text().strip(), fmt["selector"], target)
        self.preview_cache_worker = worker
        worker.ready.connect(self.preview_cache_ready)
        worker.failed.connect(self.preview_cache_failed)
        worker.finished.connect(self.preview_cache_finished)
        worker.start()

    def preview_cache_ready(self, path):
        target = Path(path)
        if target.exists() and target.stat().st_size > 0:
            self.preview_cache_path = target
            self.preview_cache_error = ""
            self.range_label.setToolTip(tr("preview_cache_ready"))
            if self.preview_player is not None and self.clip_panel.isVisible():
                position = self.preview_last_position_ms
                if self.preview_waiting_cache:
                    position = self.preview_target_ms
                playing = self.preview_waiting_play if self.preview_waiting_cache else (
                    self.preview_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState)
                rate = self.preview_player.playbackRate()
                self.preview_waiting_cache = False
                self.preview_restore_after_load = (position, playing, rate)
                self.preview_player.setSource(QUrl.fromLocalFile(str(target)))

    def preview_cache_failed(self, message):
        self.preview_cache_error = message
        self.preview_cache_path = None
        self.range_label.setToolTip(message)
        if self.preview_waiting_cache:
            self.preview_spinner.stop()
            self.clip_time_label.setText(tr("preview_load_failed"))

    def preview_cache_finished(self):
        worker = self.preview_cache_worker
        if worker is not None and worker is self.sender():
            self.preview_cache_worker = None
            worker.deleteLater()

    def paste_and_parse(self):
        self.url_edit.setText(QApplication.clipboard().text().strip())
        self.parse_current_url()

    def parse_current_url(self):
        if self.batch_worker is not None:
            return
        if self.info_worker is not None and self.info_worker.isRunning():
            return
        url = self.url_edit.text().strip()
        if not is_supported_url(url):
            QMessageBox.warning(self, tr("invalid_link_title"), tr("invalid_link_message"))
            return
        self.stop_preview_cache()
        self.cancel_clip_selection()
        self.batch_items = []
        self.save_all_covers_btn.hide()
        self.duplicate_indicator.hide()
        self.range_combo.setEnabled(True)
        self.filename_edit.setEnabled(True)
        self.preview_cache_path = None
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
        worker = self.info_worker
        if worker is not None and not worker.isRunning():
            self.info_worker = None
            worker.deleteLater()
        self.parse_btn.setEnabled(True)
        self.loading_spinner.stop()
        if self.search_entries:
            self.render_search_results()

    def info_ready(self, info, thumbnail):
        self.info, self.thumbnail_bytes = info, thumbnail
        self.refresh_duplicate_indicator()
        self.start_library_scan()
        self.video_title.setText(info.get("title") or tr("untitled_video"))
        duration = info.get("duration") or 0
        self.clip_start, self.clip_end = 0, float(duration)
        uploader = info.get("uploader") or info.get("channel") or tr("unknown_channel")
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
        self.start_preview_cache()

    def info_failed(self, message):
        QMessageBox.critical(self, tr("parse_failed_title"), message)

    def start_library_scan(self, force=False):
        if self.library_worker is not None:
            self.library_rescan_requested |= force
            return
        if not force and time.monotonic() - self.library_scanned_at < 30:
            return
        ffprobe = bundled_path("ffprobe.exe")
        if not ffprobe.is_file():
            found = shutil.which("ffprobe")
            if not found:
                self.library_error = "FFprobe unavailable"
                return
            ffprobe = Path(found)
        scanner = LibraryScanner(Path(r"D:\youtube videos"), ffprobe,
            runtime_dir() / ".media-library-cache.json", runtime_dir() / ".download-source-index.json")
        self.library_worker = LibraryWorker(scanner, self)
        self.library_worker.ready.connect(self.library_scan_ready)
        self.library_worker.failed.connect(lambda detail: setattr(self, "library_error", detail))
        self.library_worker.finished.connect(self.library_scan_finished)
        self.library_worker.start()

    def library_scan_ready(self, records):
        self.library_records = records
        self.library_scanned_at = time.monotonic()
        self.refresh_duplicate_indicator()
        self.render_search_results()

    def library_scan_finished(self):
        worker = self.library_worker
        if worker is self.sender():
            self.library_worker = None
            worker.deleteLater()
            if self.library_rescan_requested and not worker.scanner.cancelled.is_set():
                self.library_rescan_requested = False
                self.start_library_scan(force=True)

    def duplicate_tooltip(self, info):
        matches = duplicate_matches(self.library_records, info)
        if not matches:
            return ""
        lines = []
        for item in matches[:10]:
            state = search_tr("downloaded_source" if item["confirmed_source"] else "possible_duplicate")
            if item["partial"]:
                state += " · " + search_tr("duplicate_clip")
            lines.append(f"{state}\n{item['width']}×{item['height']} · {item['fps']:.2f} fps · {item['codec']} · {seconds_text(item['duration'])} · {item['size']/1024/1024:.1f} MB\n{item['path']}")
        lines.append(search_tr("duplicate_advisory"))
        return "\n\n".join(lines)

    def refresh_duplicate_indicator(self):
        tooltip = self.duplicate_tooltip(self.info or {})
        self.duplicate_indicator.setToolTip(tooltip)
        self.duplicate_indicator.setVisible(bool(tooltip))

    def record_completed_download(self, manager, title):
        try:
            remember_download(runtime_dir() / ".download-source-index.json", manager.output_path,
                              manager.url, title, manager.section)
        except OSError:
            return
        self.start_library_scan(force=True)

    def fill_formats(self, info):
        self.format_combo.clear()
        for label, data in self.video_format_options(info):
            self.format_combo.addItem(label, data)
        self.format_combo.setEnabled(self.format_combo.count() > 0)

    def video_format_options(self, info):
        options = []
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
            options.append((format_label(fmt, info.get("duration"), audio_size), data))
        return options

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
            bitrate_text = f"{bitrate:.0f} kbps" if bitrate else tr("unknown_audio_quality")
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
        selected = self.selected_cover()
        thumbnail = selected.get("thumbnail", b"")
        if not thumbnail:
            return
        initial = self.settings.value("last_folder", str(Path.home()))
        name = selected["info"].get("title") if self.batch_items else self.filename_edit.text()
        path, _ = QFileDialog.getSaveFileName(self, tr("save_cover_dialog"), str(Path(initial) / (clean_filename(name) + ".jpg")), "JPEG (*.jpg)")
        if path:
            if not path.lower().endswith((".jpg", ".jpeg")):
                path += ".jpg"
            try:
                self.write_cover_image(thumbnail, path)
                self.settings.setValue("last_folder", str(Path(path).parent))
                QMessageBox.information(self, tr("save_success_title"), tr("cover_saved_message"))
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, tr("save_failed_title"), str(exc))

    @staticmethod
    def write_cover_image(data, path):
        pixmap = QPixmap()
        if not pixmap.loadFromData(data) or not pixmap.save(str(path), "JPEG", 95):
            raise ValueError(tr("save_failed_title"))

    def save_all_covers(self):
        folder = QFileDialog.getExistingDirectory(self, search_tr("save_all_covers"),
            str(self.settings.value("last_folder", str(Path.home()))))
        if not folder:
            return
        self.settings.setValue("last_folder", folder)
        for record in self.batch_items:
            if not record.get("thumbnail"):
                continue
            target = Path(folder) / (clean_filename(record["info"].get("title")) + ".jpg")
            resolved = self.resolve_existing_file(target)
            if not resolved:
                continue
            try:
                self.write_cover_image(record["thumbnail"], resolved[0])
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, tr("save_failed_title"), str(exc))
        QMessageBox.information(self, tr("save_success_title"), tr("cover_saved_message"))

    def range_mode_changed(self, index):
        if index == 0:
            self.cancel_clip_selection(reset_combo=False)
            self.range_label.setText(tr("full_video_info"))
            return
        if not self.info:
            self.range_combo.blockSignals(True)
            self.range_combo.setCurrentIndex(0)
            self.range_combo.blockSignals(False)
            QMessageBox.warning(self, tr("not_parsed_title"), tr("not_parsed_message"))
            return
        self.show_clip_selector()

    def preview_stream_url(self):
        selected = select_preview_format(self.info)
        if not selected:
            return None
        self.preview_fps = float(selected.get("fps") or 30)
        return selected.get("url")

    def show_clip_selector(self):
        url = self.preview_stream_url()
        if not url:
            QMessageBox.warning(self, tr("preview_unavailable_title"), tr("preview_unavailable_message"))
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
        self.preview_seek_timer.stop()
        self.preview_spinner_guard.stop()
        self.preview_player.stop()
        self.preview_duration_ms = duration_ms
        self.preview_target_ms = 0
        self.preview_last_position_ms = 0
        self.preview_seek_inflight = False
        self.preview_resume_after_seek = False
        self.preview_scrubbing = False
        self.preview_seek_retry_count = 0
        self.set_preview_rate(1.0)
        self.clip_start, self.clip_end = 0.0, duration_ms / 1000
        self.clip_applied = False
        self.clip_timeline.set_duration(duration_ms)
        self.clip_timeline.set_selection(0, duration_ms, False)
        self.clip_panel.show()
        self.preview_spinner.start()
        self.preview_waiting_cache = False
        self.preview_waiting_play = True
        self.preview_restore_after_load = None
        if self.preview_cache_path and Path(self.preview_cache_path).exists():
            self.preview_player.setSource(QUrl.fromLocalFile(str(self.preview_cache_path)))
            self.preview_player.play()
        elif select_preview_format(self.info).get("acodec") in (None, "none"):
            self.preview_waiting_cache = True
            self.clip_time_label.setText(tr("preview_cache_loading"))
            if self.preview_cache_worker is None:
                self.start_preview_cache()
        else:
            self.preview_player.setSource(QUrl(url))
            self.preview_player.play()
        self.set_play_button_state(True)
        value = f"{seconds_text_ms(self.clip_start)} – {seconds_text_ms(self.clip_end)}"
        self.range_label.setText(tr("choosing_range", value=value))

    def preview_frame_duration_ms(self):
        return max(1, round(1000 / max(1.0, self.preview_fps)))

    def clamp_preview_position(self, milliseconds):
        duration = max(1, self.preview_duration_ms, self.clip_timeline.duration)
        last_frame = max(0, duration - self.preview_frame_duration_ms())
        return max(0, min(last_frame, int(milliseconds)))

    def begin_preview_scrub(self):
        if self.preview_player is None:
            return
        self.preview_scrubbing = True
        self.preview_resume_after_seek = (
            self.preview_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        )
        self.preview_player.pause()

    def seek_preview(self, milliseconds):
        if self.preview_player is None:
            return
        target = self.clamp_preview_position(milliseconds)
        if target != self.preview_target_ms:
            self.preview_seek_retry_count = 0
        self.preview_target_ms = target
        self.preview_spinner.start()
        self.preview_spinner_guard.start(2500)
        self.clip_timeline.set_position(target)
        self.clip_time_label.setText(
            f"{seconds_text_ms(target / 1000)} / {seconds_text_ms(self.preview_duration_ms / 1000)}"
        )
        self.preview_seek_timer.start()

    def end_preview_scrub(self, milliseconds):
        if self.preview_player is None:
            return
        self.preview_scrubbing = False
        self.preview_target_ms = self.clamp_preview_position(milliseconds)
        self.preview_seek_timer.stop()
        self.commit_preview_seek()

    def commit_preview_seek(self):
        if self.preview_player is None:
            return
        if self.preview_waiting_cache:
            return
        self.preview_seek_inflight = True
        self.preview_player.setPosition(self.preview_target_ms)
        if self.preview_resume_after_seek and not self.preview_scrubbing:
            self.preview_resume_after_seek = False
            self.preview_player.play()

    def toggle_preview(self):
        if self.preview_player is None:
            return
        if self.preview_waiting_cache:
            self.preview_waiting_play = not self.preview_waiting_play
            self.set_play_button_state(self.preview_waiting_play)
            return
        if self.preview_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.preview_player.pause()
        else:
            self.preview_player.play()

    def set_preview_rate(self, rate):
        if self.preview_player is not None:
            self.preview_player.setPlaybackRate(float(rate))
        for button in (self.half_speed_btn, self.double_speed_btn):
            button.blockSignals(True)
        self.half_speed_btn.setChecked(abs(float(rate) - 0.5) < 0.01)
        self.double_speed_btn.setChecked(abs(float(rate) - 2.0) < 0.01)
        for button in (self.half_speed_btn, self.double_speed_btn):
            button.blockSignals(False)

    def toggle_preview_rate(self, rate, checked):
        self.set_preview_rate(rate if checked else 1.0)

    def preview_state_changed(self, state):
        self.set_play_button_state(state == QMediaPlayer.PlaybackState.PlayingState)

    def preview_media_status_changed(self, status):
        if status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia) and self.preview_restore_after_load:
            position, playing, rate = self.preview_restore_after_load
            self.preview_restore_after_load = None
            self.preview_player.setPlaybackRate(rate)
            self.preview_player.setPosition(position)
            if playing:
                self.preview_player.play()
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
        elif (
            status == QMediaPlayer.MediaStatus.EndOfMedia
            and self.preview_seek_inflight
            and self.preview_target_ms < self.preview_duration_ms - self.preview_frame_duration_ms() * 2
            and self.preview_seek_retry_count < 1
        ):
            self.preview_seek_retry_count += 1
            QTimer.singleShot(0, self.commit_preview_seek)

    def preview_frame_ready(self, frame):
        if frame.isValid():
            if not self.preview_seek_timer.isActive():
                self.preview_spinner_guard.stop()
                self.preview_spinner.stop()

    def step_preview_frame(self, direction):
        if self.preview_player is None:
            return
        self.preview_player.pause()
        self.preview_resume_after_seek = False
        self.preview_scrubbing = False
        frame_ms = self.preview_frame_duration_ms()
        if self.preview_seek_timer.isActive() or self.preview_seek_inflight:
            base = self.preview_target_ms
        else:
            base = self.preview_last_position_ms
        self.seek_preview(base + direction * frame_ms)

    def preview_position_changed(self, milliseconds):
        milliseconds = self.clamp_preview_position(milliseconds)
        tolerance = max(250, self.preview_frame_duration_ms() * 3)
        if self.preview_seek_inflight:
            if abs(milliseconds - self.preview_target_ms) > tolerance:
                return
            self.preview_seek_inflight = False
            self.preview_seek_retry_count = 0
        self.preview_last_position_ms = milliseconds
        if not self.preview_seek_timer.isActive():
            self.preview_target_ms = milliseconds
        self.clip_timeline.set_position(milliseconds)
        self.clip_time_label.setText(
            f"{seconds_text_ms(milliseconds / 1000)} / {seconds_text_ms(self.preview_duration_ms / 1000)}"
        )

    def preview_error(self, _error, message):
        self.preview_seek_timer.stop()
        self.preview_spinner_guard.stop()
        self.preview_seek_inflight = False
        self.preview_spinner.stop()
        if message:
            self.clip_time_label.setText(tr("preview_load_failed"))

    def preview_selection_position_seconds(self):
        if self.preview_seek_timer.isActive() or self.preview_seek_inflight:
            return self.preview_target_ms / 1000
        return self.preview_last_position_ms / 1000

    def set_clip_start(self):
        if self.preview_player is None:
            return
        current = self.preview_selection_position_seconds()
        if current >= self.clip_end:
            QMessageBox.warning(self, tr("boundary_invalid_title"), tr("start_boundary_message"))
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
        current = self.preview_selection_position_seconds()
        if current <= self.clip_start:
            QMessageBox.warning(self, tr("boundary_invalid_title"), tr("end_boundary_message"))
            return
        self.clip_end = current
        self.clip_applied = False
        self.restore_full_video_filename()
        self.clip_timeline.set_selection(self.clip_start * 1000, self.clip_end * 1000, False)
        value = f"{seconds_text_ms(self.clip_start)} – {seconds_text_ms(self.clip_end)}"
        self.range_label.setText(tr("pending_range", value=value))

    def cancel_clip_selection(self, reset_combo=True):
        self.preview_waiting_cache = False
        self.preview_restore_after_load = None
        if hasattr(self, "preview_seek_timer"):
            self.preview_seek_timer.stop()
        if hasattr(self, "preview_spinner_guard"):
            self.preview_spinner_guard.stop()
        if self.preview_player is not None:
            self.preview_player.stop()
        self.preview_seek_inflight = False
        self.preview_resume_after_seek = False
        self.preview_scrubbing = False
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
            QMessageBox.warning(self, tr("range_invalid_title"), tr("range_invalid_message"))
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
        dialog.setWindowTitle(tr("file_exists_title"))
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setText(tr("file_exists_message", value=target.name))
        overwrite_button = dialog.addButton(tr("overwrite"), QMessageBox.ButtonRole.AcceptRole)
        cancel_button = dialog.addButton(tr("cancel_download"), QMessageBox.ButtonRole.RejectRole)
        number_button = dialog.addButton(tr("add_number"), QMessageBox.ButtonRole.ActionRole)
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
            tr("disk_space_title"),
            tr("disk_space_message", required=human_size(required), free=human_size(free)),
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
        section = None
        if self.range_combo.currentIndex() == 1:
            if not self.clip_applied or self.clip_end <= self.clip_start:
                QMessageBox.warning(self, tr("range_not_applied_title"), tr("range_not_applied_message"))
                return
            section = (self.clip_start, self.clip_end)
        ext = audio_format.get("audio_ext") or audio_format.get("ext") or "m4a"
        name = clean_filename(self.filename_edit.text())
        initial = Path(self.settings.value("last_folder", str(Path.home())))
        path, _ = QFileDialog.getSaveFileName(
            self, tr("save_audio_dialog"), str(initial / f"{name}.{ext}"),
            f"{ext.upper()} (*.{ext});;{tr('all_files')} (*)", options=QFileDialog.Option.DontConfirmOverwrite,
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
        if self.batch_items:
            self.prepare_batch_download()
            return
        if not self.info or self.format_combo.currentIndex() < 0:
            return
        fmt, name = self.format_combo.currentData(), clean_filename(self.filename_edit.text())
        ext = fmt.get("merge_ext") or "mp4"
        initial = Path(self.settings.value("last_folder", str(Path.home())))
        path, _ = QFileDialog.getSaveFileName(
            self, tr("save_video_dialog"), str(initial / f"{name}.{ext}"),
            f"{ext.upper()} (*.{ext});;{tr('all_files')} (*)", options=QFileDialog.Option.DontConfirmOverwrite,
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
                QMessageBox.warning(self, tr("range_not_applied_title"), tr("range_not_applied_message"))
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

    def prepare_batch_download(self):
        folder = QFileDialog.getExistingDirectory(self, tr("save_video_dialog"),
            str(self.settings.value("last_folder", str(Path.home()))))
        if not folder:
            return
        self.settings.setValue("last_folder", folder)
        pending_items, reserved = [], {str(Path(manager.output_path).resolve()).casefold()
                                     for manager, _ in self.tasks if manager.state in ("running", "waiting", "paused", "retrying")}
        for record in self.batch_items:
            fmt = record["format"]
            target = Path(folder) / f"{clean_filename(record['info'].get('title'))}.{fmt['merge_ext']}"
            original, index = target, 0
            while str(target.resolve()).casefold() in reserved:
                index += 1
                target = original.with_name(f"{original.stem}（{index}）{original.suffix}")
            resolved = self.resolve_existing_file(target)
            if not resolved:
                continue
            path, overwrite = resolved
            reserved.add(str(Path(path).resolve()).casefold())
            pending_items.append({**record, "path": path, "overwrite": overwrite,
                                  "cover": self.cover_check.isChecked()})
        required = sum(item["format"].get("estimated_bytes") or 0 for item in pending_items)
        if not pending_items or not self.ensure_disk_space(pending_items[0]["path"], required):
            return
        for pending in pending_items:
            self.create_task(None, pending, schedule=False)
        self.schedule_tasks()

    def create_task(self, section, pending=None, schedule=True):
        if pending is None:
            pending, self.pending_download = self.pending_download, None
        if not pending:
            return
        fmt = pending["format"]
        manager = DownloadManager(
            pending.get("url", self.url_edit.text().strip()), fmt["selector"], pending["path"],
            fmt.get("merge_ext"), pending["cover"], section=section,
            overwrite=pending.get("overwrite", False),
            progress_components=fmt.get("progress_components"), parent=self,
        )
        card = DownloadTaskWidget(manager, pending.get("thumbnail", self.thumbnail_bytes))
        card.set_scale(self.ui_scale or 1.0)
        card.removed.connect(self.remove_task)
        manager.queue_requested.connect(self.schedule_tasks)
        title = pending.get("info", self.info or {}).get("title", "")
        manager.finished.connect(lambda success, m=manager, t=title: self.record_completed_download(m, t) if success else None)
        manager.transient_failure.connect(self.handle_transient_failure)
        manager.format_unavailable.connect(self.format_became_unavailable)
        manager.state_changed.connect(lambda _state, _detail: QTimer.singleShot(0, self.schedule_tasks))
        self.tasks.append((manager, card))
        self.task_layout.insertWidget(0, card)
        self.update_task_count()
        if schedule:
            self.schedule_tasks()
        return manager

    def remove_task(self, card):
        for index, (manager, widget) in enumerate(list(self.tasks)):
            if widget is card:
                self.tasks.pop(index)
                widget.deleteLater()
                manager.deleteLater()
                break
        self.update_task_count()
        self.schedule_tasks()

    def update_task_count(self):
        self.task_count.setText(f"{min(len(self.tasks), MAX_TASKS)}/{MAX_TASKS}")
        self.task_count.setToolTip(f"{len(self.tasks)} · {sum(m.state == 'waiting' for m, _ in self.tasks)} {tr('waiting')}")
        for index, (_manager, card) in enumerate(self.tasks):
            card.setVisible(index >= len(self.tasks) - MAX_TASKS)

    def closeEvent(self, event):
        if self.batch_worker is not None:
            self.batch_worker.cancelled.set()
            event.ignore()
            QTimer.singleShot(200, self.close)
            return
        if self.library_worker is not None:
            self.library_worker.scanner.cancelled.set()
            event.ignore()
            QTimer.singleShot(200, self.close)
            return
        if (
            (self.engine_check_worker is not None and self.engine_check_worker.isRunning())
            or (self.engine_update_worker is not None and self.engine_update_worker.isRunning())
        ):
            QMessageBox.warning(self, tr("update_failed_title"), tr("update_in_progress_message"))
            event.ignore()
            return
        active = [manager for manager, _ in self.tasks if manager.state == "running"]
        if active:
            answer = QMessageBox.question(self, tr("exit_title"), tr("exit_message"),
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            for manager in active:
                manager.pause()
        self.stop_preview_cache()
        self.results_popup.hide()
        if self.retired_preview_workers:
            event.ignore()
            QTimer.singleShot(200, self.close)
            return
        if self.search_worker is not None:
            self.search_worker.cancel()
            event.ignore()
            QTimer.singleShot(200, self.close)
            return
        if self.info_worker is not None and self.info_worker.isRunning():
            event.ignore()
            QTimer.singleShot(500, self.close)
            return
        for reply in list(self.thumbnail_replies.values()):
            reply.abort()
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
        QMessageBox.critical(None, tr("startup_failed_title"), tr("startup_failed_message", value=details[-1200:]))
        sys.exit(1)
    window.show()
    sys.exit(app.exec())
