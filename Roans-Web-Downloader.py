#!/usr/bin/env python3
"""
AWESOME DOWNLOADER - the downloader, but it thinks it's a video game.

Same core engine as Roan's Web Downloader (concurrent downloads, resume,
auto-retry, priorities) wrapped in neon arcade animations, dubstep-ish
chiptune, particle effects, screen shake, score/combo and easter eggs.

Style inspired by "AwesomeCalculator" by deaen (video game calculator).

Run with: python Roans-Web-Downloader.py
No build required, zero external dependencies (stdlib only).
"""

import os
import math
import time
import random
import struct
import threading
import urllib.request
import urllib.error
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox

# ----------------------------------------------------------------------
# Style constants
# ----------------------------------------------------------------------
FONT = "Consolas"
TITLE_FONT = "Impact"

BG = "#05010f"
DARK = "#0b0620"
CARD = "#10082a"
FG = "#e8e8ff"
FG_DIM = "#7d7aa8"
BORDER = "#2a1b5e"

NEON_PINK = "#ff2fd6"
NEON_CYAN = "#22e6ff"
NEON_GREEN = "#39ff88"
NEON_YELLOW = "#ffe23a"
NEON_PURPLE = "#a24bff"
NEON_RED = "#ff3355"
NEON_ORANGE = "#ff8a2b"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
PRIORITY_LABELS = {0: "HIGH", 1: "NORMAL", 2: "LOW"}

CARD_H = 58
CARD_GAP = 8
QUEUE_TOP = 252
QUEUE_BOTTOM = 610

START_MUTED = False


# ----------------------------------------------------------------------
# Audio (pure stdlib synth -> WAV in memory -> winsound)
# ----------------------------------------------------------------------
RATE = 22050


def _wav_bytes(samples):
    frames = bytearray()
    for s in samples:
        v = int(max(-1.0, min(1.0, s)) * 32767)
        frames += struct.pack("<h", v)
    return (
        b"RIFF" + struct.pack("<I", 36 + len(frames)) + b"WAVE"
        + b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, RATE, RATE * 2, 2, 16)
        + b"data" + struct.pack("<I", len(frames)) + bytes(frames)
    )


def _add_tone(buf, start, dur, freq, amp, wave="square", attack=0.005):
    s0 = int(start * RATE)
    s1 = min(len(buf), int((start + dur) * RATE))
    for i in range(s0, s1):
        t = (i - s0) / RATE
        phase = freq * t
        if wave == "square":
            v = 1.0 if (phase % 1.0) < 0.5 else -1.0
        elif wave == "saw":
            v = 2.0 * (phase % 1.0) - 1.0
        else:
            v = math.sin(2 * math.pi * phase)
        env = min(1.0, t / attack) * max(0.0, 1.0 - t / dur)
        buf[i] += v * amp * env


def _add_kick(buf, start):
    dur = 0.18
    s0 = int(start * RATE)
    s1 = min(len(buf), int((start + dur) * RATE))
    for i in range(s0, s1):
        t = (i - s0) / RATE
        f = 130 * math.exp(-t * 22) + 45
        env = math.exp(-t * 12)
        buf[i] += math.sin(2 * math.pi * f * t) * 0.85 * env


def _add_noise(buf, start, dur, amp):
    s0 = int(start * RATE)
    s1 = min(len(buf), int((start + dur) * RATE))
    for i in range(s0, s1):
        t = (i - s0) / RATE
        env = max(0.0, 1.0 - t / dur)
        buf[i] += (random.random() * 2 - 1) * amp * env


def build_music():
    bpm = 150
    beat = 60.0 / bpm
    beats = 8
    length = beat * beats
    n = int(length * RATE)
    buf = [0.0] * n

    bass = [110.0, 110.0, 87.31, 87.31, 130.81, 130.81, 98.0, 98.0]
    lead = [440.0, 523.25, 659.25, 523.25, 440.0, 392.0, 440.0, 523.25]

    for b in range(beats):
        t = b * beat
        _add_kick(buf, t)
        if b % 2 == 1:
            _add_noise(buf, t, 0.12, 0.28)
        else:
            _add_noise(buf, t + beat / 2, 0.05, 0.12)
        _add_tone(buf, t, beat * 0.95, bass[b], 0.32, "saw")
        # wobble lead in 8th notes
        for k in range(2):
            t2 = t + k * beat / 2
            f = lead[b] * (1.0 if k == 0 else 0.5)
            _add_tone(buf, t2, beat / 2 * 0.9, f, 0.18, "square")
        if b == 7:
            _add_tone(buf, t + beat / 2, beat / 2, 880.0, 0.2, "square")

    return _wav_bytes(buf)


