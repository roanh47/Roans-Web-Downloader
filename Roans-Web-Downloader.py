#!/usr/bin/env python3
"""
Roan's Web Downloader - Cross-platform downloader with resume, auto-retry,
concurrent (multi-file) downloads and per-download priorities. Dark themed.

Run with: python Roans-Web-Downloader.py
No build required. Works on Windows, macOS, and Linux.
"""

import os
import time
import threading
import urllib.request
import urllib.error
from pathlib import Path

# --- GUI (tkinter is built into Python) ---
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

FONT = "Segoe UI"

# --- Dark palette ---
BG = "#12141c"          # window background
PANEL = "#1b1e29"       # cards / bars
FIELD = "#252938"       # inputs, tree rows
FIELD_ALT = "#2b3040"   # alternating tree rows
FG = "#e6e6e6"
FG_DIM = "#8b90a0"
BORDER = "#333849"
ACCENT = "#2f6df6"
ACCENT_HOVER = "#4b83ff"
ACCENT_PRESS = "#245ad0"
GREEN = "#3ecf8e"
RED = "#ff5f6d"
YELLOW = "#f2c94c"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

PRIORITY_LABELS = {0: "High", 1: "Normal", 2: "Low"}


# ----------------------------------------------------------------------
# Custom rounded button (drawn on a Canvas)
# ----------------------------------------------------------------------
def _round_rect_points(x1, y1, x2, y2, r):
    return [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]


