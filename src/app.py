"""Tkinter desktop UI for ohos-remote."""

from __future__ import annotations

import argparse
import ctypes
import queue
import re
import sys
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from PIL import Image, ImageTk

from hdc import Hdc, HdcError, find_hdc
from mirror import Mirror
from h264stream import H264Stream


def parse_size(value: str) -> tuple[int, int]:
    left, _, right = value.lower().partition("x")
    return max(1, int(left)), max(1, int(right))


def enable_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


class RemoteApp:
    def __init__(self, root: tk.Tk, hdc_exe: str, target: Optional[str], interval: float,
                 h264: Optional[str] = None, h264_size: tuple[int, int] = (540, 1204),
                 device_size: Optional[tuple[int, int]] = None, ffmpeg_exe: Optional[str] = None):
        self.root = root
        self.hdc_exe = hdc_exe
        self.interval = interval
        self.h264 = h264
        self.h264_size = h264_size
        self.device_size = device_size
        self.ffmpeg_exe = ffmpeg_exe
        self.hdc: Optional[Hdc] = None
        self.mirror: Optional[object] = None
        self.frames: "queue.Queue[tuple[str, object]]" = queue.Queue(maxsize=1)
        self.image: Optional[Image.Image] = None
        self.photo: Optional[ImageTk.PhotoImage] = None
        self.photo_item: Optional[int] = None
        self.device_w = 0
        self.device_h = 0
        self.image_w = 0
        self.image_h = 0
        self.last_click: Optional[tuple[int, int]] = None
        self.press_xy: Optional[tuple[int, int]] = None
        self.fps = 0.0
        self._last_frame_at = 0.0

        root.title("ohos-remote")
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        win_w = min(640, screen_w - 80)
        win_h = min(880, screen_h - 200)
        root.geometry(f"{win_w}x{win_h}+40+40")
        root.minsize(360, 480)
        root.configure(bg="#0b0f16")

        self._build_top()
        self._build_canvas()
        self._build_bottom()

        self.refresh_targets()
        if target:
            self.target_var.set(target)
            self.connect()

    def _build_top(self) -> None:
        bar = tk.Frame(self.root, bg="#0b0f16")
        bar.pack(fill=tk.X, padx=8, pady=6)

        self.target_var = tk.StringVar()
        self.combo = ttk.Combobox(bar, textvariable=self.target_var, width=22, state="readonly")
        self.combo.pack(side=tk.LEFT)

        ttk.Button(bar, text="刷新", command=self.refresh_targets).pack(side=tk.LEFT, padx=4)
        self.connect_btn = ttk.Button(bar, text="连接", command=self.toggle_connect)
        self.connect_btn.pack(side=tk.LEFT, padx=4)
        self.status_var = tk.StringVar(value="未连接")
        tk.Label(self.root, textvariable=self.status_var, fg="#8fa3bd", bg="#0b0f16",
                 anchor=tk.W, font=("Segoe UI", 9)).pack(fill=tk.X, padx=10, pady=(0, 4))

    def _build_canvas(self) -> None:
        self.canvas = tk.Canvas(self.root, bg="#000000", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

    def _build_bottom(self) -> None:
        bar = tk.Frame(self.root, bg="#0b0f16")
        bar.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=6)

        tk.Label(bar, text="文本", fg="#8fa3bd", bg="#0b0f16").pack(side=tk.LEFT)
        self.text_var = tk.StringVar()
        entry = tk.Entry(bar, textvariable=self.text_var, width=28)
        entry.pack(side=tk.LEFT, padx=4)
        entry.bind("<Return>", lambda _e: self.send_text())
        ttk.Button(bar, text="发送", command=self.send_text).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="保存截图", command=self.save_png).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="返回", command=lambda: self.key(2)).pack(side=tk.LEFT, padx=2)

    def refresh_targets(self) -> None:
        try:
            targets = Hdc(self.hdc_exe).list_targets()
        except (HdcError, OSError) as exc:
            self.status_var.set("hdc 不可用: " + str(exc))
            return
        self.combo["values"] = targets
        if targets and not self.target_var.get():
            self.target_var.set(targets[0])
        if not targets:
            self.status_var.set("未发现设备")

    def toggle_connect(self) -> None:
        if self.hdc is None:
            self.connect()
        else:
            self.disconnect()

    def connect(self) -> None:
        target = self.target_var.get().strip()
        if not target:
            messagebox.showinfo("ohos-remote", "请先选择设备")
            return
        try:
            hdc = Hdc(self.hdc_exe, target)
            model = hdc.model()
        except (HdcError, OSError, RuntimeError) as exc:
            messagebox.showerror("ohos-remote", "连接失败: " + str(exc))
            return
        self.hdc = hdc
        if self.device_size is None:
            try:
                out = hdc.shell("hidumper -s RenderService -a screen", timeout=5)
                match = re.search(r"render size:\s*(\d+)\s*x\s*(\d+)", out)
                if match:
                    self.device_size = (int(match.group(1)), int(match.group(2)))
            except HdcError:
                pass
        if self.device_size is None and self.h264:
            self.device_size = (self.h264_size[0] * 2, self.h264_size[1] * 2)
        if self.h264:
            self.mirror = H264Stream(self.h264, self.h264_size, self.frames, self.ffmpeg_exe)
        else:
            self.mirror = Mirror(hdc, self.frames, self.interval)
        self.mirror.start()
        self.connect_btn.configure(text="断开")
        mode = f"H264 {self.h264}" if self.h264 else "快照"
        self.status_var.set(f"{model or target} · {mode} · 连接中")
        self.root.after(30, self.poll)

    def disconnect(self) -> None:
        if self.mirror is not None:
            self.mirror.stop()
            self.mirror = None
        self.hdc = None
        self.connect_btn.configure(text="连接")
        self.status_var.set("未连接")
        self.image = None
        self.photo = None
        self.photo_item = None
        self.image_w = self.image_h = 0
        self.canvas.delete("all")

    def poll(self) -> None:
        try:
            kind, value = self.frames.get_nowait()
        except queue.Empty:
            kind, value = "", None
        if kind == "frame" and isinstance(value, Image.Image):
            now = time.time()
            if self._last_frame_at > 0:
                dt = now - self._last_frame_at
                fps = 1.0 / dt if dt > 0 else 0.0
                self.fps = self.fps * 0.7 + fps * 0.3 if self.fps else fps
            self._last_frame_at = now
            self.show_image(value)
        elif kind == "error":
            self.status_var.set("采集失败: " + str(value)[:80])
        if self.mirror is not None:
            self.root.after(30, self.poll)

    def show_image(self, img: Image.Image) -> None:
        self.image = img
        self.image_w, self.image_h = img.size
        self.device_w, self.device_h = self.device_size or img.size
        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())
        scale = min(cw / img.width, ch / img.height)
        size = (max(1, int(img.width * scale)), max(1, int(img.height * scale)))
        scaled = img.resize(size, Image.BILINEAR)
        self.photo = ImageTk.PhotoImage(scaled)
        if self.photo_item is None:
            self.photo_item = self.canvas.create_image(cw // 2, ch // 2, image=self.photo, anchor=tk.CENTER)
        else:
            self.canvas.coords(self.photo_item, cw // 2, ch // 2)
            self.canvas.itemconfigure(self.photo_item, image=self.photo)
        native = f" → {self.device_w}x{self.device_h}" if self.device_size else ""
        self.status_var.set(f"{self.fps:.1f}fps · {img.width}x{img.height}{native}")
        self.root.title(f"ohos-remote - {self.target_var.get()}")

    def canvas_to_device(self, x: int, y: int) -> Optional[tuple[int, int]]:
        if self.image_w <= 0 or self.device_w <= 0:
            return None
        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())
        scale = min(cw / self.image_w, ch / self.image_h)
        dw = self.image_w * scale
        dh = self.image_h * scale
        ox = (cw - dw) / 2
        oy = (ch - dh) / 2
        rx = (x - ox) / scale
        ry = (y - oy) / scale
        if rx < 0 or ry < 0 or rx > self.image_w or ry > self.image_h:
            return None
        dx = int(rx * self.device_w / self.image_w)
        dy = int(ry * self.device_h / self.image_h)
        return max(0, min(self.device_w - 1, dx)), max(0, min(self.device_h - 1, dy))

    def _ripple(self, x: int, y: int) -> None:
        self.canvas.delete("ripple")
        r = 12
        self.canvas.create_oval(x - r, y - r, x + r, y + r, outline="#ff5a5f",
                                width=2, tags="ripple")
        self.root.after(220, lambda: self.canvas.delete("ripple"))

    def on_press(self, event: tk.Event) -> None:
        self.press_xy = (event.x, event.y)

    def on_drag(self, _event: tk.Event) -> None:
        pass

    def on_release(self, event: tk.Event) -> None:
        if self.hdc is None or self.press_xy is None:
            return
        px, py = self.press_xy
        self.press_xy = None
        target = self.canvas_to_device(event.x, event.y)
        origin = self.canvas_to_device(px, py)
        if target is None or origin is None:
            self.status_var.set("点击在画面外")
            return
        dx, dy = target
        ox, oy = origin
        self.last_click = (dx, dy)
        self._ripple(event.x, event.y)
        try:
            if abs(event.x - px) + abs(event.y - py) < 12:
                self.hdc.tap(dx, dy)
            else:
                self.hdc.swipe(ox, oy, dx, dy, 200)
            self.status_var.set(f"输入 {dx},{dy}")
        except HdcError as exc:
            self.status_var.set("输入失败: " + str(exc))

    def send_text(self) -> None:
        text = self.text_var.get()
        if self.hdc is None or not text:
            return
        x, y = self.last_click or (self.device_w // 2, self.device_h // 2)
        try:
            self.hdc.input_text(x, y, text)
            self.text_var.set("")
        except HdcError as exc:
            self.status_var.set("输入失败: " + str(exc))

    def key(self, code: int) -> None:
        if self.hdc is None:
            return
        try:
            self.hdc.key_event(code)
        except HdcError as exc:
            self.status_var.set("按键失败: " + str(exc))

    def save_png(self) -> None:
        if self.image is None:
            return
        path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG", "*.png")])
        if path:
            self.image.save(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="ohos-remote: hdc screen mirror + control")
    parser.add_argument("--hdc", default=None, help="path to hdc executable")
    parser.add_argument("--target", default=None, help="device serial / IP:port")
    parser.add_argument("--fps", type=float, default=2.5, help="capture interval target")
    parser.add_argument("--h264", default=None, help="H264 TCP endpoint, e.g. 192.168.31.27:8766")
    parser.add_argument("--h264-size", default="540x1204", help="decoded H264 size (default 540x1204)")
    parser.add_argument("--device-size", default=None, help="native device size for input, e.g. 1080x2408")
    parser.add_argument("--ffmpeg", default=None, help="path to ffmpeg executable")
    args = parser.parse_args()

    exe = args.hdc or find_hdc()
    interval = 1.0 / max(0.5, args.fps)
    enable_dpi_awareness()
    root = tk.Tk()
    RemoteApp(
        root, exe, args.target, interval,
        h264=args.h264,
        h264_size=parse_size(args.h264_size),
        device_size=parse_size(args.device_size) if args.device_size else None,
        ffmpeg_exe=args.ffmpeg,
    )
    root.mainloop()


if __name__ == "__main__":
    main()
