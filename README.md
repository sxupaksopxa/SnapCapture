# SnapCapture

SnapCapture is a lightweight operational capture tool for quickly collecting tasks, reminders, appointments, and follow-ups from text, screenshots, PDFs, images, and audio recordings.

The application is designed as a temporary capture buffer — not a permanent organizer.

Users can:
- capture information quickly,
- review extracted items,
- edit titles, dates, and notes,
- export tasks and events,
- remove items afterwards.

---

# Features

- Text extraction
- PDF and image extraction
- Audio transcription
- AI-assisted task and event extraction
- Multiple extraction engines
- Temporary operational queue
- `.ics` calendar export
- Mobile-friendly interface
- Daily AI request limits
- Privacy-focused workflow
- BYOK (Bring Your Own Key) support

---

# Current MVP Status

SnapCapture is currently an MVP release focused on:
- operational workflows,
- fast capture,
- simple review,
- temporary storage,
- export-first usage.

The application is intentionally lightweight and does not try to replace calendars, organizers, or note-taking systems.

---

# Workflow

```text
Capture → Extract → Review → Save → Export → Delete
```

Recommended usage:
- collect tasks and events during the day,
- review extracted items,
- export them to your preferred calendar or organizer,
- delete them afterwards.

---

# Supported Inputs

- Text
- Screenshots
- Images
- PDFs
- Audio recordings

---

# Extraction Engines

SnapCapture currently supports:
- Gemini Flash
- GPT-4o-mini

Additional providers may be added later.

---

# BYOK (Bring Your Own Key)

Advanced users can optionally configure their own API keys.

This allows:
- higher usage limits,
- provider flexibility,
- personal API billing,
- reduced shared infrastructure costs.

SnapCapture does not permanently store user API keys.

---

# Privacy

SnapCapture is designed with a privacy-focused workflow:
- local OCR and transcription whenever possible,
- temporary storage only,
- export-first philosophy,
- no long-term operational archive.

Uploaded files should not be stored permanently.

---

# AI Usage

AI extraction is used only when needed.

Typical flow:
1. Local OCR/transcription
2. AI cleanup and extraction
3. Structured operational output

This helps reduce API usage while improving extraction quality.

---

# Daily AI Limits

The MVP currently uses daily AI request limits to prevent excessive API usage.

Current default:
- 30 AI requests per day

---

# Technology Stack

## Frontend
- React
- Vite

## Backend
- FastAPI
- Python

## Database
- SQLite

## Local Processing
- Tesseract OCR
- Whisper transcription

## AI Providers
- Gemini
- OpenAI

---

# Installation

## Prerequisites

Install:
- Node.js
- Python 3.11+
- Tesseract OCR

Optional:
- FFmpeg (recommended for audio support)

---

# Frontend Setup

```bash
cd frontend

npm install

npm run dev
```

Frontend runs on:

```text
http://localhost:5173
```

---

# Backend Setup

## Create virtual environment

```bash
cd backend

python -m venv .venv
```

## Activate environment

### macOS / Linux

```bash
source .venv/bin/activate
```

### Windows

```bash
.venv\Scripts\activate
```

---

## Install dependencies

```bash
pip install -r requirements.txt
```

---

## Run backend

```bash
uvicorn app.main:app --reload
```

Backend runs on:

```text
http://localhost:8000
```

---

# Environment Variables

Create `.env` inside backend directory:

```env
GEMINI_API_KEY=your_key
OPENAI_API_KEY=your_key
```

Never commit `.env` files to GitHub.

---

# OCR Setup

Install Tesseract OCR.

## macOS

```bash
brew install tesseract
```

## Ubuntu

```bash
sudo apt install tesseract-ocr
```

## Windows

Download installer from:
https://github.com/tesseract-ocr/tesseract

---

# Audio Support

Optional but recommended:

## macOS

```bash
brew install ffmpeg
```

## Ubuntu

```bash
sudo apt install ffmpeg
```

---

# Notes

SnapCapture is still under active development.

Current focus areas:
- extraction quality,
- mobile workflow,
- AI provider flexibility,
- `.ics` and `.csv` export,
- operational simplicity.

---

# Version

SnapCapture MVP v0.9

BKlein Digital Labs

Small practical tool for real everyday usage.

---

© 2026 BKlein Digital Labs. All rights reserved.# SnapCapture