def build_sfx(kind):
    if kind == "click":
        buf = [0.0] * int(0.06 * RATE)
        _add_tone(buf, 0, 0.06, 880, 0.5, "square")
    elif kind == "add":
        buf = [0.0] * int(0.18 * RATE)
        _add_tone(buf, 0.0, 0.08, 660, 0.4, "square")
        _add_tone(buf, 0.08, 0.10, 990, 0.4, "square")
    elif kind == "error":
        buf = [0.0] * int(0.30 * RATE)
        _add_tone(buf, 0.0, 0.28, 130, 0.5, "saw")
        _add_tone(buf, 0.0, 0.28, 98, 0.4, "square")
    elif kind == "complete":
        buf = [0.0] * int(0.55 * RATE)
        for i, f in enumerate((523.25, 659.25, 783.99, 1046.5)):
            _add_tone(buf, i * 0.10, 0.30, f, 0.38, "square")
    elif kind == "jumpscare":
        buf = [0.0] * int(0.7 * RATE)
        _add_noise(buf, 0, 0.7, 0.5)
        _add_tone(buf, 0, 0.7, 55, 0.6, "saw")
        _add_tone(buf, 0, 0.7, 58, 0.5, "square")
    else:
        buf = [0.0] * int(0.05 * RATE)
        _add_tone(buf, 0, 0.05, 440, 0.3, "square")
    return _wav_bytes(buf)


class Audio:
    """Background music loop + sound effects, best-effort on Windows."""

    def __init__(self):
        self.enabled = True
        self.playing = False
        self._winsound = None
        self._music = None
        self._sfx = {}
        try:
            import winsound
            self._winsound = winsound
        except Exception:
            self._winsound = None
        if self._winsound is not None:
            try:
                self._music = build_music()
                for name in ("click", "add", "error", "complete", "jumpscare"):
                    self._sfx[name] = build_sfx(name)
            except Exception:
                self._music = None

    def start_music(self):
        if self._winsound is None or self._music is None:
            return
        try:
            self._winsound.PlaySound(
                self._music,
                self._winsound.SND_MEMORY
                | self._winsound.SND_ASYNC
                | self._winsound.SND_LOOP,
            )
            self.playing = True
        except Exception:
            pass

    def stop_music(self):
        if self._winsound is None:
            return
        try:
            self._winsound.PlaySound(None, 0)
        except Exception:
            pass
        self.playing = False

    def toggle_music(self):
        if self.playing:
            self.stop_music()
        else:
            self.enabled = True
            self.start_music()
        return self.playing

    def sfx(self, name):
        if not self.enabled or self._winsound is None:
            return
        data = self._sfx.get(name)
        if data is None:
            return
        try:
            self._winsound.PlaySound(
                data, self._winsound.SND_MEMORY | self._winsound.SND_ASYNC
            )
        except Exception:
            pass


