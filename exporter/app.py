
import os
import queue
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import ffmpeg, steam

__all__ = ["run"]

APP_TITLE = "Steam 录制导出器"


class ExporterApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("980x680")
        self.root.minsize(820, 560)

        self.users = []
        self.clips = []
        self.game_names = {}
        self.tmp_dir = tempfile.mkdtemp(prefix="sre-")
        self.events = queue.Queue()
        self.scan_thread = None
        self.export_thread = None
        self.cancel_event = threading.Event()
        self.preview_windows = {}
        self.preview_images = {}
        self._sort_col = None
        self._sort_rev = False

        self._build_ui()
        self._poll_events()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.root.after(200, self._auto_detect_steam)

    def _build_ui(self):
        pad = {"padx": 6, "pady": 4}

        top = ttk.Frame(self.root)
        top.pack(fill=tk.X, **pad)

        ttk.Label(top, text="Steam 文件夹:").grid(row=0, column=0, sticky="w")
        self.steam_var = tk.StringVar()
        self.steam_entry = ttk.Entry(top, textvariable=self.steam_var)
        self.steam_entry.grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(top, text="浏览…", command=self._browse_steam).grid(row=0, column=2)
        ttk.Button(top, text="检测", command=self._auto_detect_steam).grid(row=0, column=3, padx=6)

        ttk.Label(top, text="Steam 用户:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.user_combo = ttk.Combobox(top, state="readonly", width=40)
        self.user_combo.grid(row=1, column=1, sticky="ew", padx=6, pady=(8, 0))
        self.user_combo.bind("<<ComboboxSelected>>", self._on_user_selected)
        ttk.Button(top, text="刷新", command=self._refresh_users).grid(
            row=1, column=2, pady=(8, 0)
        )
        ttk.Button(top, text="扫描", command=self._start_scan).grid(
            row=1, column=3, padx=6, pady=(8, 0)
        )
        top.columnconfigure(1, weight=1)

        mid = ttk.Frame(self.root)
        mid.pack(fill=tk.BOTH, expand=True, **pad)
        self.tree = ttk.Treeview(
            mid,
            columns=("game", "when", "size"),
            selectmode="none",
            show="headings",
        )
        self.tree.heading("game", text="游戏（双击预览）", command=lambda: self._sort_by("game"))
        self.tree.heading("when", text="录制时间", command=lambda: self._sort_by("when"))
        self.tree.heading("size", text="大小", command=lambda: self._sort_by("size"))
        self.tree.column("game", width=260, anchor="w")
        self.tree.column("when", width=150, anchor="center")
        self.tree.column("size", width=90, anchor="e")
        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<Double-Button-1>", self._on_tree_double_click)
        scroll = ttk.Scrollbar(mid, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        bottom = ttk.Frame(self.root)
        bottom.pack(fill=tk.X, **pad)

        ttk.Label(bottom, text="导出到:").grid(row=0, column=0, sticky="w")
        self.out_var = tk.StringVar(value=self._default_export_dir())
        self.out_entry = ttk.Entry(bottom, textvariable=self.out_var)
        self.out_entry.grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(bottom, text="浏览…", command=self._browse_output).grid(row=0, column=2)

        actions = ttk.Frame(bottom)
        actions.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        self.export_btn = ttk.Button(actions, text="导出选中项", command=self._start_export)
        self.export_btn.pack(side=tk.LEFT)
        self.cancel_btn = ttk.Button(
            actions, text="取消", command=self._cancel_export, state=tk.DISABLED
        )
        self.cancel_btn.pack(side=tk.LEFT, padx=6)
        self.status_var = tk.StringVar(value="就绪。")
        ttk.Label(actions, textvariable=self.status_var).pack(side=tk.RIGHT)
        bottom.columnconfigure(1, weight=1)

        self.progress = ttk.Progressbar(self.root, mode="determinate")
        self.progress.pack(fill=tk.X, padx=6, pady=(0, 4))

        log_frame = ttk.Frame(self.root)
        log_frame.pack(fill=tk.BOTH, expand=False, padx=6, pady=(0, 6))
        self.log_text = tk.Text(log_frame, height=8, state=tk.DISABLED, wrap=tk.NONE)
        log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _log(self, message: str):
        def update():
            self.log_text.configure(state=tk.NORMAL)
            self.log_text.insert(tk.END, message.rstrip() + "\n")
            self.log_text.see(tk.END)
            self.log_text.configure(state=tk.DISABLED)

        self.root.after(0, update)

    def _set_status(self, message: str):
        self.status_var.set(message)

    def _default_export_dir(self):
        videos = os.path.expanduser(os.path.join("~", "Videos"))
        path = os.path.join(videos, "Steam 录制导出")
        try:
            os.makedirs(path, exist_ok=True)
        except OSError:
            path = os.path.expanduser("~")
        return path

    def _browse_steam(self):
        path = filedialog.askdirectory(title="选择你的 Steam 安装文件夹")
        if path:
            self.steam_var.set(path)
            self._refresh_users()

    def _browse_output(self):
        path = filedialog.askdirectory(title="选择导出文件夹")
        if path:
            self.out_var.set(path)

    def _sort_by(self, col):
        if self._sort_col == col:
            self._sort_rev = not self._sort_rev
        else:
            self._sort_col = col
            self._sort_rev = False
        if not self.clips:
            return
        by_path = {c.path: c for c in self.clips}

        def key(iid):
            clip = by_path.get(iid)
            if col == "when":
                return clip.start_time if clip else ""
            if col == "size":
                return clip.total_size if clip else 0
            return self.tree.set(iid, col)

        items = sorted(self.tree.get_children(), key=key, reverse=self._sort_rev)
        for iid in items:
            self.tree.move(iid, "", tk.END)

    def _on_tree_click(self, event):
        item = self.tree.identify_row(event.y)
        if not item:
            return
        if item in self.tree.selection():
            self.tree.selection_remove(item)
        else:
            self.tree.selection_add(item)
        self._set_status(f"已选中 {len(self.tree.selection())} 个剪辑")

    def _auto_detect_steam(self):
        self._log("正在检测 Steam 安装…")
        installs = steam.find_steam_installations()
        if installs:
            self.steam_var.set(installs[0])
            self._log("找到 Steam 于：" + installs[0])
            self._refresh_users()
        else:
            self._set_status("未找到 Steam —— 请手动选择文件夹。")
            self._log("在常见路径未找到 Steam 安装。")

    def _refresh_users(self):
        path = self.steam_var.get().strip()
        if not path:
            self._log("请先选择 Steam 文件夹。")
            return
        if not steam.is_valid_steam_path(path):
            messagebox.showerror(APP_TITLE, "不是有效的 Steam 文件夹：\n" + path)
            return

        def work():
            users = steam.scan_users(path)
            self.events.put(("users", users))

        self._set_status("正在扫描用户…")
        threading.Thread(target=work, daemon=True).start()

    def _on_user_selected(self, _event=None):
        index = self.user_combo.current()
        if 0 <= index < len(self.users):
            self._log(f"已选择用户：{self.users[index].display_name()}")
            self._start_scan()

    def _on_scan_done(self, users):
        self.users = users
        if not users:
            self.user_combo["values"] = ()
            self._set_status("未找到 Steam 用户。")
            self._log("未找到 Steam 用户。")
            return
        shown = [u for u in users if u.has_recordings or u.id64]
        if not shown:
            shown = users
        shown.sort(key=lambda u: (0 if u.id64 else 1, u.display_name()))
        self.users = shown
        self.user_combo["values"] = [
            u.display_name() + ("（当前账号）" if u.id64 else "") for u in shown
        ]
        self.user_combo.current(0)
        self._set_status(f"找到 {len(shown)} 个用户。")
        self._log(f"找到 {len(shown)} 个 Steam 用户。")
        for user in shown:
            rec = "有录制" if user.has_recordings else "无录制"
            self._log(f"  - {user.display_name()} (id {user.id3}) [{rec}]")
        self._start_scan()

    def _start_scan(self):
        if self.scan_thread and self.scan_thread.is_alive():
            return
        index = self.user_combo.current()
        if index < 0 or index >= len(self.users):
            self._set_status("请先选择 Steam 用户。")
            return
        user = self.users[index]
        recordings = steam.find_game_recordings_path(user)
        if not recordings or not os.path.isdir(recordings):
            self._set_status("该用户暂时没有游戏录制。")
            self._log("未找到该用户的游戏录制。")
            return

        self._set_status("正在扫描剪辑…")
        self._log(f"正在扫描：{recordings}")
        self.tree.delete(*self.tree.get_children())
        steam_path = self.steam_var.get().strip()

        def work():
            clips = steam.find_clips(recordings)
            names = steam.load_game_names(steam_path)
            self.events.put(("clips", clips, names, recordings))

        self.scan_thread = threading.Thread(target=work, daemon=True)
        self.scan_thread.start()

    def _on_clips_done(self, clips, names, recordings):
        self.clips = clips
        self.game_names = names
        self.tree.delete(*self.tree.get_children())
        if not clips:
            self._set_status("未找到录制剪辑。")
            self._log("未在以下位置找到录制剪辑：" + recordings)
            return
        for clip in clips:
            self.tree.insert(
                "",
                tk.END,
                iid=clip.path,
                values=(
                    self._game_label(clip, names),
                    self._format_when(clip),
                    self._format_size(clip.total_size),
                ),
            )
        self._set_status("已选中 0 个剪辑")
        self._log(f"找到 {len(clips)} 个录制剪辑。")

    def _game_label(self, clip, names):
        game = names.get(clip.app_id, "")
        if game:
            return f"{clip.app_id}（{game}）"
        try:
            if int(clip.app_id) >= 2**32:
                return f"{clip.app_id}（非steam游戏）"
        except ValueError:
            pass
        return clip.app_id

    def _segment_source(self, clip):
        if clip.thumbnail:
            return clip.thumbnail
        if clip.segments:
            segment = clip.segments[0]
            try:
                return ffmpeg.fix_mpd(
                    segment.mpd_path,
                    os.path.join(self.tmp_dir, "fix_" + clip.name + ".mpd"),
                )
            except Exception:
                return segment.mpd_path
        return None

    def _extract_frame(self, clip, output_png, width, height):
        ffmpeg_path = ffmpeg.find_ffmpeg()
        if not ffmpeg_path:
            return False
        source = self._segment_source(clip)
        if not source:
            return False
        try:
            subprocess.run(
                [
                    ffmpeg_path,
                    "-y",
                    "-i",
                    source,
                    "-skip_frame",
                    "nokey",
                    "-vf",
                    f"scale={width}:{height}:force_original_aspect_ratio=decrease",
                    "-frames:v",
                    "1",
                    output_png,
                ],
                capture_output=True,
                timeout=120,
            )
        except Exception:
            return False
        return os.path.isfile(output_png)

    def _on_tree_double_click(self, event):
        item = self.tree.identify_row(event.y)
        if not item:
            return
        clip = next((c for c in self.clips if c.path == item), None)
        if not clip:
            return

        win = tk.Toplevel(self.root)
        win.title(f"预览 — {clip.name}")
        win.resizable(False, False)
        label = ttk.Label(win, text="正在加载预览…", padding=16)
        label.pack()
        win_id = id(win)
        self.preview_windows[win_id] = win
        win.protocol("WM_DELETE_WINDOW", lambda: self._close_preview(win_id))

        def work(_clip=clip, _win_id=win_id):
            png = os.path.join(self.tmp_dir, "preview_" + _clip.name + ".png")
            if not os.path.isfile(png):
                self._extract_frame(_clip, png, 960, 540)
            self.events.put(("preview_ready", _win_id, png))

        threading.Thread(target=work, daemon=True).start()

    def _close_preview(self, win_id):
        win = self.preview_windows.pop(win_id, None)
        if win is not None and win.winfo_exists():
            win.destroy()
        self.preview_images.pop(win_id, None)

    def _on_preview_ready(self, win_id, png):
        win = self.preview_windows.get(win_id)
        if win is None or not win.winfo_exists():
            return
        for child in win.winfo_children():
            child.destroy()
        if not os.path.isfile(png):
            ttk.Label(win, text="预览生成失败", padding=16).pack()
            return
        try:
            img = tk.PhotoImage(file=png)
            self.preview_images[win_id] = img
            ttk.Label(win, image=img).pack(padx=8, pady=8)
        except Exception:
            ttk.Label(win, text="预览生成失败", padding=16).pack()

    def _format_when(self, clip):
        try:
            return f"{clip.date[0:4]}-{clip.date[4:6]}-{clip.date[6:8]} {clip.time[0:2]}:{clip.time[2:4]}:{clip.time[4:6]}"
        except IndexError:
            return clip.date + " " + clip.time

    def _format_size(self, size):
        value = float(size)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if value < 1024 or unit == "TB":
                return f"{value:.1f} {unit}"
            value /= 1024
        return f"{value:.1f} GB"

    def _collect_tasks(self):
        tasks = []
        for item in self.tree.selection():
            clip = next((c for c in self.clips if c.path == item), None)
            if not clip or not clip.segments:
                continue
            game = self.game_names.get(clip.app_id, f"游戏 {clip.app_id}")
            for idx, segment in enumerate(clip.segments, start=1):
                tasks.append((clip, game, idx, segment))
        return tasks

    def _start_export(self):
        tasks = self._collect_tasks()
        if not tasks:
            self._set_status("请至少选择一个剪辑再导出。")
            return
        if not ffmpeg.export_supported():
            messagebox.showerror(
                APP_TITLE,
                "未找到 FFmpeg。\n\n"
                "请安装 ffmpeg 并确保它在 PATH 中，然后重新启动。",
            )
            return

        out_dir = self.out_var.get().strip()
        if not out_dir:
            self._set_status("请先选择导出文件夹。")
            return
        try:
            os.makedirs(out_dir, exist_ok=True)
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"无法创建文件夹：\n{exc}")
            return

        self.cancel_event.clear()
        self.export_btn.configure(state=tk.DISABLED)
        self.cancel_btn.configure(state=tk.NORMAL)
        self.total_tasks = len(tasks)
        self.progress.configure(mode="determinate", maximum=self.total_tasks, value=0)
        self._set_status(f"正在导出 {len(tasks)} 个片段…")
        self._log(f"导出开始：{len(tasks)} 个片段，输出到 {out_dir}")

        def work():
            done = 0
            failures = []
            for clip, game, idx, segment in tasks:
                filename = self._output_name(clip, game, idx, segment)
                output = os.path.join(out_dir, filename)
                fixed = None
                try:
                    fixed = ffmpeg.fix_mpd(
                        segment.mpd_path,
                        os.path.join(self.tmp_dir, f"fix_{done}_{os.getpid()}.mpd"),
                    )
                    self.events.put(("log", f"  → {filename}"))
                    offset = ffmpeg.mpd_start_offset(segment.mpd_path)
                    self.events.put(("current", filename, done, len(tasks)))

                    def on_progress(seconds, _seg=filename):
                        self.events.put(("current", _seg, done, len(tasks)))

                    ffmpeg.export_segment(
                        fixed,
                        output,
                        on_progress=on_progress,
                        cancel_event=self.cancel_event,
                        start_offset=offset,
                    )
                    self.events.put(("seg_done", filename, True, ""))
                except ffmpeg.FfmpegError as exc:
                    failures.append((filename, str(exc)))
                    self.events.put(("seg_done", filename, False, str(exc)))
                finally:
                    if fixed and os.path.exists(fixed):
                        try:
                            os.remove(fixed)
                        except OSError:
                            pass
                    done += 1
                    self.events.put(("progress", done))
            self.events.put(("export_done", failures))

        self.export_thread = threading.Thread(target=work, daemon=True)
        self.export_thread.start()

    def _output_name(self, clip, game, idx, segment):
        safe_game = "".join(c for c in game if c not in '<>:"/\\|?*').strip() or "游戏"
        if len(safe_game) > 60:
            safe_game = safe_game[:60]
        when = f"{clip.date}_{clip.time}"
        return f"{safe_game}_{when}_{segment.label}.mp4"

    def _cancel_export(self):
        self.cancel_event.set()
        self._set_status("正在取消…")
        self._log("正在取消导出…")

    def _on_seg_done(self, filename, ok, error):
        if ok:
            self._log(f"    ✓ {filename}")
        else:
            self._log(f"    ✗ {filename}：{error}")

    def _on_export_done(self, failures):
        self.export_btn.configure(state=tk.NORMAL)
        self.cancel_btn.configure(state=tk.DISABLED)
        self.progress.configure(value=self.total_tasks)
        if failures:
            self._set_status(f"完成，共 {len(failures)} 个失败。")
            self._log(f"导出完成：{len(failures)} 个失败。")
        else:
            self._set_status("导出成功。")
            self._log("导出成功。")
            messagebox.showinfo(APP_TITLE, "全部片段导出成功。")

    def _poll_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "users":
                    self._on_scan_done(event[1])
                elif kind == "clips":
                    self._on_clips_done(event[1], event[2], event[3])
                elif kind == "log":
                    self._log(event[1])
                elif kind == "current":
                    _, filename, done, total = event
                    self._set_status(f"({done + 1}/{total}) 正在导出：{filename}")
                elif kind == "seg_done":
                    self._on_seg_done(event[1], event[2], event[3])
                elif kind == "progress":
                    done = event[1]
                    self.progress.configure(value=done)
                    self._set_status(f"已导出 {done} 个片段…")
                elif kind == "preview_ready":
                    self._on_preview_ready(event[1], event[2])
        except queue.Empty:
            pass
        self.root.after(80, self._poll_events)

    def _on_close(self):
        self.cancel_event.set()
        try:
            import shutil

            shutil.rmtree(self.tmp_dir, ignore_errors=True)
        except Exception:
            pass
        self.root.destroy()


def run():
    try:
        root = tk.Tk()
    except Exception as exc:
        print(f"无法启动图形界面：{exc}", file=sys.stderr)
        return 1
    try:
        ttk.Style().theme_use("clam")
    except tk.TclError:
        pass
    ExporterApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    run()
