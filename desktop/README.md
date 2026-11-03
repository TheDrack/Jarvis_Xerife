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
source addresses and non-private Host headers. The launch script does not create firewall rules.
To explicitly open the legacy cloud HUD instead of the local core, use
`python -m app.adapters.edge.jarvis_desktop_shell --base-url https://your-jarvis-host.example --page intelligence`.
The local core remains the default. If the machine is on an untrusted network, use loopback-only mode:

```powershell
.\scripts\start_jarvis_desktop.ps1 -LoopbackOnly
```

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
  Collection and deterministic deduplication/correlation run in the local Python
  process. Source health and partial failures are returned; no data is fabricated.
  OSIRIS and God's Eye View are displayed as optional integrations and are not claimed
  connected unless their runtime probes exist.
- **Network:** local interfaces and the OS ARP neighbour cache are read on the PC.
  The ARP view sends zero active probes. Tailscale peer state is read from the local CLI,
  so Android online/offline status is visible. Android ADB state is displayed only if
  ADB is installed; no pairing/debugging settings are changed.
- **Android UI:** Android accesses the same local dashboard through Tailscale
  (or an explicitly approved LAN firewall path). This does not silently enable ADB
  screen control or replace the existing native Android app's authenticated cloud bridge.

## Runtime endpoints

- `GET /` — single-viewport Jarvis UI
- `GET /api/health` — local process health
- `GET /api/bootstrap` — local address metadata; pairing secret only on loopback
- `POST /api/pair` — exchange temporary code for a local bearer token
- `GET /api/status` — authenticated core/client state
- `GET /api/intelligence/status` — source and pipeline state
- `POST /api/intelligence/collect` — on-demand public source collection + local synthesis
- `GET /api/intelligence/latest` — latest in-memory synthesis
- `GET /api/network/status` — interfaces, passive ARP cache, ADB and paired clients

The current intelligence snapshot is in-memory and is cleared when the local server exits.
Durable history, OSIRIS/GEV live probes, Android native-app LAN transport, and Android
UI automation remain separate integration steps.