# ----------------------------------------------------------------------
# Core data model + download manager (same engine as the "boring" build)
# ----------------------------------------------------------------------
class DownloadTask:
    def __init__(self, url, folder, output_path):
        self.url = url
        self.folder = folder
        self.output_path = output_path
        self.filename = os.path.basename(output_path)
        self.state = "queued"
        self.status = "Queued"
        self.downloaded = 0
        self.total = 0
        self.speed = 0
        self.eta = 0
        self.cancel_flag = False
        self.retry_count = 0
        self.probed_name = False
        self.item_id = None
        self.priority = 1


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
        order = {id(t): i for i, t in enumerate(self.tasks)}
        self.pending.sort(key=lambda t: order.get(id(t), 0))

    def _forget(self, iid):
        self.app._delete_row(iid)

    def _scheduler(self):
        while True:
            with self.lock:
                while self.pending and len(self.active) < self.max_concurrent:
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

    def _download_task(self, task):
        if task.state == "cancelled":
            return
        task.state = "downloading"
        task.status = "Starting..."
        task.speed = 0
        task.eta = 0

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
                        self.app.root.after(0, lambda t=task: self.app._on_complete(t))
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
                    self.app.root.after(0, lambda: self.app.audio.sfx("error"))
                    return
                wait = min(2 ** (task.retry_count - 1), 60)
                task.status = f"Retry {task.retry_count}/{self.max_retries} in {wait}s"
                for _ in range(int(wait * 10)):
                    if task.cancel_flag:
                        break
                    time.sleep(0.1)

        if task.cancel_flag:
            task.state = "cancelled"
            task.status = "Cancelled"
            task.speed = 0

    def _do_download(self, task):
        url = task.url
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

            block_size = 1024 * 64
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

                if task.cancel_flag:
                    return (False, True)

                if total > 0 and downloaded < total:
                    return (False, True)

        return (True, False)

    @staticmethod
    def _name_from_headers(headers):
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
# Neon arcade button drawn on the stage canvas
# ----------------------------------------------------------------------
class ArcadeButton:
    def __init__(self, app, x, y, w, h, text, command, color=NEON_CYAN,
                 font_size=11, accent=False):
        self.app = app
        self.x, self.y, self.w, self.h = x, y, w, h
        self.text = text
        self.command = command
        self.color = color
        self.accent = accent
        self.disabled = False
        self.hover = False
        c = app.stage
        self.tag = f"btn{id(self)}"
        fill = color if accent else DARK
        self.body = c.create_rectangle(
            x, y, x + w, y + h, outline=color, width=3, fill=fill,
            tags=("ui", self.tag),
        )
        self.label = c.create_text(
            x + w / 2, y + h / 2, text=text, fill=(BG if accent else color),
            font=(FONT, font_size, "bold"), tags=("ui", self.tag),
        )
        self.glow = c.create_rectangle(
            x - 4, y - 4, x + w + 4, y + h + 4, outline=color, width=1,
            dash=(2, 6), tags=("ui", self.tag),
        )

    def contains(self, px, py):
        return self.x <= px <= self.x + self.w and self.y <= py <= self.y + self.h

    def set_text(self, text):
        self.app.stage.itemconfig(self.label, text=text)

    def press(self):
        if self.disabled:
            return
        c = self.app.stage
        c.itemconfig(self.body, fill=self.color)
        c.itemconfig(self.label, fill=BG)
        self.app.audio.sfx("click")

    def release(self):
        c = self.app.stage
        c.itemconfig(self.body, fill=(self.color if self.accent else DARK))
        c.itemconfig(self.label, fill=(BG if self.accent else self.color))

    def invoke(self):
        if not self.disabled and self.command:
            self.command()


