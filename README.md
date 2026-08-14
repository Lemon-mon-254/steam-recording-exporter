# Steam 录制导出器

一款跨平台（Linux 和 Windows）桌面工具，用于将 Steam（Steam 游戏录制 / Game Recording）
录制的视频无损导出为 MP4 文件，不重新编码、不损失画质。

灵感来自 [Pineapple Steam Recording Exporter](https://github.com/BLumia/pineapple-steam-recording-exporter)。

## 功能特性

- 扫描 Steam 游戏录制库，列出所有已录制的剪辑
- 自动识别 Steam 用户，并从 Steam 库读取游戏的真实名称
- 使用 `ffmpeg -c copy` 无损导出任意剪辑片段为 MP4（不重编码、速度快、无画质损失）
- 自动修复 Steam 的分片式 MP4（DASH）文件，导出后在任何播放器都能正常播放
- 简洁的图形界面，带进度条和实时导出日志
- 无第三方 Python 依赖；发布版捆绑 ffmpeg（Linux 和 Windows），开箱即用

## 系统要求

- Python 3.9+（源码运行方式）
- ffmpeg 位于 `PATH` 中（打包发布版会自动回退到内置的 ffmpeg）

## 源码运行

```bash
git clone https://github.com/yourname/steam-recording-exporter.git
cd steam-recording-exporter
python3 main.py
```

## 使用方法

1. 选择你的 Steam 文件夹（常见安装路径会自动检测）。
2. 如有多个用户，选择你的 Steam 用户。
3. 点击 *扫描剪辑* 列出所有录制剪辑。
4. 选中要导出的剪辑/片段，并选择输出文件夹。
5. 点击 *导出选中项* —— 文件将以 MP4 无损写出。

## 工作原理

Steam 将每一条录制剪辑保存为一个目录：

```
<steam>/userdata/<id>/gamerecordings/clips/clip_<appid>_<YYYYMMDD>_<HHMMSS>/
    thumbnail.jpg
    video/bg_.../session.mpd      # DASH 清单
    video/bg_.../chunk-stream*.m4s  # 分片式 MP4 片段
    video/bg_.../init-stream*.m4s
```

本工具会修复 Steam 的 `session.mpd`（去掉会导致 ffmpeg DASH 解复用器误判时长的
非零 `Period start` 偏移以及尾部垃圾字节），然后执行：

```
ffmpeg -i session.mpd -c copy -avoid_negative_ts make_zero -fflags +genpts \
       -movflags +faststart -y out.mp4
```

全程不重新编码，因此导出无损，且速度远超实时。

## 构建发布版

使用 PyInstaller 构建单个自包含可执行文件。当存在 `vendor/ffmpeg/` 目录时会自动捆绑 ffmpeg：

```bash
python3 -m venv .venv
.venv/bin/pip install pyinstaller
mkdir -p vendor/ffmpeg && cp /usr/bin/ffmpeg /usr/bin/ffprobe vendor/ffmpeg/   # Linux
.venv/bin/pyinstaller packaging/steam-recording-exporter.spec --noconfirm
# 结果：dist/SteamRecordingExporter
```

GitHub Actions 会自动下载静态版 ffmpeg、捆绑打包，并在推送 `v*` 标签时自动构建
Linux 和 Windows 二进制并挂到 Releases 页面。详见 `.github/workflows/release.yml`。

## 开发

```bash
git clone https://github.com/yourname/steam-recording-exporter.git
cd steam-recording-exporter
python3 main.py            # 源码运行 GUI
python3 -m pytest          # 单元测试（tests/）
```

## 许可证

MIT
