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


## 许可证

MIT
