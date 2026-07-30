# Roan's Web Downloader

## Project Info
- **Language:** Python 3.14
- **Entry Point:** `Roans-Web-Downloader.py`
- **Python Path:** `C:/Users/roanh/AppData/Local/Python/pythoncore-3.14-64/python.exe`

## How to Run
```
python Roans-Web-Downloader.py
```

## Architecture
- Single-file, zero-build Python script
- GUI: `tkinter` (built-in, no install needed)
- Downloads: `urllib` (built-in)
- Zero external dependencies — cross-platform (Windows, macOS, Linux)

## Features
- URL input + folder picker GUI
- Resume interrupted downloads (HTTP Range header)
- Auto-retry up to 10 times with exponential backoff (1s → 2s → 4s... max 60s)
- Real-time progress bar with download speed and ETA
- Cancel button
- Detects real filename from `Content-Disposition` header (not just URL path)
- Connection-drop detection: retries instead of falsely reporting "complete"

## Key Design Decisions
- Uses ONLY Python stdlib — no `requests`, no `aiohttp`, no external packages
- Background download thread keeps UI responsive
- HEAD request probes server for resume/range support before attempting resume
- Falls back to full redownload if server doesn't support Range requests
- Exponential backoff for retries: `min(2^(n-1), 60)` seconds
- `_do_download()` returns `(success, partial)` — connection drops are caught mid-stream and retried with resume
- `_probe_filename()` does a HEAD → reads `Content-Disposition` for correct filename + extension
