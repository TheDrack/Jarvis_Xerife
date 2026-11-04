# Jarvis Desktop — Local Core

Jarvis Desktop starts a local API and a native WebView2 window. The same responsive
single-viewport interface is served to the Windows PC and, when LAN mode is enabled,
to a browser on Android.

## Start on Windows

From the repository root:

```powershell
python -m pip install -r requirements/desktop.txt
powershell -ExecutionPolicy Bypass -File .\scripts\start_jarvis_desktop.ps1
```

The default listener is port 8766 on local/private interfaces. The API rejects public
source addresses and non-private Host headers. Uvicorn proxy headers are disabled, so
client identity is not derived from an untrusted `X-Forwarded-For` value. The launch
script does not create firewall rules.
To explicitly open the legacy cloud HUD instead of the local core, use
`python -m app.adapters.edge.jarvis_desktop_shell --base-url https://your-jarvis-host.example --page intelligence`.
The local core remains the default. If the machine is on an untrusted network, use loopback-only mode:

```powershell
.\scripts\start_jarvis_desktop.ps1 -LoopbackOnly
```

## Build the native Windows application

The Windows package is a one-folder PyInstaller distribution. Keep the executable and
its `_internal` directory together; moving only the EXE breaks its bundled runtime.
Windows requires the Microsoft Edge WebView2 Runtime.

Install the project and desktop build dependencies, then build from the repository root:

```powershell
python -m pip install -r requirements.txt -r requirements/desktop.txt
powershell -ExecutionPolicy Bypass -File .\scripts\build_jarvis_desktop.ps1
```

The validated output is `dist\JarvisDesktop\JarvisDesktop.exe`. The build script
fails unless both the executable and bundled `_internal\desktop\jarvis.ico` asset
exist. The icon is also embedded in the executable by `JarvisDesktop.spec`. A Windows
shortcut should use the EXE as its icon source (for example,
`dist\JarvisDesktop\JarvisDesktop.exe,0`) rather than referencing the source tree.

## Connect Android through Tailscale

1. Open the Jarvis Desktop window on the PC.
2. Read the Tailscale address and six-digit temporary pairing code in the Command Center.
3. On Android, enable Tailscale and open the PC's Tailscale IPv4 from
   `tailscale ip -4` as `http://<tailscale-ip>:8766` in Chrome/Brave.
   Direct Wi-Fi/LAN access requires a separately approved Windows Firewall rule.
4. Enter the temporary pairing code. The browser receives a random bearer token valid
   for 12 hours.
5. Both screens use the same local API and local runtime; no Render/Firebase dependency
   is used for the desktop/mobile dashboard.

On the current Windows host, the inbound firewall allowance is restricted to TCP 8766
from the Tailscale CGNAT range `100.64.0.0/10` on the Private profile. No broad
LocalSubnet or Public-profile rule is created. Direct Wi-Fi/LAN access is therefore
not opened by default; use Tailscale for Android until a narrower LAN rule is explicitly
approved.

The pairing code is visible only to loopback clients and rotates after a successful
pairing or after ten minutes. Five failed attempts temporarily lock pairing.
The bearer token is held in the browser session storage, not embedded in HTML.

**Transport note:** LAN mode uses HTTP, not TLS. The one-time pairing and bearer token
provide access control, not encryption against a hostile Wi-Fi/LAN observer. Use only
a trusted private network. Do not forward port 8766 to the public internet. For remote
access, use the user's approved authenticated private HTTPS route instead.

## Functional layers

- **Intelligence:** GDELT, NASA EONET and USGS are collected only on explicit click.
  OSIRIS uses the public read-only API at https://osirisai.live by default; set
  JARVIS_OSIRIS_ENABLED=false to disable it or JARVIS_OSIRIS_API_BASE_URL to use
  another HTTPS origin. God's Eye View connects through its local MCP STDIO server.
  Its entrypoint, loopback API base and bounded geographic area are loaded from
  %LOCALAPPDATA%\Jarvis_Xerife\intelligence.env; only the documented
  JARVIS_OSIRIS_* and JARVIS_GEV_* keys are accepted, and process environment
  variables take precedence. Collection and deterministic deduplication/correlation
  run in the local Python process. Source health and partial failures are returned;
  no data is fabricated. The GEV vessel query requires AISSTREAM_API_KEY in the
  God's Eye View server environment; without it, aircraft and satellite observations
  can still succeed and the source is reported as partially degraded.
