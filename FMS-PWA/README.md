# FMS Smart Multi-user Online — PWA static package

**GitHub target:** https://github.com/KnowsoftCloudAir/FMS-Multi-user-online  
(Requested name `FMSS_Smark_Multi_user_online` was not found; public repo is `FMS-Multi-user-online`.)

**Example app path on your PC:** `C:\app`

## What this package is

A complete **Progressive Web App** static shell:

| Path | Role |
|------|------|
| `index.html` | Start page (replace with your UI from `C:\app`) |
| `offline.html` | Offline fallback |
| `manifest.webmanifest` | Install metadata (name, icons, theme) |
| `sw.js` | Service worker (cache + offline) |
| `static/icons/*` | App icons 48–512 + maskable |
| `static/css/app.css` | Minimal shell styles |
| `static/js/app.js` | SW register + install button |

## Merge with `C:\app`

1. Copy your real web app files from `C:\app` into this folder (or copy these PWA files *into* `C:\app`).
2. In every main HTML template, add:

```html
<link rel="manifest" href="/manifest.webmanifest">
<meta name="theme-color" content="#0f172a">
<link rel="apple-touch-icon" href="/static/icons/apple-touch-icon.png">
<script src="/static/js/app.js"></script>
```

3. Ensure HTTPS hosting (GitHub Pages, Render, etc.).
4. Update `PRECACHE` in `sw.js` to list your real CSS/JS bundles.

## Push to GitHub

```bat
cd C:\path\to\FMS-PWA
git init
git remote add origin https://github.com/KnowsoftCloudAir/FMS-Multi-user-online.git
git add .
git commit -m "Add FMS Smart PWA static package"
git branch -M main
git push -u origin main
```

If the remote already has commits, pull/rebase first.

## PWABuilder

1. Deploy this site (or your merged app) on HTTPS.
2. Open https://www.pwabuilder.com → enter your live URL.
3. Package Android / Windows as needed.

## Local test

```bat
cd FMS-PWA
npx --yes serve -p 4173
```

Open http://localhost:4173 — DevTools → Application → Manifest / Service Workers.

## Branding

Default icons are generated FMS/teal style. Replace `static/icons/*` with your official artwork (same filenames) if you have brand assets from `C:\app`.

---
Knowsoft · FMS Smart Multi-user Online
