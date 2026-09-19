# Knowsoft FMSS Multi-User Online — with PWA

## PWA assets
- `/manifest.webmanifest` — install metadata (name, icons, theme)
- `/sw.js` — service worker (shell cache)
- `/static/icons/` — 72–512 px + maskable icons

## Install (PWABuilder / browser)
1. Deploy to HTTPS (Render)
2. Open site → Chrome/Edge → Install app
3. Or https://www.pwabuilder.com with your live URL

## Start
```bash
pip install -r requirements.txt
cd backend && uvicorn main:app --host 0.0.0.0 --port 8000
# or from root:
uvicorn app:app --host 0.0.0.0 --port $PORT
```
