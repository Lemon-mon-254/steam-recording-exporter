
import os
import re
import shutil
import subprocess
import sys
import threading

__all__ = [
    "FfmpegError",
    "find_ffmpeg",
    "find_ffprobe",
    "fix_mpd",
    "mpd_start_offset",
    "probe_duration",
    "export_segment",
    "export_supported",
]

_STREAM_ORDER = ("video", "audio", "data", "subtitle")


class FfmpegError(RuntimeError):
    pass


def _bundled_dir() -> str:
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, "ffmpeg")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vendor")


def _find_binary(names, env_names=()):
    for env_name in env_names:
        value = os.environ.get(env_name)
        if value:
            return value
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    bundled = _bundled_dir()
    for name in names:
        candidate = os.path.join(bundled, name)
        if os.name == "nt":
            candidate = os.path.join(bundled, name + ".exe")
        if os.path.isfile(candidate):
            return candidate
    return None


def find_ffmpeg():
    return _find_binary(["ffmpeg"], ("FFMPEG_PATH",))


def find_ffprobe():
    return _find_binary(["ffprobe"], ("FFPROBE_PATH",))


def export_supported() -> bool:
    return find_ffmpeg() is not None


_PERIOD_START_RE = re.compile(r'(<Period\b[^>]*\bstart=")[^"]*(")')
_PERIOD_START_VALUE_RE = re.compile(r'<Period\b[^>]*\bstart="PT(?:(\d+)H)?(?:(\d+)M)?([0-9.]+)S"')


def fix_mpd(mpd_path: str, output_path: str) -> str:
    with open(mpd_path, "rb") as handle:
        data = handle.read()

    text = data.decode("utf-8", errors="replace")
    text = text.replace("\x00", "")
    text = _PERIOD_START_RE.sub(r"\1PT0S\2", text)

    session_dir = os.path.dirname(mpd_path).replace("\\", "/")
    text = re.sub(r'initialization="([^"]*)"', r'initialization="%s/\1"' % _xml_escape(session_dir), text)
    text = re.sub(r'media="([^"]*)"', r'media="%s/\1"' % _xml_escape(session_dir), text)

    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return output_path


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def mpd_start_offset(mpd_path: str) -> float:
    try:
        with open(mpd_path, "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read()
        match = _PERIOD_START_VALUE_RE.search(text)
        if match:
            hours, minutes, seconds = match.groups()
            total = float(seconds or 0)
            if minutes:
                total += int(minutes) * 60
            if hours:
                total += int(hours) * 3600
            return total
    except Exception:
        pass
    return 0.0


def probe_duration(media_path: str) -> float:
    ffprobe = find_ffprobe()
    if not ffprobe:
        return 0.0
    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        media_path,
    ]
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=60,
            creationflags=_creation_flags(),
        )
        value = proc.stdout.strip().splitlines()
        if not value:
            return 0.0
        return float(value[0])
    except Exception:
        return 0.0


def _creation_flags():
    if os.name == "nt":
        return subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    return 0


def _parse_progress_line(line: str):
    if "=" not in line:
        return None
    key, _, value = line.partition("=")
    return key.strip(), value.strip()


def export_segment(
    mpd_path: str,
    output_path: str,
    on_progress=None,
    cancel_event: threading.Event = None,
    start_offset: float = 0.0,
) -> None:
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise FfmpegError("未找到 FFmpeg 可执行文件。请安装 ffmpeg 或随程序打包。")

    out_dir = os.path.dirname(output_path)
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    command = [
        ffmpeg,
        "-hide_banner",
        "-y",
        "-i",
        mpd_path,
        "-c",
        "copy",
        "-avoid_negative_ts",
        "make_zero",
        "-fflags",
        "+genpts",
        "-movflags",
        "+faststart",
        "-progress",
        "pipe:1",
        "-nostats",
    ]
    if start_offset > 0:
        command += ["-output_ts_offset", f"-{start_offset:.6f}"]
    command.append(output_path)

    if cancel_event is not None and cancel_event.is_set():
        raise FfmpegError("导出已取消。")

    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=_creation_flags(),
    )

    last_time = 0.0
    errors = []

    def read_stream(stream, on_line):
        try:
            for raw in iter(stream.readline, b""):
                if on_line:
                    on_line(raw.decode("utf-8", errors="replace"))
        except Exception:
            pass

    def handle_stdout(raw):
        nonlocal last_time
        for line in raw.splitlines():
            parsed = _parse_progress_line(line)
            if not parsed:
                continue
            key, value = parsed
            if key in ("out_time_us", "out_time_ms") and value != "N/A":
                try:
                    if key == "out_time_us":
                        last_time = int(value) / 1_000_000
                    else:
                        last_time = int(value) / 1_000
                except ValueError:
                    pass
                if on_progress:
                    on_progress(last_time)

    def handle_stderr(raw):
        for line in raw.splitlines():
            lowered = line.lower()
            if "error" in lowered or "invalid" in lowered or "failed" in lowered:
                errors.append(line.strip())

    stdout_thread = threading.Thread(target=read_stream, args=(proc.stdout, handle_stdout), daemon=True)
    stderr_thread = threading.Thread(target=read_stream, args=(proc.stderr, handle_stderr), daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    exit_code = None
    while exit_code is None:
        if cancel_event is not None and cancel_event.is_set():
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            raise FfmpegError("用户取消了导出。")
        try:
            exit_code = proc.wait(timeout=0.2)
        except subprocess.TimeoutExpired:
            continue

    stdout_thread.join(timeout=1)
    stderr_thread.join(timeout=1)

    if exit_code != 0 or not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
        detail = "\n".join(errors[-12:]) if errors else f"ffmpeg 以退出码 {exit_code} 结束"
        raise FfmpegError(f"导出失败：{detail}")

    if on_progress:
        on_progress(last_time or 0.0)