- **Network:** local interfaces and the OS ARP neighbour cache are read on the PC.
  The ARP view sends zero active probes. Tailscale peer state is read from the local CLI,
  so Android online/offline status is visible. Android ADB state is displayed only if
  ADB is installed; no pairing/debugging settings are changed.
- **Android UI:** Android accesses the same local dashboard through Tailscale
  (or an explicitly approved LAN firewall path). This does not silently enable ADB
  screen control or replace the existing native Android app's authenticated cloud bridge.

## Runtime endpoints

- `GET /` — single-viewport Jarvis UI (orbital HUD)
- `GET /static/world-land.json` — simplified land outlines used by the globe canvas
- `GET /api/health` — local process health
- `GET /api/bootstrap` — local address metadata; pairing secret only on loopback
- `POST /api/pair` — exchange temporary code for a local bearer token
- `GET /api/status` — authenticated core/client state
- `GET /api/telemetry` — host CPU, memory, temperature (when the OS exposes it), processes and uptime
- `GET /api/briefing` — daily headlines by topic (region, world, politics, economy, war, technology, climate) plus the local weather forecast
- `GET /api/cameras` — operator-registered camera allowlist (never probes or opens a stream)

The daily briefing reads two credential-free public sources: Google News RSS
(pt-BR headlines per topic) and Open-Meteo (current conditions plus a three-day
forecast). Point it at your own region with `JARVIS_BRIEFING_LABEL`,
`JARVIS_BRIEFING_LAT`, `JARVIS_BRIEFING_LON` and `JARVIS_BRIEFING_TIMEZONE`
(defaults: Porto Alegre, `America/Sao_Paulo`). Headlines keep their publisher
link; nothing is rewritten and no article body is stored.

Cameras are never discovered or scraped: register only public views you are
allowed to watch in `%LOCALAPPDATA%\Jarvis_Xerife\cameras.json`.

```json
{"cameras": [{"label": "Centro", "url": "https://exemplo/camera.jpg", "kind": "snapshot", "refresh_seconds": 20}]}
```

`kind` is `snapshot` (JPEG refresh) or `video` (direct MP4/WebM URL). Only
`http(s)` URLs without embedded credentials are accepted, up to 12 cameras;
invalid entries are counted in `rejected` instead of being silently dropped.

## Universal Intelligence

The local core serves the Universal Intelligence surface natively with the same
contract as the main API:

- `GET /intelligence` — Universal Intelligence dashboard (`app/static/intelligence.html`)
- `GET /v1/intelligence/status` — authenticated status contract (sources, pipeline, history, security)
- `POST /v1/intelligence/collect?limit=N` — on-demand collection through the canonical collector

The dashboard reads `jarvis_auth_token` from `localStorage` or falls back to the
local `jarvis_local_access` session token, so it opens from the desktop HUD
without a second login. The Intel window of the orbital HUD renders the same
contract and links to the full dashboard.
- `GET /api/intelligence/status` — source and pipeline state
- `POST /api/intelligence/collect` — on-demand public source collection + local synthesis
- `POST /api/intelligence/osiris` — OSIRIS routes only, with per-route health
- `POST /api/intelligence/gods-eye` — God's Eye View MCP snapshot only, with entity counts
- `GET /api/intelligence/latest` — latest in-memory synthesis
- `GET /api/network/status` — interfaces, passive ARP cache, ADB and paired clients

The orbital HUD renders only what these endpoints return: events and observations are plotted
on the globe, the status line reflects the last real probe, and uncollected layers stay empty.
OSIRIS and God's Eye can be refreshed independently so one slow or degraded provider does not
block the other. Host telemetry reports `temperature_c: null` on Windows because psutil does not
expose a sensor source there.

The current intelligence snapshot is in-memory and is cleared when the local server exits.
Durable history, Android native-app LAN transport, and Android UI automation remain separate
integration steps.
