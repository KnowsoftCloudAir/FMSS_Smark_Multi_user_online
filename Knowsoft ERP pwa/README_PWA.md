# FMSS Smart — Knowsoft ERP PWA Brand Pack

This package uses the supplied **Knowsoft ERP artwork** as the primary app icon and PWA visual identity.

## Contents

- `manifest.webmanifest` — installable PWA metadata
- `sw.js` — service worker with app-shell/runtime caching
- `offline.html` — branded offline screen
- `icons/` — PWA, Android, iOS and browser icon sizes
- `screenshots/` — PWA install screenshots
- `favicon*.png` — browser favicons

## Integration

Copy the package contents into the application's public/static root.

Add inside `<head>`:

```html
<link rel="manifest" href="/manifest.webmanifest">
<link rel="icon" type="image/png" href="/favicon-32.png">
<meta name="theme-color" content="#080C0F">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<link rel="apple-touch-icon" href="/icons/icon-192.png">
```

Register the service worker before `</body>`:

```html
<script>
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(console.error);
  });
}
</script>
```

### Important

If FMSS already has a service worker, merge this caching logic into the existing worker instead of installing a second worker for the same scope.

For a React/Vite app, these assets normally belong in `public/`.
For a plain HTML/JS app, use the site's public web root.
For another framework, use its equivalent static/public directory.
