
import datetime
import os
import re
from dataclasses import dataclass, field

from . import vdf

__all__ = [
    "SteamUser",
    "ClipSegment",
    "RecordingClip",
    "find_steam_installations",
    "is_valid_steam_path",
    "scan_users",
    "find_game_recordings_path",
    "find_clips",
    "load_game_names",
    "steam_id64_to_id3",
]

CLIP_NAME_RE = re.compile(r"clip_(\d+)_(\d{8})_(\d{6})")
BG_FG_NAME_RE = re.compile(r"^(bg|fg)_(\d+)_(\d{8})_(\d{6})(?:_\d+)?$")


@dataclass
class SteamUser:
    id3: str
    id64: str = ""
    persona_name: str = ""
    account_name: str = ""
    recordings_path: str = ""
    has_recordings: bool = False

    def display_name(self) -> str:
        return self.persona_name or self.account_name or f"用户 {self.id3}"


@dataclass
class ClipSegment:

    label: str
    kind: str
    mpd_path: str
    session_dir: str
    size_bytes: int = 0


@dataclass
class RecordingClip:

    path: str
    name: str
    app_id: str
    date: str
    time: str
    thumbnail: str = ""
    segments: list = field(default_factory=list)

    @property
    def start_time(self) -> datetime.datetime:
        try:
            return datetime.datetime.strptime(
                self.date + self.time, "%Y%m%d%H%M%S"
            )
        except ValueError:
            return datetime.datetime.min

    @property
    def total_size(self) -> int:
        return sum(seg.size_bytes for seg in self.segments)

    @property
    def game_name(self) -> str:
        return ""


def _linux_candidates():
    home = os.path.expanduser("~")
    candidates = [
        os.path.join(home, ".steam", "steam"),
        os.path.join(home, ".local", "share", "Steam"),
        os.path.join(home, ".var", "app", "com.valvesoftware.Steam", ".steam", "steam"),
        os.path.join(home, ".var", "app", "com.valvesoftware.Steam", "data", "Steam"),
        "/var/lib/flatpak/app/com.valvesoftware.Steam/current/active/export/share",
    ]
    return candidates


