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
  no data is fabricated. OSIRIS also contributes bounded ADS-B flights, ports,
  chokepoints and AIS vessels, CelesTrak satellites, public CCTV directory metadata
  and the GDELT/GDACS feed; camera stream URLs remain references and are never
  proxied or probed. God's Eye View additionally contributes allowlisted public
  camera, infrastructure and military-installation assets when its live tool schemas
  declare them read-only. The GEV vessel query requires AISSTREAM_API_KEY in the
  God's Eye View server environment; without it, aircraft, satellite and asset
  observations can still succeed and the source is reported as partially degraded.
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

## Devices on the globe

`GET /api/devices` reads the `devices` table of the local SQLite registry
(`jarvis.db`, override with `JARVIS_DEVICES_DB`) with `mode=ro`. Nothing is
written: each row returns name, type, status, last IP, last seen and the
coordinates the node itself reported. A device without coordinates is still
listed with `located: false` and is not drawn — no position is inferred from
the IP address.

The HUD plots located devices as amber hexagons (bright when `online`, dim when
`offline`) and lists them in the DISPOSITIVOS panel, where a row recenters the
globe on that device.

## Briefing anchored on the accessing device

`GET /api/briefing?lat=<latitude>&lon=<longitude>` anchors the briefing on the
device that is reading the HUD instead of the host configuration:

- weather comes from Open-Meteo at those exact coordinates (`timezone=auto`);
- the regional headline topic is rebuilt from the place names resolved for that
  coordinate;
- `region.source` tells the caller where the briefing came from — `device` or
  `configured` — and `region.geocoded` tells whether the place names resolved.

Place names come from the public OSM Nominatim reverse endpoint (one call per
rounded coordinate cell, cached for a day, spaced by at least one second, always
with the Jarvis user agent). Only the coordinates are sent; no token, device id
or operator identity. Set `JARVIS_BRIEFING_GEOCODE=off` to keep coordinates on
the host: the weather then still uses them, and the regional headlines stay on
the configured terms, which the payload states explicitly.

Coordinates are validated (`lat` in −90..90, `lon` in −180..180, both or
neither) and rejected with 422 otherwise. The HUD asks the browser/WebView for
`navigator.geolocation` on load and exposes the `LOC` button to ask again; when
permission is denied the footer says so and the configured region is used.

## Globe controls

The globe rotates by drag, zooms with the mouse wheel, a two-finger pinch or the
`+` / `−` controls, and `⤢` recenters it. The label row under the globe focuses
an area with an animated rotation and zoom: MUNDO, the continental presets,
REGIÃO (the briefing region, or the God's Eye box when the briefing has no
region) and DISPOSITIVOS (centroid of the located devices). A chip is disabled
when there is no real anchor for it, so the control never invents a target.

The page keeps one type scale (`--fs-*`) and one palette (`--mint`, `--amber`,
`--red`), two font families (monospace for readouts, sans for content), and
shows only the panels of the selected view — BRIEFING + FONTES in the default
CORE view.

The dock is split into labelled groups that share one style: INTELIGÊNCIA
(Core, Eventos, Fontes, Orbital, Intel), AQUI (Telemetria, Rede — this device)
and ENCONTRADO (Disp, Cams — discovered on the network), with the collection orb
in the middle.

### Devices: GPS, IP and place names

`GET /api/devices` labels where each position came from. A node that reported
coordinates is `location_source: "gps"` and its coordinate is reverse-geocoded
to `city`/`state`/`country` (`place_label`, e.g. `Curitiba · Paraná · Brasil`).
A node without GPS falls back to its last public IP through ipwho.is, marked
`location_source: "ip"` and `approximate: true` because it points at the ISP's
city, not the device. Private, loopback, link-local, CGNAT and Tailscale
addresses are never sent to that service, and a failure is reported as
`location_reason` instead of a guessed position. Set `JARVIS_IP_GEOLOCATION=off`
to disable the IP lookup entirely.

### Earthquakes: affected regions

The local core enriches USGS earthquake events with an estimated affected radius
(`felt_radius_km`, `damage_radius_km`, `method: magnitude_scaling_v1`) and, for
the first events of each collection, the reverse-geocoded place. It is an
estimate derived from the magnitude — not a ShakeMap — and the payload says so.
The globe draws that radius as a translucent ring around the epicentre with the
magnitude and the place label, the `ABALOS` chip in the area bar focuses the most
recent one, and the EVENTS list shows `país/estado/cidade · RAIO ~N KM`.

### Public cameras

`GET /api/cameras` is the operator's own allowlist. `GET /api/cameras/open`
adds public cameras near a coordinate (`lat`, `lon`, `radius_km` up to 500,
`limit` up to 24), from two providers that permit public reuse:

- **Transport for London JamCams** — keyless, official API, JPEG snapshots.
- **Datumfeed** — aggregator of official traffic-camera registries (Caltrans,
  Washington, Austin, Ottawa, Ontario 511, TfL, Toronto). Keyless anonymous tier;
  `JARVIS_DATUMFEED_KEY` raises the limits. Cameras whose registry forbids
  proxying are skipped.

Each camera carries `provider`, `attribution`, `license` and, when the provider
reports them, trust/uptime fields; the HUD prints the attribution next to the
frame. Coverage is the providers' coverage (London plus US/Canadian registries),
and the response says so instead of pretending global coverage. Private or
unsecured cameras are deliberately not supported.

### HUD source and the packaged app

The PowerShell launcher (`scripts/start_jarvis_desktop.ps1`) starts
`jarvis_desktop_shell`, which serves `app/static/jarvis-desktop.html` straight
from the repository — there is a single HUD file. `GET /api/hud/version` returns
its SHA-256, size and modification time, and the footer shows the short hash, so
you can see which file the running window is actually rendering. A packaged
`JarvisDesktop.exe` copies `app/static` at build time: rebuild it with
`scripts/build_jarvis_desktop.ps1` after changing the HUD.

## HUD on Android

`mobile/android` embeds this same page in a WebView (`HudScreen.kt`), so the
desktop and the phone share a single HUD implementation. The phone only needs
the core address (LAN or Tailscale, port 8777) and the six-digit pairing code
shown in the HUD footer.

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
- `POST /api/intelligence/osiris` — OSIRIS event and observation routes only, with per-route health
- `POST /api/intelligence/gods-eye` — God's Eye View MCP snapshot only, with entity counts for
  aircraft, vessels, satellites, cameras, infrastructure and military sites
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