class RoundedButton(tk.Canvas):
    def __init__(self, parent, text="", command=None, *, width=120, height=34,
                 radius=9, surface=BG, fill=FIELD, hover=BORDER, fg=FG,
                 font=None, accent=False):
        super().__init__(parent, width=width, height=height, bg=surface,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.command = command
        self._bw, self._bh = width, height
        self._radius = radius
        self._text = text
        self._font = font or (FONT, 10)
        self._accent = accent
        self._fg = "#ffffff" if accent else fg
        self._base_fill = ACCENT if accent else fill
        self._hover_fill = ACCENT_HOVER if accent else hover
        self._enabled = True
        self._selected = False
        self._shape = None
        self._label = None

        self._draw()
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Return>", lambda e: self._invoke())
        self.bind("<space>", lambda e: self._invoke())

    # -- drawing -------------------------------------------------------
    def _draw(self):
        self.delete("all")
        points = _round_rect_points(1, 1, self._bw - 1, self._bh - 1, self._radius)
        self._shape = self.create_polygon(
            points, smooth=True, splinesteps=36, fill=self._fill(),
            outline=BORDER, width=1,
        )
        self._label = self.create_text(
            self._bw / 2, self._bh / 2 + 1, text=self._text,
            fill=self._fg if self._enabled else FG_DIM, font=self._font,
        )

    def _fill(self):
        if not self._enabled:
            return PANEL
        if self._selected:
            return ACCENT
        return self._base_fill

    # -- events --------------------------------------------------------
    def _on_enter(self, _):
        if self._enabled:
            self.itemconfig(
                self._shape,
                fill=ACCENT_HOVER if (self._accent or self._selected) else self._hover_fill,
            )

    def _on_leave(self, _):
        self.itemconfig(self._shape, fill=self._fill())

    def _on_press(self, _):
        if self._enabled:
            self.itemconfig(
                self._shape,
                fill=ACCENT_PRESS if (self._accent or self._selected) else PANEL,
            )

    def _on_release(self, _):
        if self._enabled:
            self.itemconfig(self._shape, fill=self._fill())
            self._invoke()

    def _invoke(self):
        if self._enabled and self.command:
            self.command()

    # -- public API ----------------------------------------------------
    def set_selected(self, flag):
        self._selected = bool(flag)
        if self._shape and self._label:
            self.itemconfig(self._shape, fill=self._fill())
            self.itemconfig(self._label, fill="#ffffff" if flag else self._fg)

    def set_state(self, enabled):
        self._enabled = bool(enabled)
        self.configure(cursor="hand2" if self._enabled else "")
        if self._shape and self._label:
            self.itemconfig(self._shape, fill=self._fill())
            self.itemconfig(
                self._label, fill=self._fg if self._enabled else FG_DIM
            )


# ----------------------------------------------------------------------
# Rounded input surfaces (a rounded background with a borderless widget)
# ----------------------------------------------------------------------
class _RoundedSurface(tk.Frame):
    """A frame that paints a rounded rectangle behind a child widget."""

    def __init__(self, parent, *, surface=BG, fill=FIELD, radius=9,
                 height=36, outline=BORDER):
        super().__init__(parent, bg=surface, height=height)
        self.pack_propagate(False)
        self._radius = radius
        self._fill = fill
        self._surface = surface
        self._outline = outline
        self._item = None
        self.canvas = tk.Canvas(
            self, bg=surface, highlightthickness=0, bd=0, takefocus=0
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", self._on_configure)

    def _on_configure(self, event):
        self.canvas.delete("bg")
        points = _round_rect_points(
            1, 1, event.width - 1, event.height - 1, self._radius
        )
        self._item = self.canvas.create_polygon(
            points, smooth=True, splinesteps=36, fill=self._fill,
            outline=self._outline, width=1, tags="bg",
        )
        self.canvas.tag_lower("bg")
        self._layout(event.width, event.height)

    def _layout(self, width, height):
        pass

    def set_outline(self, color):
        self._outline = color
        if self._item is not None:
            self.canvas.itemconfig(self._item, outline=color)


class RoundedEntry(_RoundedSurface):
    def __init__(self, parent, textvariable=None, *, height=34, surface=BG,
                 fill=FIELD, fg=FG, font=None, radius=9):
        super().__init__(
            parent, surface=surface, fill=fill, radius=radius, height=height
        )
        self.entry = tk.Entry(
            self.canvas, textvariable=textvariable, bd=0, relief="flat",
            bg=fill, fg=fg, insertbackground=ACCENT, selectbackground=ACCENT,
            selectforeground="#ffffff", font=font or (FONT, 10),
            highlightthickness=0,
        )
        self.entry.bind("<FocusIn>", lambda e: self.set_outline(ACCENT))
        self.entry.bind("<FocusOut>", lambda e: self.set_outline(BORDER))

    def _layout(self, width, height):
        self.entry.place(
            in_=self.canvas, x=12, y=6, relwidth=1.0, width=-24,
            height=height - 12,
        )


class RoundedText(_RoundedSurface):
    def __init__(self, parent, *, height=76, surface=PANEL, fill=FIELD, fg=FG,
                 font=None, radius=10):
        super().__init__(
            parent, surface=surface, fill=fill, radius=radius, height=height
        )
        self.text = tk.Text(
            self.canvas, bd=0, relief="flat", bg=fill, fg=fg,
            insertbackground=ACCENT, selectbackground=ACCENT,
            selectforeground="#ffffff", font=font or (FONT, 10), wrap="none",
            undo=True, highlightthickness=0, padx=8, pady=6,
        )
        self.text.bind("<FocusIn>", lambda e: self.set_outline(ACCENT))
        self.text.bind("<FocusOut>", lambda e: self.set_outline(BORDER))

    def _layout(self, width, height):
        self.text.place(
            in_=self.canvas, x=3, y=3, relwidth=1.0, width=-6, height=height - 6
        )


# ----------------------------------------------------------------------
# Data model
# ----------------------------------------------------------------------
class DownloadTask:
    """A single queued download."""

    def __init__(self, url, folder, output_path):
        self.url = url
        self.folder = folder
        self.output_path = output_path
        self.filename = os.path.basename(output_path)

        # Machine + human state
        self.state = "queued"  # queued|downloading|complete|failed|cancelled
        self.status = "Queued"

        # Progress
        self.downloaded = 0
        self.total = 0
        self.speed = 0
        self.eta = 0

        # Control
        self.cancel_flag = False
        self.retry_count = 0
        self.probed_name = False
        self.item_id = None

        # Priority: 0 = High, 1 = Normal, 2 = Low
        self.priority = 1


# ----------------------------------------------------------------------
# Download manager (runs downloads in background threads)
# ----------------------------------------------------------------------
class DownloadManager:
    def __init__(self, app, max_retries=10):
        self.app = app
        self.max_retries = max_retries
        self.tasks = []
        self.pending = []
        self.active = set()
        self.max_concurrent = 3
        self.running = False
        self.lock = threading.Lock()

    # -- queue control -------------------------------------------------
    def add(self, task):
        with self.lock:
            self.tasks.append(task)

    def start_all(self):
        start = False
        with self.lock:
            for t in self.tasks:
                if (
                    t.state in ("queued", "cancelled", "failed")
                    and t not in self.active
                    and t not in self.pending
                ):
                    t.cancel_flag = False
                    t.retry_count = 0
                    t.state = "queued"
                    t.status = "Queued"
                    self.pending.append(t)
            if self.pending and not self.running:
                self.running = True
                start = True
        if start:
            threading.Thread(target=self._scheduler, daemon=True).start()
        self.app.root.after(0, self.app._refresh_all_rows)

    def cancel_all(self):
        with self.lock:
            for t in self.pending:
                t.cancel_flag = True
                t.state = "cancelled"
                t.status = "Cancelled"
            self.pending = []
            targets = list(self.tasks)
        for t in targets:
            t.cancel_flag = True
            if t.state in ("queued", "downloading"):
                t.status = "Cancelling..."
        for t in targets:
            self.app.root.after(0, lambda t=t: self.app._refresh_row(t))
        self.app.root.after(0, self.app._update_status_bar)

    def clear_finished(self):
        with self.lock:
            keep = []
            for t in self.tasks:
                if t.state in ("complete", "failed", "cancelled") and t not in self.active:
                    if t.item_id is not None:
                        self.app.root.after(0, lambda i=t.item_id: self._forget(i))
                else:
                    keep.append(t)
            self.tasks = keep
        self.app.root.after(0, self.app._refresh_all_rows)

    def _reorder_pending(self):
        """Restore pending order to match the queue order (lock held)."""
        order = {id(t): i for i, t in enumerate(self.tasks)}
        self.pending.sort(key=lambda t: order.get(id(t), 0))

    def _forget(self, iid):
        try:
            if self.app.tree.exists(iid):
                self.app.tree.delete(iid)
        except Exception:
            pass
        self.app.tasks_by_iid.pop(iid, None)

    # -- scheduling ----------------------------------------------------
    def _scheduler(self):
        while True:
            with self.lock:
                while self.pending and len(self.active) < self.max_concurrent:
                    # Highest priority first; ties keep queue order (stable).
                    self.pending.sort(key=lambda t: t.priority)
                    task = self.pending.pop(0)
                    self.active.add(task)
                    threading.Thread(
                        target=self._run_task, args=(task,), daemon=True
                    ).start()
                if not self.pending and not self.active:
                    self.running = False
                    break
            time.sleep(0.1)
        self.app.root.after(0, self.app._on_batch_done)

    def _run_task(self, task):
        try:
            self._download_task(task)
        finally:
            with self.lock:
                self.active.discard(task)

    # -- retry loop ----------------------------------------------------
    def _download_task(self, task):
        if task.state == "cancelled":
            return
        task.state = "downloading"
        task.status = "Starting..."
        task.speed = 0
        task.eta = 0
        self.app.root.after(0, lambda: self.app._refresh_row(task))

        while task.retry_count <= self.max_retries and not task.cancel_flag:
            try:
                success, partial = self._do_download(task)
                if success:
                    if not task.cancel_flag:
                        task.state = "complete"
                        task.status = "Complete"
                        task.speed = 0
                        task.eta = 0
                        task.downloaded = task.total or task.downloaded
                        self.app.root.after(0, lambda: self.app._refresh_row(task))
                    return
                if partial:
                    raise ConnectionError("Download interrupted")
            except Exception as e:
                if task.cancel_flag:
                    break
                task.retry_count += 1
                if task.retry_count > self.max_retries:
                    task.state = "failed"
                    task.status = f"Failed: {e}"
                    task.speed = 0
                    self.app.root.after(0, lambda: self.app._refresh_row(task))
                    return
                wait = min(2 ** (task.retry_count - 1), 60)
                task.status = (
                    f"Retry {task.retry_count}/{self.max_retries} in {wait}s"
                )
                self.app.root.after(0, lambda: self.app._refresh_row(task))
                for _ in range(int(wait * 10)):
                    if task.cancel_flag:
                        break
                    time.sleep(0.1)

        if task.cancel_flag:
            task.state = "cancelled"
            task.status = "Cancelled"
            task.speed = 0
            self.app.root.after(0, lambda: self.app._refresh_row(task))

    # -- actual transfer ----------------------------------------------
    def _do_download(self, task):
        """
        Download one task with resume support using urllib.

        Returns (success, partial):
          - (True, False)  -> finished cleanly
          - (False, True)  -> connection dropped (file kept for resume)
          - raises on hard errors (DNS, 404, etc.)
        """
        url = task.url

        # --- Probe server: total size + Range support + real filename ---
        remote_size = 0
        accepts_ranges = False
        cd_name = None

        req = urllib.request.Request(url, method="HEAD")
        req.add_header("User-Agent", USER_AGENT)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                remote_size = int(resp.headers.get("Content-Length", 0))
                accepts_ranges = (
                    resp.headers.get("Accept-Ranges", "").lower() == "bytes"
                )
                cd_name = self._name_from_headers(resp.headers)
        except (urllib.error.HTTPError, urllib.error.URLError):
            probe_req = urllib.request.Request(url)
            probe_req.add_header("User-Agent", USER_AGENT)
            probe_req.add_header("Range", "bytes=0-0")
            try:
                with urllib.request.urlopen(probe_req, timeout=30) as resp:
                    content_range = resp.headers.get("Content-Range", "")
                    if content_range:
                        remote_size = int(content_range.split("/")[-1])
                        accepts_ranges = True
                    else:
                        remote_size = int(resp.headers.get("Content-Length", 0))
                    cd_name = self._name_from_headers(resp.headers)
            except Exception:
                remote_size = 0
                accepts_ranges = False

        # --- Adopt the server-provided filename (once) ---
        if cd_name and not task.probed_name:
            task.probed_name = True
            if cd_name != task.filename:
                new_path = self.app._unique_output_path(
                    task.folder, cd_name, exclude=task
                )
                task.output_path = new_path
                task.filename = os.path.basename(new_path)

        existing_size = 0
        if os.path.exists(task.output_path):
            existing_size = os.path.getsize(task.output_path)

        resume = (
            accepts_ranges
            and existing_size > 0
            and (remote_size == 0 or existing_size < remote_size)
        )

        get_req = urllib.request.Request(url)
        get_req.add_header("User-Agent", USER_AGENT)
        if resume:
            get_req.add_header("Range", f"bytes={existing_size}-")

        with urllib.request.urlopen(get_req, timeout=30) as resp:
            content_range = resp.headers.get("Content-Range", "")
            if content_range:
                total = int(content_range.split("/")[-1])
                downloaded = existing_size
                mode = "ab"
            else:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                mode = "wb"
                if resume and total > 0 and existing_size >= total:
                    task.total = total
                    task.downloaded = total
                    return (True, False)

            task.total = total
            task.downloaded = downloaded

            block_size = 1024 * 64  # 64 KiB
            start_time = time.monotonic()
            last_progress = 0.0

            with open(task.output_path, mode) as f:
                while not task.cancel_flag:
                    try:
                        chunk = resp.read(block_size)
                    except (
                        ConnectionResetError,
                        TimeoutError,
                        OSError,
                        urllib.error.URLError,
                    ):
                        return (False, True)

                    if not chunk:
                        break

                    f.write(chunk)
                    downloaded += len(chunk)
                    task.downloaded = downloaded

                    now = time.monotonic()
                    if now - last_progress > 0.25:
                        last_progress = now
                        elapsed = now - start_time
                        task.speed = downloaded / elapsed if elapsed > 0 else 0
                        if total > 0 and task.speed > 0:
                            task.eta = (total - downloaded) / task.speed
                        task.status = (
                            "Downloading"
                            if task.eta <= 0
                            else f"ETA {self.app._fmt_time(task.eta)}"
                        )
                        self.app.root.after(
                            0, lambda t=task: self.app._refresh_row(t)
                        )

                if task.cancel_flag:
                    return (False, True)

                if total > 0 and downloaded < total:
                    return (False, True)

        return (True, False)

    @staticmethod
    def _name_from_headers(headers):
        """Extract a filename from a Content-Disposition header, if present."""
        cd = headers.get("Content-Disposition", "")
        if not cd:
            return None
        from urllib.parse import unquote as url_unquote
        import re

        m = re.search(r"filename\*=([^;]+)", cd, re.IGNORECASE)
        if m:
            enc_part = m.group(1).strip().strip('"').strip("'")
            parts = enc_part.split("'", 2)
            if len(parts) == 3:
                return os.path.basename(url_unquote(parts[2]))
        m = re.search(r'filename="?([^";]+)"?', cd, re.IGNORECASE)
        if m:
            return os.path.basename(url_unquote(m.group(1).strip()))
        return None


# ----------------------------------------------------------------------
# GUI
# ----------------------------------------------------------------------
class DownloaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Roan's Web Downloader")
        self.root.geometry("940x640")
        self.root.minsize(780, 520)
        self.root.configure(bg=BG)

        self.manager = DownloadManager(self)
        self.tasks_by_iid = {}
        self.priority_buttons = {}

        self._apply_theme()
        self._build_ui()
        self._enable_dark_titlebar()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------
    def _apply_theme(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            "Treeview", background=FIELD, fieldbackground=FIELD, foreground=FG,
            bordercolor=BG, borderwidth=0, relief="flat", rowheight=34,
            lightcolor=FIELD, darkcolor=FIELD, font=(FONT, 10),
        )
        style.map(
            "Treeview",
            background=[("selected", ACCENT)],
            foreground=[("selected", "#ffffff")],
        )
        style.configure(
            "Treeview.Heading", background=PANEL, foreground=FG_DIM,
            relief="flat", borderwidth=0, padding=(8, 8),
            font=(FONT, 9, "bold"),
        )
        style.map("Treeview.Heading", background=[("active", FIELD_ALT)])

        style.configure(
            "Vertical.TScrollbar", background=BORDER, troughcolor=BG,
            bordercolor=BG, arrowcolor=FG_DIM, relief="flat",
            darkcolor=BORDER, lightcolor=BORDER, arrowsize=14,
        )
        style.map(
            "Vertical.TScrollbar",
            background=[("active", ACCENT), ("pressed", ACCENT_PRESS)],
        )

    def _enable_dark_titlebar(self):
        """Ask Windows to draw a dark title bar (best effort)."""
        if os.name != "nt":
            return
        try:
            import ctypes

            self.root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            value = ctypes.c_int(1)
            for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)
                )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        main = tk.Frame(self.root, bg=BG)
        main.pack(fill=tk.BOTH, expand=True, padx=18, pady=(14, 12))
        main.columnconfigure(0, weight=1)
        main.rowconfigure(3, weight=1)

        self._build_header(main, row=0)
        self._build_input_card(main, row=1)
        self._build_queue_header(main, row=2)
        self._build_tree(main, row=3)
        self._build_bottom_bar(main, row=4)
        self._build_status_bar(main, row=5)

    def _build_header(self, parent, row):
        header = tk.Frame(parent, bg=BG)
        header.grid(row=row, column=0, sticky=tk.EW)
        tk.Label(
            header, text="Roan's Web Downloader", bg=BG, fg="#ffffff",
            font=(FONT, 18, "bold"),
        ).pack(anchor="w")
        tk.Label(
            header,
            text="Concurrent downloads  ·  resume  ·  auto-retry  ·  priorities",
            bg=BG, fg=FG_DIM, font=(FONT, 9),
        ).pack(anchor="w", pady=(2, 0))
        tk.Frame(header, bg=ACCENT, height=2).pack(fill="x", pady=(10, 0))

    def _build_input_card(self, parent, row):
        card = tk.Frame(parent, bg=PANEL)
        card.grid(row=row, column=0, sticky=tk.EW, pady=(14, 0))
        card.columnconfigure(0, weight=1)

        inner = tk.Frame(card, bg=PANEL)
        inner.grid(row=0, column=0, sticky=tk.EW, padx=14, pady=12)
        inner.columnconfigure(0, weight=1)

        tk.Label(
            inner, text="ADD URLS   (one per line)", bg=PANEL, fg=FG_DIM,
            font=(FONT, 8, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w")

        url_box = RoundedText(inner, height=78, surface=PANEL)
        url_box.grid(row=1, column=0, sticky=tk.EW, pady=(6, 0))
        self.url_text = url_box.text
        self.url_text.bind("<Return>", self._on_url_return)

        RoundedButton(
            inner, text="Add to Queue", command=self._add_urls, width=140,
            height=78, radius=10, surface=PANEL, accent=True,
            font=(FONT, 10, "bold"),
        ).grid(row=1, column=1, sticky=tk.N, padx=(10, 0), pady=(6, 0))

    def _build_queue_header(self, parent, row):
        qh = tk.Frame(parent, bg=BG)
        qh.grid(row=row, column=0, sticky=tk.EW, pady=(16, 6))
        qh.columnconfigure(0, weight=1)

        tk.Label(
            qh, text="QUEUE", bg=BG, fg=FG_DIM, font=(FONT, 8, "bold")
        ).grid(row=0, column=0, sticky="w")

        RoundedButton(
            qh, text="↑", command=lambda: self._move_selected(-1), width=38,
            height=30, radius=8, surface=BG, font=(FONT, 12),
        ).grid(row=0, column=1, padx=(0, 4))
        RoundedButton(
            qh, text="↓", command=lambda: self._move_selected(1), width=38,
            height=30, radius=8, surface=BG, font=(FONT, 12),
        ).grid(row=0, column=2, padx=(0, 12))
        tk.Label(
            qh, text="Priority:", bg=BG, fg=FG_DIM, font=(FONT, 9)
        ).grid(row=0, column=3, padx=(0, 6))

        for col, (text, value) in enumerate(
            (("High", 0), ("Normal", 1), ("Low", 2)), start=4
        ):
            btn = RoundedButton(
                qh, text=text, command=lambda v=value: self._set_priority(v),
                width=66, height=30, radius=8, surface=BG, font=(FONT, 9),
            )
            btn.grid(row=0, column=col, padx=(0, 5))
            self.priority_buttons[value] = btn

    def _build_tree(self, parent, row):
        frame = tk.Frame(parent, bg=BG)
        frame.grid(row=row, column=0, sticky=tk.NSEW)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        columns = ("priority", "name", "size", "progress", "speed", "status")
        self.tree = ttk.Treeview(
            frame, columns=columns, show="headings", selectmode="extended"
        )
        headings = {
            "priority": ("Priority", 78),
            "name": ("File", 230),
            "size": ("Size", 150),
            "progress": ("Progress", 175),
            "speed": ("Speed", 90),
            "status": ("Status", 150),
        }
        for col, (text, width) in headings.items():
            self.tree.heading(col, text=text, anchor=tk.W)
            self.tree.column(col, width=width, anchor=tk.W, stretch=col == "name")
        self.tree.grid(row=0, column=0, sticky=tk.NSEW)

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        vsb.grid(row=0, column=1, sticky=tk.NS)
        self.tree.configure(yscrollcommand=vsb.set)

        self.tree.tag_configure("queued", foreground=FG_DIM)
        self.tree.tag_configure("downloading", foreground=FG)
        self.tree.tag_configure("complete", foreground=GREEN)
        self.tree.tag_configure("failed", foreground=RED)
        self.tree.tag_configure("cancelled", foreground=YELLOW)
        self.tree.tag_configure("band0", background=FIELD)
        self.tree.tag_configure("band1", background=FIELD_ALT)

        self.tree.bind("<<TreeviewSelect>>", self._update_priority_controls)

    def _build_bottom_bar(self, parent, row):
        bar = tk.Frame(parent, bg=PANEL)
        bar.grid(row=row, column=0, sticky=tk.EW, pady=(14, 0))

        inner = tk.Frame(bar, bg=PANEL)
        inner.pack(fill="x", padx=14, pady=12)

        # --- Save-to row: label | rounded entry (expands) | Browse ---
        folder_row = tk.Frame(inner, bg=PANEL)
        folder_row.pack(fill="x")
        tk.Label(
            folder_row, text="Save to", bg=PANEL, fg=FG_DIM, font=(FONT, 9)
        ).pack(side=tk.LEFT, padx=(0, 10))
        RoundedButton(
            folder_row, text="Browse…", command=self._pick_folder, width=94,
            height=34, radius=9, surface=PANEL,
        ).pack(side=tk.RIGHT, padx=(8, 0))
        self.folder_var = tk.StringVar(value=str(Path.home() / "Downloads"))
        self.folder_entry = RoundedEntry(
            folder_row, textvariable=self.folder_var, height=34, surface=PANEL
        )
        self.folder_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # --- Controls row: Concurrent stepper (left) | actions (right) ---
        ctrl_row = tk.Frame(inner, bg=PANEL)
        ctrl_row.pack(fill="x", pady=(12, 0))

        tk.Label(
            ctrl_row, text="Concurrent", bg=PANEL, fg=FG_DIM, font=(FONT, 9)
        ).pack(side=tk.LEFT, padx=(0, 10))
        RoundedButton(
            ctrl_row, text="−", command=self._dec_concurrent, width=32,
            height=30, radius=8, surface=PANEL, font=(FONT, 13),
        ).pack(side=tk.LEFT)
        self.concurrent_label = tk.Label(
            ctrl_row, text=str(self.manager.max_concurrent), bg=PANEL, fg=FG,
            font=(FONT, 11, "bold"), width=3,
        )
        self.concurrent_label.pack(side=tk.LEFT)
        RoundedButton(
            ctrl_row, text="+", command=self._inc_concurrent, width=32,
            height=30, radius=8, surface=PANEL, font=(FONT, 13),
        ).pack(side=tk.LEFT)

        RoundedButton(
            ctrl_row, text="Start downloads", command=self.manager.start_all,
            width=150, height=32, radius=8, surface=PANEL, accent=True,
            font=(FONT, 10, "bold"),
        ).pack(side=tk.RIGHT)
        RoundedButton(
            ctrl_row, text="Cancel all", command=self.manager.cancel_all,
            width=96, height=32, radius=8, surface=PANEL,
        ).pack(side=tk.RIGHT, padx=(0, 6))
        RoundedButton(
            ctrl_row, text="Clear finished", command=self.manager.clear_finished,
            width=116, height=32, radius=8, surface=PANEL,
        ).pack(side=tk.RIGHT, padx=(0, 6))
        RoundedButton(
            ctrl_row, text="Remove", command=self._remove_selected, width=84,
            height=32, radius=8, surface=PANEL,
        ).pack(side=tk.RIGHT, padx=(0, 6))

    def _build_status_bar(self, parent, row):
        bar = tk.Frame(parent, bg=BG)
        bar.grid(row=row, column=0, sticky=tk.EW, pady=(10, 0))
        self.status_dot = tk.Canvas(
            bar, width=10, height=10, bg=BG, highlightthickness=0
        )
        self.status_dot.pack(side=tk.LEFT, pady=2)
        self._dot = self.status_dot.create_oval(1, 1, 9, 9, fill=FG_DIM, outline="")
        self.status_var = tk.StringVar(value="Ready.")
        tk.Label(
            bar, textvariable=self.status_var, bg=BG, fg=FG_DIM, font=(FONT, 9)
        ).pack(side=tk.LEFT, padx=(8, 0))

    # ------------------------------------------------------------------
    # Helpers / callbacks
    # ------------------------------------------------------------------
    def _on_url_return(self, event):
        self._add_urls()
        return "break"

    def _pick_folder(self):
        path = filedialog.askdirectory(
            title="Choose download folder", initialdir=self.folder_var.get()
        )
        if path:
            self.folder_var.set(path)

    def _dec_concurrent(self):
        self._set_concurrent(self.manager.max_concurrent - 1)

    def _inc_concurrent(self):
        self._set_concurrent(self.manager.max_concurrent + 1)

    def _set_concurrent(self, value):
        value = max(1, min(8, value))
        self.manager.max_concurrent = value
        self.concurrent_label.config(text=str(value))
        self._update_status_bar()

    def _add_urls(self):
        folder = self.folder_var.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showwarning(
                "Bad Folder", "Please select a valid save folder first."
            )
            return

        raw = self.url_text.get("1.0", tk.END)
        urls = [u.strip() for u in raw.split() if u.strip()]
        if not urls:
            messagebox.showwarning("Missing URL", "Please enter at least one URL.")
            return

        added = 0
        for url in urls:
            if not (url.startswith("http://") or url.startswith("https://")):
                continue
            filename = self._extract_filename(url) or "download"
            output_path = self._unique_output_path(folder, filename)
            task = DownloadTask(url, folder, output_path)
            self.manager.add(task)

            iid = self.tree.insert(
                "", tk.END, values=self._row_values(task),
                tags=self._tags_for(task),
            )
            task.item_id = iid
            self.tasks_by_iid[iid] = task
            added += 1

        if added == 0:
            messagebox.showwarning(
                "No valid URLs", "URLs must start with http:// or https://"
            )
            return

        self.url_text.delete("1.0", tk.END)
        self._refresh_all_rows()

    def _remove_selected(self):
        for iid in list(self.tree.selection()):
            task = self.tasks_by_iid.get(iid)
            if task is None:
                continue
            if task.state in ("downloading", "queued"):
                task.cancel_flag = True
                task.status = "Cancelling..."
                self._refresh_row(task)
                with self.manager.lock:
                    if task in self.manager.pending:
                        self.manager.pending.remove(task)
                if task not in self.manager.active:
                    task.state = "cancelled"
                    task.status = "Cancelled"
            else:
                with self.manager.lock:
                    if task in self.manager.tasks:
                        self.manager.tasks.remove(task)
                self.tasks_by_iid.pop(iid, None)
                try:
                    self.tree.delete(iid)
                except Exception:
                    pass
        self._refresh_all_rows()

    def _move_selected(self, delta):
        """Move selected rows up (-1) or down (+1) in the queue."""
        selection = list(self.tree.selection())
        if not selection:
            return
        selected = [
            self.tasks_by_iid[i] for i in selection if i in self.tasks_by_iid
        ]
        tasks = self.manager.tasks

        if delta < 0:
            for task in sorted(selected, key=tasks.index):
                i = tasks.index(task)
                if i > 0 and tasks[i - 1] not in selected:
                    tasks[i - 1], tasks[i] = tasks[i], tasks[i - 1]
        else:
            for task in sorted(selected, key=tasks.index, reverse=True):
                i = tasks.index(task)
                if i < len(tasks) - 1 and tasks[i + 1] not in selected:
                    tasks[i + 1], tasks[i] = tasks[i], tasks[i + 1]

        with self.manager.lock:
            self.manager._reorder_pending()
        self._sync_tree_order()
        self._refresh_all_rows()
        self.tree.selection_set(selection)

    def _set_priority(self, value):
        """Set priority on all selected rows (0=High, 1=Normal, 2=Low)."""
        selection = list(self.tree.selection())
        if not selection:
            return
        for iid in selection:
            task = self.tasks_by_iid.get(iid)
            if task is not None:
                task.priority = value
                self._refresh_row(task)
        with self.manager.lock:
            self.manager._reorder_pending()
        self._update_priority_controls()

    def _update_priority_controls(self, event=None):
        selection = list(self.tree.selection())
        selected = [
            self.tasks_by_iid[i] for i in selection if i in self.tasks_by_iid
        ]
        prios = {t.priority for t in selected}
        active = prios.pop() if len(prios) == 1 else None
        for value, btn in self.priority_buttons.items():
            btn.set_selected(value == active)

    def _sync_tree_order(self):
        """Reorder treeview rows to match the queue/list order."""
        for index, task in enumerate(self.manager.tasks):
            if task.item_id is None:
                continue
            try:
                if self.tree.exists(task.item_id):
                    self.tree.move(task.item_id, "", index)
            except Exception:
                pass

    def _on_close(self):
        self.manager.cancel_all()
        self.root.destroy()

    def _on_batch_done(self):
        self._update_status_bar()

    # ------------------------------------------------------------------
    # Row rendering (main thread only)
    # ------------------------------------------------------------------
    def _tags_for(self, task):
        try:
            index = self.manager.tasks.index(task)
        except ValueError:
            index = 0
        return (task.state, "band1" if index % 2 else "band0")

    def _row_values(self, task):
        if task.total > 0:
            size = (
                f"{self._human_size(task.downloaded)} / "
                f"{self._human_size(task.total)}"
            )
            pct = min(100.0, (task.downloaded / task.total) * 100)
            progress = f"{self._bar(pct)} {pct:3.0f}%"
        else:
            size = self._human_size(task.downloaded) if task.downloaded else "-"
            progress = "—"

        if task.state == "downloading" and task.speed > 0:
            speed = f"{self._human_size(task.speed)}/s"
        else:
            speed = ""

        name = task.filename or task.url
        priority = PRIORITY_LABELS.get(task.priority, "Normal")
        return (priority, name, size, progress, speed, task.status)

    def _refresh_row(self, task):
        if task.item_id is None:
            return
        try:
            if not self.tree.exists(task.item_id):
                return
        except Exception:
            return
        try:
            self.tree.item(
                task.item_id,
                values=self._row_values(task),
                tags=self._tags_for(task),
            )
        except Exception:
            pass
        self._update_status_bar()

    def _refresh_all_rows(self):
        for task in self.manager.tasks:
            self._refresh_row(task)
        self._update_status_bar()

    def _update_status_bar(self):
        counts = {"queued": 0, "downloading": 0, "complete": 0, "failed": 0,
                  "cancelled": 0}
        for t in self.manager.tasks:
            counts[t.state] = counts.get(t.state, 0) + 1
        parts = []
        if counts["downloading"]:
            parts.append(
                f"{counts['downloading']}/{self.manager.max_concurrent} active"
            )
        if counts["queued"]:
            parts.append(f"{counts['queued']} queued")
        if counts["complete"]:
            parts.append(f"{counts['complete']} complete")
        if counts["failed"]:
            parts.append(f"{counts['failed']} failed")
        if counts["cancelled"]:
            parts.append(f"{counts['cancelled']} cancelled")
        self.status_var.set("  ·  ".join(parts) if parts else "Ready.")

        if counts["failed"]:
            color = RED
        elif counts["downloading"]:
            color = ACCENT
        elif counts["complete"] and not counts["queued"]:
            color = GREEN
        else:
            color = FG_DIM
        try:
            self.status_dot.itemconfig(self._dot, fill=color)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Naming helpers
    # ------------------------------------------------------------------
    def _unique_output_path(self, folder, filename, exclude=None):
        base, ext = os.path.splitext(filename)
        existing = {
            os.path.normcase(t.output_path)
            for t in self.manager.tasks
            if t is not exclude
        }
        candidate = filename
        n = 1
        while os.path.normcase(os.path.join(folder, candidate)) in existing:
            candidate = f"{base} ({n}){ext}"
            n += 1
        return os.path.join(folder, candidate)

    @staticmethod
    def _extract_filename(url):
        from urllib.parse import urlparse, unquote

        name = os.path.basename(urlparse(url).path)
        name = unquote(name)
        if "?" in name:
            name = name.split("?")[0]
        return name.strip() or None

    @staticmethod
    def _bar(pct, width=16):
        filled = int(round(width * pct / 100))
        filled = max(0, min(width, filled))
        return "█" * filled + "░" * (width - filled)

    @staticmethod
    def _human_size(num_bytes):
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if abs(num_bytes) < 1024:
                return f"{num_bytes:.1f} {unit}"
            num_bytes /= 1024
        return f"{num_bytes:.1f} PB"

    @staticmethod
    def _fmt_time(seconds):
        if seconds < 60:
            return f"{seconds:.0f}s"
        if seconds < 3600:
            return f"{seconds // 60:.0f}m {seconds % 60:.0f}s"
        h = seconds // 3600
        m = (seconds % 3600) // 60
        return f"{h:.0f}h {m:.0f}m"


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------
def main():
    root = tk.Tk()
    app = DownloaderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
