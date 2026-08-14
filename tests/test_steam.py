import os

from exporter import steam

CLIP_DIR_NAMES = [
    "clip_250900_20251129_034618",
    "clip_250900_20250705_122712",
    "clip_250900_20241121_132258",
]


def _write(steam_root, *parts, content=""):
    path = os.path.join(steam_root, *parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


def _make_clip(clips_dir, name):
    clip_dir = os.path.join(clips_dir, name)
    video_dir = os.path.join(clip_dir, "video", "bg_" + name[5:])
    os.makedirs(video_dir)
    for fname in ("init-stream0.m4s", "init-stream1.m4s", "chunk-stream0-00001.m4s"):
        with open(os.path.join(video_dir, fname), "wb") as handle:
            handle.write(b"\x00" * 1024)
    with open(os.path.join(video_dir, "session.mpd"), "w", encoding="utf-8") as handle:
        handle.write("<MPD/>")
    with open(os.path.join(clip_dir, "thumbnail.jpg"), "wb") as handle:
        handle.write(b"jpg")


def _make_steam_tree(tmp_path, custom_recordings=None):
    steam_root = str(tmp_path / "steam")
    id64 = "76561198000000000"
    id3 = steam.steam_id64_to_id3(id64)
    user_dir = os.path.join(steam_root, "userdata", id3)
    os.makedirs(user_dir)

    _write(
        steam_root,
        "config",
        "config.vdf",
        content="""
"InstallConfigStore"
{
    "Software"
    {
        "Valve"
        {
            "Steam"
            {
                "Accounts"
                {
                    "76561198000000000"
                    {
                        "SteamID"        "76561198000000000"
                    }
                }
            }
        }
    }
}
""",
    )

    local_lines = ['"UserLocalConfigStore"', "{", '    "AccountName"        "tester"']
    if custom_recordings:
        local_lines += [
            '    "GameRecording"',
            "    {",
            f'        "BackgroundRecordPath"        "{custom_recordings}"',
            "    }",
        ]
    local_lines += ["}", '"friends"', "{", '    "PersonaName"        "TesterUser"', "}"]
    _write(
        steam_root,
        "userdata",
        id3,
        "config",
        "localconfig.vdf",
        content="\n".join(local_lines),
    )

    _write(
        steam_root,
        "steamapps",
        "appmanifest_250900.acf",
        content='\n"AppState"\n{\n\t"appid"\t\t"250900"\n\t"name"\t\t"Test Game"\n}\n',
    )
    return steam_root, id3


def test_is_valid_steam_path(tmp_path):
    steam_root, _ = _make_steam_tree(tmp_path)
    assert steam.is_valid_steam_path(steam_root)
    assert not steam.is_valid_steam_path(str(tmp_path / "nope"))


def test_scan_users_default_recordings_path(tmp_path):
    steam_root, id3 = _make_steam_tree(tmp_path)
    users = steam.scan_users(steam_root)
    assert len(users) == 1
    user = users[0]
    assert user.id3 == id3
    assert user.id64 == "76561198000000000"
    assert user.persona_name == "TesterUser"
    assert user.account_name == "tester"
    assert user.recordings_path == os.path.join(steam_root, "userdata", id3, "gamerecordings")


def test_scan_users_custom_recordings_path(tmp_path):
    custom = str(tmp_path / "custom-clips")
    os.makedirs(custom)
    steam_root, _ = _make_steam_tree(tmp_path, custom_recordings=custom)
    users = steam.scan_users(steam_root)
    assert users[0].recordings_path == custom
    assert users[0].has_recordings is False
    bg = os.path.join(custom, "video", "bg_250900_20250601_120000")
    os.makedirs(bg)
    with open(os.path.join(bg, "session.mpd"), "w", encoding="utf-8") as handle:
        handle.write("<MPD/>")
    users = steam.scan_users(steam_root)
    assert users[0].has_recordings is True


def test_find_clips_sorts_newest_first(tmp_path):
    custom = str(tmp_path / "custom-clips")
    clips_dir = os.path.join(custom, "clips")
    steam_root, _ = _make_steam_tree(tmp_path, custom_recordings=custom)
    for name in CLIP_DIR_NAMES:
        _make_clip(clips_dir, name)
    clips = steam.find_clips(custom)
    assert [c.name for c in clips] == sorted(CLIP_DIR_NAMES, reverse=True)
    newest = clips[0]
    assert newest.app_id == "250900"
    assert newest.segments[0].kind == "bg"
    assert newest.segments[0].mpd_path.endswith("session.mpd")
    assert newest.total_size > 0


def test_load_game_names(tmp_path):
    steam_root, _ = _make_steam_tree(tmp_path)
    assert steam.load_game_names(steam_root) == {"250900": "Test Game"}


def test_find_clips_background_recordings_when_no_clips_dir(tmp_path):
    custom = str(tmp_path / "custom-clips")
    steam_root, _ = _make_steam_tree(tmp_path, custom_recordings=custom)
    bg_dir = os.path.join(custom, "video", "bg_250900_20251129_034618")
    os.makedirs(bg_dir)
    with open(os.path.join(bg_dir, "session.mpd"), "w", encoding="utf-8") as handle:
        handle.write("<MPD/>")
    with open(os.path.join(bg_dir, "chunk-stream0-00001.m4s"), "wb") as handle:
        handle.write(b"\x00" * 1024)
    clips = steam.find_clips(custom)
    assert len(clips) == 1
    clip = clips[0]
    assert clip.name == "bg_250900_20251129_034618"
    assert clip.app_id == "250900"
    assert len(clip.segments) == 1
    assert clip.segments[0].kind == "bg"
    assert clip.total_size > 0


def test_find_clips_merges_clips_and_background_recordings(tmp_path):
    custom = str(tmp_path / "custom-clips")
    steam_root, _ = _make_steam_tree(tmp_path, custom_recordings=custom)
    _make_clip(os.path.join(custom, "clips"), CLIP_DIR_NAMES[0])
    bg_dir = os.path.join(custom, "video", "bg_250900_20250701_120000")
    os.makedirs(bg_dir)
    with open(os.path.join(bg_dir, "session.mpd"), "w", encoding="utf-8") as handle:
        handle.write("<MPD/>")
    clips = steam.find_clips(custom)
    names = [c.name for c in clips]
    assert "clip_250900_20251129_034618" in names
    assert "bg_250900_20250701_120000" in names
    assert names == sorted(names, reverse=True)
