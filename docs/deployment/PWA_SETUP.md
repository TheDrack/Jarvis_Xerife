# JARVIS PWA (Progressive Web App) Setup

## 🎯 Overview

The JARVIS HUD is now a Progressive Web App, enabling it to be installed as a standalone application on mobile devices and desktops. This provides:

- **Full-screen experience** on mobile (no browser chrome)
- **Home screen installation** - Add to home screen like a native app
- **Offline capability** - Service worker enables basic offline functionality
- **Native app feel** - Looks and behaves like a native application

## ✅ What's Implemented

### 1. PWA Manifest (`static/manifest.json`)

Defines the app's metadata:
- **Name**: "JARVIS - Just A Rather Very Intelligent System"
- **Short Name**: "JARVIS"
- **Display Mode**: `standalone` (full-screen, no browser UI)
- **Theme Colors**: #00d4ff (cyan) and #0a0e27 (dark blue)
- **Icons**: 192x192 and 512x512 PNG icons
- **Orientation**: Any (supports portrait and landscape)

### 2. Service Worker (`static/sw.js`)

Enables PWA installation and offline capability:
- **Cache Strategy**: Network-first, fallback to cache
- **Auto-updates**: Clears old caches on activation
- **Essential Caching**: Caches the root page for offline access

### 3. iOS/Safari Support

Special meta tags for iOS devices:
```html
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="JARVIS">
<link rel="apple-touch-icon" href="/static/icon-192.png">
```

### 4. Static Files Mounting

FastAPI serves the `static/` directory at `/static`:
- Manifest: `/static/manifest.json`
- Service Worker: `/static/sw.js`
- Icons: `/static/icon-192.png`, `/static/icon-512.png`

## 🎨 Generating Icons

### Option 1: Use the Icon Generator (Recommended)

1. Start the JARVIS server
2. Navigate to: `http://your-server/static/generate-icons.html`
3. The page will display two canvases with the JARVIS icons
4. Right-click on each canvas:
   - Save 192x192 canvas as `icon-192.png`
   - Save 512x512 canvas as `icon-512.png`
5. Place both files in the `static/` directory

### Option 2: Use Browser Console

1. Open `http://your-server/static/generate-icons.html`
2. Open browser developer console (F12)
3. Run these commands:
   ```javascript
   downloadCanvas("icon192", "icon-192.png")
   downloadCanvas("icon512", "icon-512.png")
   ```
4. Icons will download automatically

### Option 3: Create Custom Icons

Use any image editor to create:
- **icon-192.png**: 192x192 pixels
- **icon-512.png**: 512x512 pixels

Design guidelines:
- Background: #0a0e27 (dark blue)
- Primary color: #00d4ff (cyan)
- Theme: Arc reactor / tech aesthetic
- Include "JARVIS" text or logo

### Option 4: Use Online Tools

Convert the provided SVG template to PNG:
1. Open `static/icon-192.png.svg` in a browser
2. Use online converters:
   - https://cloudconvert.com/svg-to-png
   - https://onlineconvertfree.com/convert-format/svg-to-png/
3. Generate at 192x192 and 512x512 resolutions

## 📱 Installing the PWA

### On Android (Chrome/Edge)

1. Open the JARVIS HUD in Chrome
2. Tap the menu (⋮) → "Add to Home screen"
3. Confirm installation
4. The JARVIS icon appears on your home screen
5. Tap to open in full-screen standalone mode

### On iOS (Safari)

1. Open the JARVIS HUD in Safari
2. Tap the Share button (box with arrow)
3. Scroll down and tap "Add to Home Screen"
4. Customize the name if desired
5. Tap "Add"
6. The JARVIS icon appears on your home screen

### On Desktop (Chrome/Edge)

1. Open the JARVIS HUD in Chrome/Edge
2. Look for the install icon (⊕) in the address bar
3. Click "Install"
4. JARVIS opens in its own window
5. Access from Start Menu / Applications

## 🔍 Verifying PWA Installation

### Check Manifest

1. Open browser DevTools (F12)
2. Go to "Application" tab (Chrome) or "Storage" (Firefox)
3. Under "Manifest" section, verify:
   - Name: "JARVIS"
   - Start URL: "/"
   - Display: "standalone"
   - Icons are loaded

### Check Service Worker

1. In DevTools → Application → Service Workers
2. Verify service worker is registered:
   - Source: `/static/sw.js`
   - Status: Activated and running
   - Scope: `/`

