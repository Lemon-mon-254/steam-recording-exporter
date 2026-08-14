# Steam 录制导出器

用于将 Steam
录制的视频导出为 MP4 文件。在Linux和Windows上可用。


## 功能特性

- 扫描 Steam 游戏录制库，列出所有已录制的剪辑
- 自动识别 Steam 用户
- 使用 `ffmpeg -c copy` 无损导出任意剪辑片段为 MP4
- 自动修复 Steam 的分片式 MP4（DASH）文件

## 系统要求

- Python 3.9+
- ffmpeg 位于 `PATH` 中

## 源码运行

```bash
git clone https://github.com/yourname/steam-recording-exporter.git
cd steam-recording-exporter
python3 main.py
```

## 使用方法

1. 选择你的 Steam 文件夹。
2. 如有多个用户，选择你的 Steam 用户。
3. 点击 *扫描* 列出所有录制剪辑。
4. 选中要导出的剪辑/片段，并选择输出文件夹。
5. 点击 *导出选中项*。


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
