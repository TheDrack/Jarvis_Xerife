# ADR-005 — Native fullscreen bridge for Jarvis Desktop

- **Status:** Proposed for PR #710
- **Date:** 2026-11-03
- **Depends on:** Jarvis Desktop local WebView2 shell and the browser HUD

## Context

The same HUD is used by the native Windows desktop shell and by browser/mobile clients. The browser Fullscreen API controls the document viewport, but it does not own the native Windows window frame. The desktop requirement is a true native fullscreen transition: the WebView2 host must cover the active monitor and hide its window border, then restore its previous bounds and frame.

The desktop shell also has an explicit remote-URL mode. A remote page must not receive native desktop capabilities merely because it is rendered inside a WebView.

## Decision

1. Expose a deliberately narrow `DesktopWindowBridge.set_fullscreen(enabled)` API through pywebview's `js_api` only for the local desktop page.
2. Pass `js_api=None` in explicit remote-URL mode. Do not expose the native window object, arbitrary evaluation, filesystem access, or other host capabilities to page JavaScript.
3. Bind the bridge to the concrete native window immediately after `create_window` and before `webview.start`.
4. Treat fullscreen as a desired-state operation, not a blind toggle. Repeated requests for the current state must not call the native toggle again.
5. Serialize bridge calls with a process-local `threading.Lock`. pywebview executes exposed JavaScript API methods on separate threads and documents that those methods are not thread-safe. The lock protects both the desired-state check and the native window transition.
6. Keep the browser Fullscreen API as the fallback for ordinary browser/mobile clients that do not have the native bridge.
7. Update the HUD control only after the native bridge promise resolves. F11 and Escape use the same state transition path as the visible control.

## Alternatives considered

### Browser Fullscreen API only

Rejected for the native Windows shell. It can fullscreen the document inside WebView2, but it does not reliably control the outer native window frame and monitor bounds.

### Expose the complete pywebview window object

Rejected because it grants page JavaScript more native authority than this feature needs. A single boolean operation is a smaller capability boundary.

### Use operating-system hotkeys only

Rejected because it leaves the visible HUD control without a consistent action path and does not provide browser/mobile parity.

### Expose the bridge in remote-URL mode

Rejected because a remotely loaded page must not inherit local host capabilities. Remote mode remains browser-only.

## Consequences

- Local Windows fullscreen is a native window transition, including border removal and restoration of the prior window geometry.
- Repeated or concurrent button/F11 requests are serialized and idempotent.
- Browser/mobile clients retain a standards-based fallback without receiving the native bridge.
- The packaged Windows application must be rebuilt after the bridge changes are merged; an older installed executable does not contain this capability.
- Native behavior must be verified on Windows/WebView2, while the browser fallback and responsive layout are verified separately in Chromium.

## Verification contract

- Unit tests cover idempotency, unbound-window failure and concurrent requests.
- Windows E2E checks native bounds, border style, F11, button activation and Escape restoration.
- Browser automation checks the fallback contract, navigation and narrow viewports.
- Remote mode must continue to create its WebView without a JavaScript API bridge.
