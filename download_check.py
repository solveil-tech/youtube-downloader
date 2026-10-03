"""Read-only post-download checks. Warnings are evidence, not automatic deletion."""
import json
import math
import subprocess
from pathlib import Path


def positive_number(value):
    try:
        number = float(value)
        return number if math.isfinite(number) and number > 0 else 0.0
    except (ValueError, TypeError):
        return 0.0


def check_metadata(data, expected_duration=0, video_required=True, audio_required=True, clip=False):
    issues = []
    streams = data.get('streams', [])
    video = [s for s in streams if s.get('codec_type') == 'video' and not s.get('disposition', {}).get('attached_pic')]
    audio = [s for s in streams if s.get('codec_type') == 'audio']
    if video_required and not video:
        issues.append(('missing_video', ''))
    if audio_required and not audio:
        issues.append(('missing_audio', ''))
    duration = positive_number(data.get('format', {}).get('duration'))
    if not duration:
        issues.append(('unknown_duration', ''))
    expected = positive_number(expected_duration)
    tolerance = max(3.0, min(15.0, expected * 0.02)) if clip else max(2.0, expected * 0.01)
    if duration and expected and abs(duration - expected) > tolerance:
        issues.append(('duration_mismatch', f'{duration:.3f}s / {expected:.3f}s'))
    durations = [positive_number(s.get('duration')) for s in video[:1] + audio[:1]]
    if len(durations) == 2 and all(durations) and abs(durations[0] - durations[1]) > max(2, duration * 0.01):
        issues.append(('av_mismatch', f'{durations[0]:.3f}s / {durations[1]:.3f}s'))
    return issues, duration


def check_audio_packets(output, media_duration, origin=0):
    """Packets, not silence: legitimate silent audio still contains packets."""
    first, last, previous_end, largest_gap = None, None, None, 0.0
    for line in output.splitlines():
        fields = line.split(',')
        if len(fields) < 2:
            continue
        try:
            start, length = float(fields[0]) - origin, float(fields[1])
        except ValueError:
            continue
        if not math.isfinite(start) or not math.isfinite(length):
            continue
        first = start if first is None else min(first, start)
        if previous_end is not None:
            largest_gap = max(largest_gap, start - previous_end)
        previous_end = max(previous_end or start, start + max(0, length))
        last = max(last or start, start + max(0, length))
    if first is None:
        return [('audio_packets_unknown', '')]
    issues = []
    if largest_gap > 1.0:
        issues.append(('audio_gap', f'{largest_gap:.3f}s'))
    if media_duration and (first > 2 or media_duration - last > max(2, media_duration * 0.01)):
        issues.append(('audio_coverage', f'{first:.3f}s → {last:.3f}s / {media_duration:.3f}s'))
    return issues


def inspect_download(path, ffprobe, ffmpeg=None, expected_duration=0,
                     video_required=True, audio_required=True, clip=False, cancelled=lambda: False):
    path = Path(path)
    if not path.is_file() or path.stat().st_size == 0:
        return [('missing_file', '')]
    flags = subprocess.CREATE_NO_WINDOW if __import__('os').name == 'nt' else 0

    def run(command, timeout):
        if cancelled():
            raise InterruptedError()
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, encoding='utf-8', errors='replace', creationflags=flags)
        import time
        start = time.monotonic()
        try:
            while True:
                if cancelled():
                    raise InterruptedError()
                if time.monotonic() - start > timeout:
                    raise TimeoutError('Inspection timed out')
                try:
                    stdout, stderr = process.communicate(timeout=0.2)
                    if process.returncode:
                        raise ValueError(stderr[-600:])
                    return stdout
                except subprocess.TimeoutExpired:
                    pass
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()

    try:
        metadata = json.loads(run([str(ffprobe), '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)], 30))
        issues, duration = check_metadata(metadata, expected_duration, video_required, audio_required, clip)
        if any(s.get('codec_type') == 'audio' for s in metadata.get('streams', [])):
            packets = run([str(ffprobe), '-v', 'error', '-select_streams', 'a:0', '-show_entries',
                           'packet=pts_time,duration_time', '-of', 'csv=p=0', str(path)], 120)
            try:
                origin = float(metadata.get('format', {}).get('start_time') or 0)
            except (TypeError, ValueError):
                origin = 0
            issues += check_audio_packets(packets, duration, origin)
        # Decode short samples only. A full decode would cost roughly playback
        # duration and is not appropriate for automatic completion checking.
        if ffmpeg and duration:
            for position in sorted({0.0, max(0.0, duration / 2 - 0.5), max(0.0, duration - 1)}):
                try:
                    run([str(ffmpeg), '-v', 'error', '-xerror', '-ss', str(position), '-i', str(path),
                         '-t', '1', '-map', '0:v:0?', '-map', '0:a:0?', '-f', 'null', '-'], 30)
                except (ValueError, TimeoutError) as exc:
                    issues.append(('decode_error', f'{position:.3f}s: {exc}'))
                    break
        elif not ffmpeg:
            issues.append(('inspection_unavailable', 'FFmpeg unavailable'))
        return issues
    except InterruptedError:
        raise
    except (ValueError, OSError, TimeoutError) as exc:
        return [('inspection_unavailable', str(exc))]
