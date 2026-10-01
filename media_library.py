"""Read-only media inspection and advisory source-identity matching."""
import json
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Event

MEDIA_EXTENSIONS = {".mp4", ".webm", ".mkv", ".mov", ".avi", ".m4v", ".ts"}
SOURCE_PATTERN = re.compile(r"(?:youtu\.be/|youtube\.com/(?:watch\?(?:[^\s]*?&)?v=|shorts/|live/))([A-Za-z0-9_-]{11})(?![A-Za-z0-9_-])")


def source_ids(value):
    return set(SOURCE_PATTERN.findall(str(value)))


def read_json(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def save_json(path, data):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)


def fingerprint(path):
    stat = Path(path).stat()
    return [stat.st_size, stat.st_mtime_ns]


def media_record(path, probe, signature, provenance=None):
    fmt = probe.get("format", {})
    streams = probe.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"
                  and not s.get("disposition", {}).get("attached_pic")), None)
    if not video:
        return None
    tags = {str(k).lower(): str(v) for obj in [fmt, *streams] for k, v in obj.get("tags", {}).items()}
    # Video descriptions often link to OTHER videos; they are not provenance.
    explicit_sources = [tags.get(key, "") for key in ("purl", "source_url", "webpage_url", "url", "website")]
    comment = tags.get("comment", "")
    explicit_sources += re.findall(r"(?im)^(?:Video URL|Source URL|URL):\s*(\S+)", comment)
    if re.fullmatch(r"https?://\S+", comment.strip()):
        explicit_sources.append(comment.strip())
    ids = source_ids("\n".join(explicit_sources))
    title = tags.get("title", "")
    if not title:
        match = re.search(r"(?m)^Video:\s*(.+)$", tags.get("comment", ""))
        title = match.group(1).strip() if match else ""
    if provenance and provenance.get("signature") == signature:
        ids.update(source_ids(provenance.get("url", "")))
        title = title or provenance.get("title", "")
    try:
        numerator, denominator = str(video.get("avg_frame_rate", "0/1")).split("/")
        fps = float(numerator) / float(denominator)
    except (ValueError, ZeroDivisionError):
        fps = 0
    return {"path": str(path), "signature": signature, "source_ids": sorted(ids), "title": title,
            "duration": float(fmt.get("duration") or video.get("duration") or 0),
            "width": video.get("width", 0), "height": video.get("height", 0), "fps": fps,
            "codec": video.get("codec_name", "?"), "size": signature[0],
            "section": provenance.get("section") if provenance and provenance.get("signature") == signature else None}


def duplicate_matches(records, info):
    target = str(info.get("id") or "")
    duration = float(info.get("duration") or 0)
    title = str(info.get("title") or "").strip().casefold()
    matches = []
    for record in records:
        same_id = bool(target and target in record.get("source_ids", []))
        # Never infer identity solely from filename, resolution or duration.
        probable = (not record.get("source_ids") and bool(title)
                    and title == record.get("title", "").strip().casefold()
                    and duration > 0 and abs(record["duration"] - duration) <= max(1, duration * .005))
        if same_id or probable:
            try:
                if fingerprint(record["path"]) != record["signature"]:
                    continue
            except OSError:
                continue
            matches.append({**record, "confirmed_source": same_id,
                            "partial": bool(record.get("section")) or (duration > 0 and record["duration"] < duration - max(2, duration * .02))})
    return matches


class LibraryScanner:
    def __init__(self, root, ffprobe, cache_path, source_path):
        self.root, self.ffprobe = Path(root), str(ffprobe)
        self.cache_path, self.source_path = Path(cache_path), Path(source_path)
        self.cancelled = Event()
        self.failed_count = 0

    def probe(self, path, signature, provenance):
        if self.cancelled.is_set():
            return None
        try:
            command = [self.ffprobe, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)]
            with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0) as process:
                elapsed = 0
                while True:
                    if self.cancelled.is_set() or elapsed >= 15:
                        process.kill()
                        process.communicate()
                        return None
                    try:
                        output, _ = process.communicate(timeout=.25)
                        break
                    except subprocess.TimeoutExpired:
                        elapsed += .25
                if process.returncode:
                    self.failed_count += 1
                    return None
            return media_record(path, json.loads(output), signature, provenance)
        except (OSError, ValueError, TypeError):
            self.failed_count += 1
            return None

    def scan(self):
        saved, sources = read_json(self.cache_path), read_json(self.source_path)
        cache = saved.get("records", {}) if saved.get("version") == 2 else {}
        records, jobs = {}, []
        with ThreadPoolExecutor(max_workers=2) as pool:
            for directory, _, files in os.walk(self.root, followlinks=False):
                if self.cancelled.is_set():
                    break
                for name in files:
                    path = Path(directory) / name
                    if path.suffix.lower() not in MEDIA_EXTENSIONS or path.is_symlink():
                        continue
                    key = str(path.resolve())
                    try:
                        signature = fingerprint(path)
                    except OSError:
                        continue
                    old = cache.get(key, {})
                    if old.get("signature") == signature and old.get("provenance") == sources.get(key):
                        records[key] = old
                    else:
                        jobs.append((key, sources.get(key), pool.submit(self.probe, path, signature, sources.get(key))))
            future_keys = {job: (key, source) for key, source, job in jobs}
            for job in as_completed(future_keys):
                if self.cancelled.is_set():
                    for other in future_keys:
                        other.cancel()
                    break
                record = job.result()
                if record:
                    key, source = future_keys[job]
                    records[key] = {**record, "provenance": source}
        if not self.cancelled.is_set():
            save_json(self.cache_path, {"version": 2, "records": records})
        return list(records.values())


def remember_download(source_path, path, url, title, section):
    path = Path(path)
    if not path.is_file() or path.suffix.lower() not in MEDIA_EXTENSIONS:
        return
    records = read_json(source_path)
    records[str(path.resolve())] = {"signature": fingerprint(path), "url": url, "title": title, "section": section}
    save_json(source_path, records)
