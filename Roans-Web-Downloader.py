#!/usr/bin/env python3
"""
Roan's Web Downloader - Cross-platform downloader with resume & auto-retry.
Run with: python Roans-Web-Downloader.py
No build required. Works on Windows, macOS, and Linux.
"""

import os
import sys
import time
import threading
import urllib.request
import urllib.error
from pathlib import Path

# --- GUI (tkinter is built into Python) ---
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


class DownloaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Roan's Web Downloader")
        self.root.geometry("600x320")
        self.root.resizable(True, True)
        self.root.minsize(480, 280)

        # State
        self.downloading = False
        self.cancel_flag = False
        self.retry_count = 0
        self.max_retries = 10

        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        # Use a modern ttk theme if available
        style = ttk.Style(self.root)
        available = style.theme_names()
        for preferred in ("vista", "aqua", "clam", "alt", "default"):
            if preferred in available:
                style.theme_use(preferred)
                break

        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        # --- URL row ---
        ttk.Label(main, text="Download URL:").grid(
            row=0, column=0, sticky=tk.W, pady=(0, 2)
        )
        self.url_var = tk.StringVar()
        url_entry = ttk.Entry(main, textvariable=self.url_var)
        url_entry.grid(row=1, column=0, columnspan=2, sticky=tk.EW, pady=(0, 8))
        url_entry.focus()

        # --- Folder row ---
        ttk.Label(main, text="Save to folder:").grid(
            row=2, column=0, sticky=tk.W, pady=(0, 2)
        )
        folder_row = ttk.Frame(main)
        folder_row.grid(row=3, column=0, columnspan=2, sticky=tk.EW, pady=(0, 8))
        folder_row.columnconfigure(0, weight=1)

        self.folder_var = tk.StringVar(value=str(Path.home() / "Downloads"))
        ttk.Entry(folder_row, textvariable=self.folder_var).grid(
            row=0, column=0, sticky=tk.EW
        )
        ttk.Button(folder_row, text="Browse...", command=self._pick_folder).grid(
            row=0, column=1, padx=(6, 0)
        )

        # --- Progress bar ---
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            main, variable=self.progress_var, mode="determinate", maximum=100
        )
        self.progress_bar.grid(
            row=4, column=0, columnspan=2, sticky=tk.EW, pady=(4, 4)
        )

        # --- Status label ---
        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(main, textvariable=self.status_var).grid(
            row=5, column=0, columnspan=2, sticky=tk.W, pady=(0, 8)
        )

        # --- Buttons ---
        btn_row = ttk.Frame(main)
        btn_row.grid(row=6, column=0, columnspan=2, sticky=tk.E)
        self.download_btn = ttk.Button(
            btn_row, text="Download", command=self._start_download
        )
        self.download_btn.pack(side=tk.RIGHT, padx=(6, 0))
        self.cancel_btn = ttk.Button(
            btn_row, text="Cancel", command=self._cancel, state=tk.DISABLED
        )
        self.cancel_btn.pack(side=tk.RIGHT)

        # Configure grid weight so widgets stretch
        main.columnconfigure(0, weight=1)
        main.rowconfigure(7, weight=1)

        # Paste from clipboard helper
        self.root.bind("<Control-v>", lambda e: self._paste_url())

    def _pick_folder(self):
        path = filedialog.askdirectory(
            title="Choose download folder", initialdir=self.folder_var.get()
        )
        if path:
            self.folder_var.set(path)

    def _paste_url(self):
        try:
            clip = self.root.clipboard_get()
            if clip and not self.url_var.get():
                self.url_var.set(clip.strip())
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Download logic
    # ------------------------------------------------------------------
    def _start_download(self):
        url = self.url_var.get().strip()
        folder = self.folder_var.get().strip()

        if not url:
            messagebox.showwarning("Missing URL", "Please enter a download URL.")
            return
        if not folder:
            messagebox.showwarning("Missing Folder", "Please select a save folder.")
            return
        if not os.path.isdir(folder):
            messagebox.showwarning("Bad Folder", "Selected folder does not exist.")
            return

        # Guess filename from URL (fallback), then probe Content-Disposition
        filename = self._extract_filename(url)
        if not filename:
            filename = "download"
        # Try to get the real filename from the server's Content-Disposition header
        real_name = self._probe_filename(url)
        if real_name:
            filename = real_name
        self.output_path = os.path.join(folder, filename)

        self.downloading = True
        self.cancel_flag = False
        self.retry_count = 0
        self._set_ui_state(downloading=True)

        # Run download in background thread
        thread = threading.Thread(target=self._download_thread, args=(url,), daemon=True)
        thread.start()

    def _cancel(self):
        self.cancel_flag = True
        self.status_var.set("Cancelling...")

    def _set_ui_state(self, downloading):
        state = tk.DISABLED if downloading else tk.NORMAL
        self.download_btn.config(state=state)
        self.cancel_btn.config(
            state=tk.NORMAL if downloading else tk.DISABLED
        )

    # ------------------------------------------------------------------
    # Background download thread
    # ------------------------------------------------------------------
    def _download_thread(self, url):
        while self.retry_count <= self.max_retries and not self.cancel_flag:
            try:
                success, partial = self._do_download(url)
                if success:
                    if not self.cancel_flag:
                        self.root.after(0, self._on_success)
                    return
                # partial=True means connection dropped mid-stream;
                # fall through to retry (resume will pick up where it left off)
                if partial:
                    raise ConnectionError("Download interrupted")
            except Exception as e:
                if self.cancel_flag:
                    break
                self.retry_count += 1
                if self.retry_count > self.max_retries:
                    self.root.after(0, lambda msg=str(e): self._on_failure(msg))
                    return
                # Exponential backoff: 1s, 2s, 4s, 8s...
                wait = min(2 ** (self.retry_count - 1), 60)
                self._update_status(
                    f"Retry {self.retry_count}/{self.max_retries} in {wait}s "
                    f"({e})"
                )
                time.sleep(wait)

    def _do_download(self, url):
        """
        Download with resume support using urllib.

        Returns (success, partial):
          - (True, False)  → download finished cleanly
          - (False, True)  → connection dropped mid-stream (file kept for resume)
          - raises on hard errors (DNS, 404, etc.)
        """
        existing_size = 0
        if os.path.exists(self.output_path):
            existing_size = os.path.getsize(self.output_path)

        # --- Probe server: get total size + check Range support ---
        remote_size = 0
        accepts_ranges = False

        req = urllib.request.Request(url, method="HEAD")
        req.add_header(
            "User-Agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                remote_size = int(resp.headers.get("Content-Length", 0))
                accepts_ranges = (
                    resp.headers.get("Accept-Ranges", "").lower() == "bytes"
                )
        except (urllib.error.HTTPError, urllib.error.URLError):
            # Server hates HEAD — probe with a tiny Range GET instead
            probe_req = urllib.request.Request(url)
            probe_req.add_header(
                "User-Agent",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            )
            probe_req.add_header("Range", "bytes=0-0")
            try:
                with urllib.request.urlopen(probe_req, timeout=30) as resp:
                    content_range = resp.headers.get("Content-Range", "")
                    if content_range:
                        # "bytes 0-0/12345"
                        remote_size = int(content_range.split("/")[-1])
                        accepts_ranges = True
                    else:
                        remote_size = int(
                            resp.headers.get("Content-Length", 0)
                        )
            except Exception:
                # Server doesn't support Range at all — full download only
                remote_size = 0
                accepts_ranges = False

        # --- Determine whether to resume ---
        resume = (
            accepts_ranges
            and existing_size > 0
            and (remote_size == 0 or existing_size < remote_size)
        )

        # --- Build the GET request ---
        get_req = urllib.request.Request(url)
        get_req.add_header(
            "User-Agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        )
        if resume:
            get_req.add_header("Range", f"bytes={existing_size}-")
            self._update_status(f"Resuming from {self._human_size(existing_size)}...")

        with urllib.request.urlopen(get_req, timeout=30) as resp:
            # Determine what we're getting
            content_range = resp.headers.get("Content-Range", "")
            if content_range:
                # Server accepted Range; "bytes 100-199/200"
                total = int(content_range.split("/")[-1])
                downloaded = existing_size
                mode = "ab"
            else:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                mode = "wb"
                # If we asked to resume but server ignored Range, nuke existing file
                if resume and total > 0 and existing_size >= total:
                    # Already have complete file
                    return (True, False)

            block_size = 1024 * 64  # 64 KiB
            start_time = time.monotonic()
            last_progress = 0.0

            with open(self.output_path, mode) as f:
                while not self.cancel_flag:
                    try:
                        chunk = resp.read(block_size)
                    except (
                        ConnectionResetError,
                        TimeoutError,
                        OSError,
                        urllib.error.URLError,
                    ) as e:
                        # Socket dropped mid-read — partial download, can resume
                        return (False, True)

                    if not chunk:
                        # EOF from server
                        break

                    f.write(chunk)
                    downloaded += len(chunk)

                    # --- Progress update (throttled) ---
                    now = time.monotonic()
                    if now - last_progress > 0.25:
                        last_progress = now
                        elapsed = now - start_time
                        speed = downloaded / elapsed if elapsed > 0 else 0
                        if total > 0:
                            pct = (downloaded / total) * 100
                            eta = (total - downloaded) / speed if speed > 0 else 0
                            self.root.after(
                                0,
                                lambda p=pct, d=downloaded, t=total, s=speed, e=eta: self._update_progress(
                                    p, d, t, s, e
                                ),
                            )
                        else:
                            self.root.after(
                                0,
                                lambda d=downloaded, s=speed: self._update_progress_unknown(
                                    d, s
                                ),
                            )

                # --- Verify completeness ---
                if self.cancel_flag:
                    return (False, True)

                if total > 0 and downloaded < total:
                    # Premature EOF — connection dropped, file is incomplete
                    return (False, True)

        # Fully downloaded
        if not self.cancel_flag:
            self.root.after(0, lambda: self.progress_var.set(100))
        return (True, False)

    # ------------------------------------------------------------------
    # UI callbacks (run on main thread via .after)
    # ------------------------------------------------------------------
    def _update_status(self, text):
        self.root.after(0, lambda: self.status_var.set(text))

    def _update_progress(self, pct, downloaded, total, speed, eta):
        self.progress_var.set(pct)
        self.status_var.set(
            f"{self._human_size(downloaded)} / {self._human_size(total)}  "
            f"({pct:.0f}%)  {self._human_size(speed)}/s  "
            f"ETA: {self._fmt_time(eta)}"
        )

    def _update_progress_unknown(self, downloaded, speed):
        self.progress_bar.config(mode="indeterminate")
        self.progress_bar.start(10)
        self.status_var.set(
            f"{self._human_size(downloaded)} downloaded  "
            f"{self._human_size(speed)}/s"
        )

    def _on_success(self):
        self.downloading = False
        self._set_ui_state(downloading=False)
        self.progress_bar.config(mode="determinate")
        self.progress_bar.stop()
        self.progress_var.set(100)
        self.status_var.set("Download complete!")
        messagebox.showinfo("Done", f"Saved to:\n{self.output_path}")

    def _on_failure(self, error_msg):
        self.downloading = False
        self._set_ui_state(downloading=False)
        self.progress_bar.config(mode="determinate")
        self.progress_bar.stop()
        self.status_var.set(f"Failed after {self.max_retries} retries.")
        messagebox.showerror("Error", f"Download failed:\n{error_msg}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _probe_filename(url):
        """Get the real filename from the server's Content-Disposition header."""
        try:
            req = urllib.request.Request(url, method="HEAD")
            req.add_header(
                "User-Agent",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                cd = resp.headers.get("Content-Disposition", "")
                if cd:
                    # "attachment; filename=realname.zip"  or  filename*=UTF-8''realname.zip
                    import email.message
                    import re

                    # Try filename*= (RFC 5987)
                    m = re.search(r"filename\*=([^;]+)", cd, re.IGNORECASE)
                    if m:
                        enc_part = m.group(1).strip().strip('"').strip("'")
                        # UTF-8''realname.zip
                        parts = enc_part.split("'", 2)
                        if len(parts) == 3:
                            from urllib.parse import unquote as url_unquote
                            return url_unquote(parts[2])
                    # Try plain filename=
                    m = re.search(r'filename="?([^";]+)"?', cd, re.IGNORECASE)
                    if m:
                        from urllib.parse import unquote as url_unquote
                        return url_unquote(m.group(1).strip())
        except Exception:
            pass
        return None

    @staticmethod
    def _extract_filename(url):
        """Pull a filename from the URL path."""
        from urllib.parse import urlparse, unquote

        path = urlparse(url).path
        name = os.path.basename(path)
        name = unquote(name)
        # Strip query params that may have leaked in
        if "?" in name:
            name = name.split("?")[0]
        return name.strip() or None

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


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------
def main():
    root = tk.Tk()
    app = DownloaderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
