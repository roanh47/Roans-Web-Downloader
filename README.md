# Roan's Web Downloader

Cross-platform GUI downloader with resume & auto-retry — zero external dependencies.

## Features

- **Resume interrupted downloads** — uses HTTP Range headers to pick up where it left off
- **Auto-retry** — up to 10 retries with exponential backoff (1s → 2s → 4s... max 60s)
- **Real-time progress** — progress bar with download speed and ETA
- **Cancel** — stop a download at any time
- **Content-Disposition detection** — discovers the real filename from server headers, not just the URL
- **Connection-drop detection** — retries mid-stream drops instead of reporting a false success

## Requirements

- Python 3.x
- Nothing else — uses only the standard library (`tkinter`, `urllib`)

## How to Run

```
python Roans-Web-Downloader.py
```

## Usage

1. Paste a download URL you definitely didn't get from your shady friend
2. Choose a save folder (defaults to `Downloads`)
3. Click **Download**