def _windows_candidates():
    candidates = [r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam"]
    reg_keys = [
        r"SOFTWARE\Valve\Steam",
        r"SOFTWARE\WOW6432Node\Valve\Steam",
    ]
    for hive in ("HKLM", "HKCU"):
        for key in reg_keys:
            value = _read_windows_registry(hive, key, "SteamPath")
            if value:
                candidates.append(value)
    return candidates


def _read_windows_registry(hive, key, name):
    try:
        import winreg  # type: ignore

        access = winreg.KEY_READ
        handle = winreg.OpenKey(
            getattr(winreg, "HKEY_LOCAL_MACHINE" if hive == "HKLM" else "HKEY_CURRENT_USER"),
            key,
            0,
            access,
        )
        value, _ = winreg.QueryValueEx(handle, name)
        winreg.CloseKey(handle)
        return value
    except Exception:
        return None


def find_steam_installations():
    if os.name == "nt":
        candidates = _windows_candidates()
    else:
        candidates = _linux_candidates()

    found = []
    seen = set()
    for path in candidates:
        path = os.path.normpath(path)
        if path in seen:
            continue
        seen.add(path)
        if is_valid_steam_path(path):
            found.append(path)
    return found


def is_valid_steam_path(path: str) -> bool:
    if not path or not os.path.isdir(path):
        return False
    return os.path.isdir(os.path.join(path, "userdata")) and os.path.isdir(
        os.path.join(path, "steamapps")
    )


def steam_id64_to_id3(steam_id64: str) -> str:
    try:
        value = int(steam_id64)
        return str(value - 76561197960265728)
    except (TypeError, ValueError):
        return ""


def _parse_steam_id64(steam_path: str) -> str:
    config_path = os.path.join(steam_path, "config", "config.vdf")
    if not os.path.isfile(config_path):
        return ""
    try:
        root = vdf.load(config_path)
        accounts = (
            root.get("InstallConfigStore", {})
            .get("Software", {})
            .get("Valve", {})
            .get("Steam", {})
            .get("Accounts", {})
        )
    except Exception:
        return ""
    if not accounts:
        return ""
    first = next(iter(accounts.items()), (None, None))
    if not first[0]:
        return ""
    account = first[1]
    if isinstance(account, dict):
        return str(account.get("SteamID", ""))
    return str(first[0])


def _recordings_exist(recordings_path: str) -> bool:
    for sub in ("video", "clips"):
        path = os.path.join(recordings_path, sub)
        if os.path.isdir(path):
            try:
                if os.listdir(path):
                    return True
            except OSError:
                pass
    return False


def scan_users(steam_path: str):
    users = []
    userdata = os.path.join(steam_path, "userdata")
    if not os.path.isdir(userdata):
        return users

    id64 = _parse_steam_id64(steam_path)
    for entry in sorted(os.listdir(userdata)):
        user_dir = os.path.join(userdata, entry)
        if not os.path.isdir(user_dir) or not entry.isdigit():
            continue

        user = SteamUser(id3=entry)
        if id64 and steam_id64_to_id3(id64) == entry:
            user.id64 = id64

        local_config = os.path.join(user_dir, "config", "localconfig.vdf")
        if os.path.isfile(local_config):
            try:
                root = vdf.load(local_config)
                friends = root.get("friends")
                if isinstance(friends, dict):
                    user.persona_name = str(friends.get("PersonaName", ""))
                store = root.get("UserLocalConfigStore")
                if isinstance(store, dict):
                    user.account_name = str(store.get("AccountName", ""))
                    game_rec = store.get("GameRecording")
                    if isinstance(game_rec, dict):
                        custom = str(game_rec.get("BackgroundRecordPath", ""))
                        if custom and os.path.isdir(custom):
                            user.recordings_path = custom
            except Exception:
                pass

        if not user.recordings_path:
            default = os.path.join(user_dir, "gamerecordings")
            user.recordings_path = default if os.path.isdir(default) else default

        user.has_recordings = _recordings_exist(user.recordings_path)

        users.append(user)
    return users


def find_game_recordings_path(user: SteamUser) -> str:
    return user.recordings_path


def _segment_kind(label: str) -> str:
    if label.startswith("fg_"):
        return "fg"
    return "bg"


def _dir_size(path: str) -> int:
    total = 0
    try:
        for root, _dirs, files in os.walk(path):
            for name in files:
                try:
                    total += os.path.getsize(os.path.join(root, name))
                except OSError:
                    pass
    except OSError:
        pass
    return total


def _scan_segments(clip_dir: str):
    segments = []
    video_dir = os.path.join(clip_dir, "video")
    if not os.path.isdir(video_dir):
        return segments
    try:
        entries = sorted(os.listdir(video_dir))
    except OSError:
        return segments
    for entry in entries:
        if not (entry.startswith("fg_") or entry.startswith("bg_")):
            continue
        session_dir = os.path.join(video_dir, entry)
        mpd_path = os.path.join(session_dir, "session.mpd")
        if os.path.isfile(mpd_path):
            segments.append(
                ClipSegment(
                    label=entry,
                    kind=_segment_kind(entry),
                    mpd_path=mpd_path,
                    session_dir=session_dir,
                    size_bytes=_dir_size(session_dir),
                )
            )
    return segments


def _scan_clip_dir(clip_dir: str) -> RecordingClip:
    name = os.path.basename(clip_dir)
    match = CLIP_NAME_RE.match(name)
    if not match:
        return None
    app_id, date, time_ = match.groups()
    thumbnail = os.path.join(clip_dir, "thumbnail.jpg")
    return RecordingClip(
        path=clip_dir,
        name=name,
        app_id=app_id,
        date=date,
        time=time_,
        thumbnail=thumbnail if os.path.isfile(thumbnail) else "",
        segments=_scan_segments(clip_dir),
    )


def _scan_background_recordings(recordings_path: str):
    recordings = []
    video_dir = os.path.join(recordings_path, "video")
    if not os.path.isdir(video_dir):
        return recordings
    try:
        entries = sorted(os.listdir(video_dir))
    except OSError:
        return recordings
    for entry in entries:
        match = BG_FG_NAME_RE.match(entry)
        if not match:
            continue
        session_dir = os.path.join(video_dir, entry)
        if not os.path.isdir(session_dir):
            continue
        mpd_path = os.path.join(session_dir, "session.mpd")
        if not os.path.isfile(mpd_path):
            continue
        kind, app_id, date, time_ = match.groups()
        segment = ClipSegment(
            label=entry,
            kind=kind,
            mpd_path=mpd_path,
            session_dir=session_dir,
            size_bytes=_dir_size(session_dir),
        )
        recordings.append(
            RecordingClip(
                path=session_dir,
                name=entry,
                app_id=app_id,
                date=date,
                time=time_,
                segments=[segment],
            )
        )
    return recordings


def find_clips(recordings_path: str):
    clips = []
    clips_dir = os.path.join(recordings_path, "clips")
    if not os.path.isdir(clips_dir):
        clips = _scan_background_recordings(recordings_path)
        clips.sort(key=lambda c: (c.date, c.time), reverse=True)
        return clips

    try:
        entries = os.listdir(clips_dir)
    except OSError:
        entries = []

    for entry in entries:
        if not entry.startswith("clip_"):
            continue
        clip_dir = os.path.join(clips_dir, entry)
        if not os.path.isdir(clip_dir):
            continue
        clip = _scan_clip_dir(clip_dir)
        if clip:
            clips.append(clip)

    clips.extend(_scan_background_recordings(recordings_path))
    clips.sort(key=lambda c: (c.date, c.time), reverse=True)
    return clips


def _steam_library_paths(steam_path: str):
    paths = [os.path.join(steam_path, "steamapps")]
    library_file = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
    if os.path.isfile(library_file):
        try:
            root = vdf.load(library_file)
        except Exception:
            root = {}
        folders = root.get("libraryfolders", {})
        if isinstance(folders, dict):
            for entry in folders.values():
                if isinstance(entry, dict):
                    path = str(entry.get("path", ""))
                    if path:
                        paths.append(os.path.join(path, "steamapps"))
    return paths


def load_game_names(steam_path: str):
    names = {}
    for steamapps in _steam_library_paths(steam_path):
        if not os.path.isdir(steamapps):
            continue
        try:
            entries = os.listdir(steamapps)
        except OSError:
            continue
        for entry in entries:
            match = re.match(r"appmanifest_(\d+)\.acf$", entry)
            if not match or match.group(1) in names:
                continue
            try:
                manifest = vdf.load(os.path.join(steamapps, entry))
            except Exception:
                continue
            name = manifest.get("AppState", {}).get("name")
            if name:
                names[match.group(1)] = str(name)
    return names