### Test Offline Mode

1. Install the PWA
2. In DevTools → Network, enable "Offline" mode
3. Refresh the page
4. The cached version should load

## 🚀 Features When Installed

### Full-Screen Experience

- No browser chrome (address bar, navigation buttons)
- Immersive UI like a native app
- Maximizes screen real estate on mobile

### Standalone Window (Desktop)

- Runs in its own window (not a browser tab)
- Appears in taskbar/dock as separate app
- Can be pinned for quick access

### Native App Behavior

- Appears in app switcher
- Can receive focus like native apps
- Integrates with OS notifications (future)

### Offline Access

- Cached pages available offline
- Service worker handles failed network requests
- Basic functionality works without internet

## 🔧 Configuration

### Customizing the Manifest

Edit `static/manifest.json`:

```json
{
  "name": "Your Custom Name",
  "short_name": "Short",
  "theme_color": "#YOUR_COLOR",
  "background_color": "#YOUR_BG_COLOR",
  ...
}
```

### Customizing the Service Worker

Edit `static/sw.js`:

```javascript
// Add more URLs to cache
const urlsToCache = [
  '/',
  '/static/manifest.json',
  '/static/icon-192.png',
  // Add more resources
];
```

### Cache Strategy Options

Current: **Network-first, fallback to cache**
- Always tries network first
- Falls back to cache on failure
- Good for dynamic content

Alternative: **Cache-first, fallback to network**
```javascript
event.respondWith(
  caches.match(event.request)
    .then((response) => response || fetch(event.request))
);
```

## 🐛 Troubleshooting

### PWA Won't Install

**Problem**: Install prompt doesn't appear

**Solutions**:
1. Ensure you're using HTTPS (or localhost)
2. Verify manifest.json is accessible
3. Check service worker is registered
4. Clear browser cache and reload
5. Check DevTools console for errors

### Service Worker Not Registering

**Problem**: Service worker registration fails

**Solutions**:
1. Check `/static/sw.js` is accessible
2. Verify HTTPS is enabled (required for SW)
3. Clear existing service workers in DevTools
4. Check browser console for errors

### Icons Not Showing

**Problem**: Default icons appear instead of JARVIS icons

**Solutions**:
1. Verify `icon-192.png` and `icon-512.png` exist in `static/`
2. Use the icon generator tool
3. Check file permissions (must be readable)
4. Clear browser cache
5. Uninstall and reinstall the PWA

### iOS Not Working

**Problem**: iOS doesn't recognize PWA

**Solutions**:
1. Ensure apple-mobile-web-app meta tags are present
2. Verify apple-touch-icon exists
3. Safari requires actual PNG files (not just manifest)
4. Test in Safari specifically (not Chrome on iOS)

### Offline Mode Not Working

**Problem**: App doesn't work offline

**Solutions**:
1. Verify service worker is active
2. Load the page online first (to populate cache)
3. Check cache strategy in sw.js
4. Use DevTools → Application → Cache Storage to inspect cached files

## 📊 Browser Support

| Feature | Chrome | Safari | Firefox | Edge |
|---------|--------|--------|---------|------|
| PWA Install | ✅ | ✅ | ✅ | ✅ |
| Service Worker | ✅ | ✅ | ✅ | ✅ |
| Manifest | ✅ | ✅ | ✅ | ✅ |
| Standalone Mode | ✅ | ✅ | ⚠️ | ✅ |
| Offline Cache | ✅ | ✅ | ✅ | ✅ |

⚠️ Firefox on Android supports PWA but has limited standalone mode

## 🔮 Future Enhancements

- [ ] Push notifications
- [ ] Background sync
- [ ] Periodic background sync
- [ ] File handling
- [ ] Share target API
- [ ] Shortcuts API
- [ ] Badging API
- [ ] Advanced caching strategies

## 📝 Testing Checklist

- [ ] Manifest is accessible at `/static/manifest.json`
- [ ] Service worker registers successfully
- [ ] Icons (192x192 and 512x512) are in place
- [ ] Install prompt appears on mobile
- [ ] App installs and runs in standalone mode
- [ ] Offline mode works after first load
- [ ] iOS Safari recognizes as web app
- [ ] Desktop installation works (Chrome/Edge)
- [ ] App appears in home screen / start menu
- [ ] Full-screen mode works on mobile

---

**🤖 JARVIS PWA: Your AI assistant, now as a standalone app** 📱💻