# ----------------------------------------------------------------------
# The game
# ----------------------------------------------------------------------
class AwesomeDownloader:
    def __init__(self, root):
        self.root = root
        self.root.title("AWESOME DOWNLOADER")
        self.root.geometry("1024x720+80+40")
        self.root.resizable(False, False)
        self.root.configure(bg=BG)

        self.manager = DownloadManager(self)
        self.tasks_by_iid = {}
        self._next_iid = 0
        self.selected = set()
        self.scroll = 0
        self.popups = []
        self.particles = []
        self.buttons = []
        self.card_rects = []
        self.title_hue = 0.0
        self.shake_until = 0.0
        self._shake_active = False
        self._shake_base = (80, 40)
        self.scare_until = 0.0
        self.cantaloupe_until = 0.0
        self.combo = 0
        self.score = 0
        self.last_event = time.time()
        self.audio = Audio() if not START_MUTED else _muted_audio()

        self.stars = [
            [random.uniform(0, 1024), random.uniform(0, 720),
             random.uniform(0.3, 1.6), random.choice((NEON_CYAN, NEON_PINK, FG))]
            for _ in range(70)
        ]

        self.stage = tk.Canvas(
            self.root, width=1024, height=720, bg=BG, highlightthickness=0
        )
        self.stage.pack(fill=tk.BOTH, expand=True)

        self._build()
        self.audio.start_music()
        self._bind_events()
        self._tick()

    # -- construction --------------------------------------------------
    def _build(self):
        c = self.stage
        self._build_background()

        # URL entry (embedded widget)
        self.url_var = tk.StringVar()
        self.url_entry = tk.Entry(
            c, textvariable=self.url_var, bg=DARK, fg=NEON_CYAN,
            insertbackground=NEON_PINK, relief="flat", font=(FONT, 12),
            highlightthickness=0,
        )
        c.create_window(38, 150, window=self.url_entry, anchor="nw",
                        width=700, height=30, tags=("widgets",))
        self.url_entry.bind("<Return>", lambda e: self._add_urls())

        # Folder entry (embedded widget)
        self.folder_var = tk.StringVar(value=str(Path.home() / "Downloads"))
        self.folder_entry = tk.Entry(
            c, textvariable=self.folder_var, bg=DARK, fg=NEON_GREEN,
            insertbackground=NEON_PINK, relief="flat", font=(FONT, 10),
            highlightthickness=0,
        )
        c.create_window(130, 628, window=self.folder_entry, anchor="nw",
                        width=470, height=28, tags=("widgets",))

        # Buttons
        self.buttons = [
            ArcadeButton(self, 776, 140, 110, 48, "ADD!",
                         self._add_urls, NEON_PINK, 14, accent=True),
            ArcadeButton(self, 896, 140, 112, 48, "MUSIC ON",
                         self._toggle_music, NEON_YELLOW, 10),
            ArcadeButton(self, 614, 626, 110, 32, "BROWSE",
                         self._pick_folder, NEON_GREEN, 10),
        ]
        # queue toolbar
        self.buttons += [
            ArcadeButton(self, 600, 204, 44, 28, "UP",
                         lambda: self._move_selected(-1), NEON_CYAN, 10),
            ArcadeButton(self, 650, 204, 54, 28, "DOWN",
                         lambda: self._move_selected(1), NEON_CYAN, 10),
            ArcadeButton(self, 782, 204, 56, 28, "HIGH",
                         lambda: self._set_priority(0), NEON_RED, 10),
            ArcadeButton(self, 844, 204, 64, 28, "NORM",
                         lambda: self._set_priority(1), NEON_YELLOW, 10),
            ArcadeButton(self, 914, 204, 54, 28, "LOW",
                         lambda: self._set_priority(2), NEON_GREEN, 10),
        ]
        # concurrent stepper
        self.minus_btn = ArcadeButton(self, 150, 670, 34, 30, "-",
                                      self._dec_concurrent, NEON_PURPLE, 14)
        self.plus_btn = ArcadeButton(self, 216, 670, 34, 30, "+",
                                     self._inc_concurrent, NEON_PURPLE, 14)
        self.buttons += [self.minus_btn, self.plus_btn]
        # bottom actions
        self.buttons += [
            ArcadeButton(self, 300, 670, 100, 30, "REMOVE",
                         self._remove_selected, NEON_CYAN, 10),
            ArcadeButton(self, 410, 670, 130, 30, "CLEAR DONE",
                         self.manager.clear_finished, NEON_CYAN, 10),
            ArcadeButton(self, 550, 670, 120, 30, "CANCEL ALL",
                         self.manager.cancel_all, NEON_ORANGE, 10),
            ArcadeButton(self, 790, 664, 214, 42, "START!",
                         self.manager.start_all, NEON_GREEN, 16, accent=True),
        ]
        self.music_btn = self.buttons[1]

    def _build_background(self):
        """Static background items drawn once, animated in place."""
        c = self.stage
        self.star_items = [
            c.create_oval(s[0], s[1], s[0] + 2, s[1] + 2, fill=s[3],
                          outline="", tags="bg")
            for s in self.stars
        ]
        self.grid_spacing = 34
        self.grid_lines = [
            c.create_line(0, 0, 1024, 0, fill=NEON_PURPLE, tags="bg")
            for _ in range(24)
        ]
        for x in range(0, 1025, 64):
            c.create_line(512, 430, x, 720, fill="#2b1560", tags="bg")
        self.title_item = c.create_text(
            512, 58, text="AWESOME DOWNLOADER", fill=NEON_PINK,
            font=(TITLE_FONT, 40, "bold"), tags="bg",
        )
        c.create_text(512, 98, text="DOWNLOAD... LIKE A BOSS!!!!!",
                      fill=NEON_CYAN, font=(FONT, 12, "bold"), tags="bg")
        c.create_rectangle(30, 138, 762, 190, outline=NEON_PURPLE, width=2,
                           tags="bg")
        c.create_text(38, 128, text="URL", anchor="w", fill=FG_DIM,
                      font=(FONT, 9, "bold"), tags="bg")
        c.create_rectangle(24, 618, 1004, 712, outline=NEON_PURPLE, width=2,
                           tags="bg")
        c.create_text(34, 642, text="SAVE TO", anchor="w", fill=FG_DIM,
                      font=(FONT, 9, "bold"), tags="bg")
        c.create_text(34, 685, text="CONCURRENT", anchor="w", fill=FG_DIM,
                      font=(FONT, 9, "bold"), tags="bg")
        self.concurrent_item = c.create_text(
            200, 685, text=str(self.manager.max_concurrent), fill=NEON_PURPLE,
            font=(FONT, 13, "bold"), tags="bg",
        )
        c.create_text(24, 216, text="DOWNLOAD QUEUE", anchor="w",
                      fill=NEON_CYAN, font=(FONT, 11, "bold"), tags="bg")
        c.create_text(716, 218, text="PRIORITY", anchor="w", fill=FG_DIM,
                      font=(FONT, 9, "bold"), tags="bg")

    def _bind_events(self):
        self.stage.bind("<Button-1>", self._on_press)
        self.stage.bind("<ButtonRelease-1>", self._on_release)
        self.stage.bind("<Motion>", self._on_motion)
        self.stage.bind("<MouseWheel>", self._on_wheel)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # -- input ---------------------------------------------------------
    def _pick_folder(self):
        path = filedialog.askdirectory(
            title="Choose download folder", initialdir=self.folder_var.get()
        )
        if path:
            self.folder_var.set(path)

    def _add_urls(self):
        folder = self.folder_var.get().strip()
        if not folder or not os.path.isdir(folder):
            self.audio.sfx("error")
            self._popup(512, 360, "PICK A REAL FOLDER!", NEON_RED)
            return
        raw = self.url_var.get()
        if "9+10" in raw:
            self._popup(512, 360, "9 + 10 = 21", NEON_YELLOW)
            self.score += 21
        urls = [u.strip() for u in raw.replace(",", " ").split() if u.strip()]
        if not urls:
            self.audio.sfx("error")
            self._popup(512, 360, "WHERE'S THE URL??", NEON_RED)
            return
        added = 0
        for url in urls:
            if not (url.startswith("http://") or url.startswith("https://")):
                continue
            filename = self._extract_filename(url) or "download"
            output_path = self._unique_output_path(folder, filename)
            task = DownloadTask(url, folder, output_path)
            task.item_id = self._next_iid
            self._next_iid += 1
            self.manager.add(task)
            self.tasks_by_iid[task.item_id] = task
            self._popup(512, 360, "ADDED TO THE QUEUE!", NEON_CYAN)
            added += 1
        if added:
            self.url_var.set("")
            self.audio.sfx("add")
            self.score += added * 10
        else:
            self.audio.sfx("error")
            self._popup(512, 360, "http:// OR https:// ONLY!", NEON_RED)

    def _toggle_music(self):
        playing = self.audio.toggle_music()
        self.music_btn.set_text("MUSIC ON" if playing else "MUSIC OFF")

    def _dec_concurrent(self):
        self._set_concurrent(self.manager.max_concurrent - 1)

    def _inc_concurrent(self):
        self._set_concurrent(self.manager.max_concurrent + 1)

    def _set_concurrent(self, value):
        self.manager.max_concurrent = max(1, min(8, value))
        self.stage.itemconfig(
            self.concurrent_item, text=str(self.manager.max_concurrent)
        )

    def _on_wheel(self, event):
        total = len(self.manager.tasks) * (CARD_H + CARD_GAP)
        view = QUEUE_BOTTOM - QUEUE_TOP
        self.scroll = max(0, min(max(0, total - view), self.scroll - event.delta // 2))

    def _on_press(self, event):
        x, y = event.x, event.y
        for b in self.buttons:
            if b.contains(x, y):
                b.press()
                return
        for x1, y1, x2, y2, task in reversed(self.card_rects):
            if x1 <= x <= x2 and y1 <= y <= y2:
                if task.item_id in self.selected:
                    self.selected.discard(task.item_id)
                else:
                    self.selected.add(task.item_id)

    def _on_release(self, event):
        for b in self.buttons:
            if b.contains(event.x, event.y):
                b.release()
                b.invoke()
                return
            b.release()

    def _on_motion(self, event):
        for b in self.buttons:
            b.hover = b.contains(event.x, event.y)

    # -- selection operations -----------------------------------------
    def _selected_tasks(self):
        return [t for t in self.manager.tasks if t.item_id in self.selected]

    def _remove_selected(self):
        for task in self._selected_tasks():
            if task.state in ("downloading", "queued"):
                task.cancel_flag = True
                task.status = "Cancelling..."
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
                self.tasks_by_iid.pop(task.item_id, None)
        self.selected.clear()
        self.audio.sfx("click")

    def _move_selected(self, delta):
        selected = self._selected_tasks()
        if not selected:
            return
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
        self.audio.sfx("click")

    def _set_priority(self, value):
        for task in self._selected_tasks():
            task.priority = value
        with self.manager.lock:
            self.manager._reorder_pending()
        self.audio.sfx("click")

    def _delete_row(self, iid):
        self.tasks_by_iid.pop(iid, None)
        self.selected.discard(iid)

    # -- engine callbacks (mostly no-ops: we render every frame) -------
    def _refresh_row(self, task):
        pass

    def _refresh_all_rows(self):
        pass

    def _update_status_bar(self):
        pass

    def _on_batch_done(self):
        self._popup(512, 300, "ALL DONE! AWESOME!", NEON_GREEN)

    def _on_complete(self, task):
        self.combo += 1
        mb = max(1, task.total // (1024 * 1024))
        gained = mb * 5 * self.combo
        self.score += gained
        self.audio.sfx("complete")
        self._popup(512, 300 + random.randint(-30, 30),
                    f"DOWNLOADED! +{gained}  COMBO x{self.combo}", NEON_GREEN)
        self._burst(random.randint(200, 800), random.randint(300, 550))
        roll = random.random()
        if roll < 0.02:
            self._jumpscare()
        elif roll < 0.07:
            self.cantaloupe_until = time.time() + 4.0
            self._popup(512, 400, "🍈 CANTALOUPE OBTAINED! +1000", NEON_ORANGE)
            self.score += 1000

    def _jumpscare(self):
        self.scare_until = time.time() + 0.8
        self.shake_until = time.time() + 0.6
        self._shake_base = (self.root.winfo_x(), self.root.winfo_y())
        self._shake_active = True
        self.combo = 0
        self.audio.sfx("jumpscare")

    def _burst(self, x, y):
        for _ in range(26):
            ang = random.uniform(0, math.tau)
            spd = random.uniform(2, 7)
            self.particles.append({
                "x": x, "y": y,
                "vx": math.cos(ang) * spd, "vy": math.sin(ang) * spd - 2,
                "life": random.uniform(0.6, 1.2),
                "color": random.choice((NEON_PINK, NEON_CYAN, NEON_GREEN,
                                        NEON_YELLOW)),
            })

    def _popup(self, x, y, text, color):
        self.popups.append({
            "x": x, "y": y, "text": text, "color": color, "life": 1.6,
        })

    # -- rendering loop ------------------------------------------------
    def _tick(self):
        now = time.time()
        self._draw_background(now)
        self._draw_hud(now)
        self._draw_cards(now)
        self._draw_popups(now)
        self._draw_particles(now)
        self._draw_scare(now)
        self._draw_cantaloupe(now)
        self._apply_shake(now)
        c = self.stage
        c.tag_raise("cards")
        c.tag_raise("ui")
        c.tag_raise("popups")
        c.tag_raise("scare")
        c.tag_raise("widgets")
        self.root.after(16, self._tick)

    def _draw_background(self, now):
        c = self.stage
        # starfield (move existing items, no flicker)
        for i, s in enumerate(self.stars):
            s[1] += s[2]
            if s[1] > 720:
                s[1] = 0
                s[0] = random.uniform(0, 1024)
            c.coords(self.star_items[i], s[0], s[1], s[0] + 2, s[1] + 2)
        # smooth time-based scrolling horizon grid (updates coords in place)
        offset = (now * 90) % self.grid_spacing
        for i, item in enumerate(self.grid_lines):
            y = 720 - i * self.grid_spacing + offset
            c.coords(item, 0, y, 1024, y)
        # color-cycling title
        self.title_hue = (self.title_hue + 2.5) % 360
        c.itemconfig(self.title_item, fill=self._hsv(self.title_hue, 1.0, 1.0))

    def _draw_hud(self, now):
        c = self.stage
        c.delete("hud")
        active = sum(1 for t in self.manager.tasks if t.state == "downloading")
        queued = sum(1 for t in self.manager.tasks if t.state == "queued")
        c.create_text(1000, 26, text=f"SCORE {self.score}", anchor="ne",
                      fill=NEON_YELLOW, font=(FONT, 14, "bold"), tags="hud")
        c.create_text(1000, 50, text=f"COMBO x{self.combo}", anchor="ne",
                      fill=NEON_PINK, font=(FONT, 11, "bold"), tags="hud")
        c.create_text(1000, 72,
                      text=f"{active}/{self.manager.max_concurrent} ACTIVE  "
                           f"{queued} QUEUED",
                      anchor="ne", fill=FG_DIM, font=(FONT, 9), tags="hud")

    def _draw_cards(self, now):
        c = self.stage
        c.delete("cards")
        self.card_rects = []
        y = QUEUE_TOP - self.scroll
        for task in self.manager.tasks:
            if y + CARD_H >= QUEUE_TOP - 20 and y <= QUEUE_BOTTOM + 20:
                self._draw_card(task, 20, y, 984, CARD_H, now)
                self.card_rects.append((20, y, 1004, y + CARD_H, task))
            y += CARD_H + CARD_GAP

    def _draw_card(self, task, x, y, w, h, now):
        c = self.stage
        color = self._state_color(task.state)
        selected = task.item_id in self.selected
        outline = NEON_YELLOW if selected else color
        c.create_rectangle(x, y, x + w, y + h, outline=outline,
                           width=3 if selected else 2, fill=CARD, tags="cards")
        c.create_text(x + 14, y + 18, text=task.filename, anchor="w",
                      fill=FG, font=(FONT, 11, "bold"), tags="cards")
        info = (
            f"{PRIORITY_LABELS.get(task.priority, 'NORMAL')}  |  "
            f"{self._human_size(task.downloaded)} / "
            f"{self._human_size(task.total) if task.total else '??'}  |  "
            f"{self._human_size(task.speed)}/s  |  {task.status}"
        )
        c.create_text(x + 14, y + 38, text=info, anchor="w", fill=FG_DIM,
                      font=(FONT, 9), tags="cards")
        bx1, by1, bx2, by2 = x + 14, y + h - 13, x + w - 14, y + h - 5
        c.create_rectangle(bx1, by1, bx2, by2, outline=BORDER, fill=DARK,
                           tags="cards")
        if task.total > 0:
            pct = max(0.0, min(1.0, task.downloaded / task.total))
        elif task.state in ("complete",):
            pct = 1.0
        else:
            pct = 0.0
        fill_w = (bx2 - bx1) * pct
        if fill_w > 1:
            c.create_rectangle(bx1, by1, bx1 + fill_w, by2, outline="",
                               fill=color, tags="cards")
            if task.state == "downloading":
                sx = bx1 + ((now * 260) % max(1.0, fill_w))
                c.create_rectangle(sx, by1, min(sx + 14, bx1 + fill_w), by2,
                                   outline="", fill="#ffffff", tags="cards")
        c.create_text(bx2, y + 18, text=f"{int(pct * 100):3d}%", anchor="e",
                      fill=color, font=(FONT, 11, "bold"), tags="cards")

    def _draw_popups(self, now):
        c = self.stage
        c.delete("popups")
        alive = []
        for p in self.popups:
            p["life"] -= 0.033
            p["y"] -= 0.7
            if p["life"] > 0:
                alive.append(p)
                c.create_text(p["x"], p["y"], text=p["text"], fill=p["color"],
                              font=(FONT, 15, "bold"), tags="popups")
        self.popups = alive

    def _draw_particles(self, now):
        c = self.stage
        c.delete("particles")
        alive = []
        for p in self.particles:
            p["life"] -= 0.033
            if p["life"] <= 0:
                continue
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["vy"] += 0.25
            alive.append(p)
            c.create_oval(p["x"], p["y"], p["x"] + 4, p["y"] + 4, outline="",
                          fill=p["color"], tags="particles")
        self.particles = alive

    def _draw_scare(self, now):
        c = self.stage
        c.delete("scare")
        if now >= self.scare_until:
            return
        c.create_rectangle(0, 0, 1024, 720, outline="", fill="#3a0000",
                           tags="scare")
        jitter = random.randint(-8, 8)
        c.create_oval(300 + jitter, 200, 440, 340, fill="#ffffff",
                      outline=NEON_RED, width=4, tags="scare")
        c.create_oval(560 + jitter, 200, 700, 340, fill="#ffffff",
                      outline=NEON_RED, width=4, tags="scare")
        c.create_oval(350 + jitter, 250, 390, 290, fill="#000000", outline="",
                      tags="scare")
        c.create_oval(610 + jitter, 250, 650, 290, fill="#000000", outline="",
                      tags="scare")
        c.create_text(512, 460, text="R U N", fill=NEON_RED,
                      font=(TITLE_FONT, 60, "bold"), tags="scare")

    def _draw_cantaloupe(self, now):
        c = self.stage
        c.delete("melon")
        if now >= self.cantaloupe_until:
            return
        cx, cy = 512, 300
        c.create_oval(cx - 90, cy - 70, cx + 90, cy + 70, fill="#8fce4a",
                      outline="#4a7a1e", width=3, tags="melon")
        for dx in (-45, 0, 45):
            c.create_arc(cx + dx - 30, cy - 70, cx + dx + 30, cy + 70,
                         start=250, extent=40, style=tk.ARC, outline="#4a7a1e",
                         width=3, tags="melon")
        c.create_text(cx, cy + 110, text="🍈 CANTALOUPE! +1000",
                      fill=NEON_ORANGE, font=(FONT, 16, "bold"), tags="melon")

    def _apply_shake(self, now):
        # Only touch the window geometry while shaking, then restore once.
        # Otherwise the window is free to be moved by the user.
        if now < self.shake_until:
            bx, by = self._shake_base
            self.root.geometry(
                f"+{bx + random.randint(-6, 6)}+{by + random.randint(-6, 6)}"
            )
        elif self._shake_active:
            bx, by = self._shake_base
            self.root.geometry(f"+{bx}+{by}")
            self._shake_active = False

    # -- helpers -------------------------------------------------------
    @staticmethod
    def _hsv(h, s, v):
        i = int(h // 60) % 6
        f = (h / 60) - int(h / 60)
        p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
        rgb = [(v, t, p), (q, v, p), (p, v, t),
               (p, q, v), (t, p, v), (v, p, q)][i]
        return "#%02x%02x%02x" % tuple(int(c * 255) for c in rgb)

    @staticmethod
    def _state_color(state):
        return {
            "queued": NEON_CYAN,
            "downloading": NEON_PINK,
            "complete": NEON_GREEN,
            "failed": NEON_RED,
            "cancelled": NEON_ORANGE,
        }.get(state, FG)

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
    def _human_size(num_bytes):
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if abs(num_bytes) < 1024:
                return f"{num_bytes:.1f}{unit}"
            num_bytes /= 1024
        return f"{num_bytes:.1f}PB"

    @staticmethod
    def _fmt_time(seconds):
        if seconds < 60:
            return f"{seconds:.0f}s"
        if seconds < 3600:
            return f"{seconds // 60:.0f}m{seconds % 60:.0f}s"
        h = seconds // 3600
        m = (seconds % 3600) // 60
        return f"{h:.0f}h{m:.0f}m"

    def _on_close(self):
        self.manager.cancel_all()
        self.audio.stop_music()
        self.root.destroy()


def _muted_audio():
    class _Muted:
        enabled = False
        def start_music(self): pass
        def stop_music(self): pass
        def toggle_music(self): return False
        def sfx(self, name): pass
    return _Muted()


def main():
    root = tk.Tk()
    AwesomeDownloader(root)
    root.mainloop()


if __name__ == "__main__":
    main()
