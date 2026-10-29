---
name: jarvis-mobile-notifications
description: Send authenticated Jarvis notifications or speech to the Android companion over the native WebSocket or durable event queue.
---

# Jarvis Mobile Notifications

## Delivery architecture
- When the authenticated Android bridge is connected, the agent sends a task over `/v1/local-bridge` and waits for the task result.
- When disconnected, the backend stores a short-lived event in Supabase. The Android app fetches pending events after its authenticated bridge reconnects and acknowledges them after posting a notification or completing speech.
- Offline queueing is not immediate delivery: Android must reconnect to the Jarvis API. No third-party push provider is used.

## Preconditions
- The backend deployment must include the mobile event queue endpoints and the Supabase migration.
- `JARVIS_MOBILE_NOTIFY_KEY` must be configured for agent endpoints, and the protected Windows key file may be used by the client script.
- Never display, echo, log, commit, or transmit the credential anywhere except the `X-Jarvis-Mobile-Notify-Key` request header.
- Never use the phone's Bearer token, `API_KEY_LOCAL`, or `JARVIS_RETURN_ACTIVITY_KEY` as a substitute.

## Sending
Run the repository script with Windows PowerShell 5.1 or later:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\send_mobile_notification.ps1 -Text "Teste do Jarvis" -Mode notification
```

Use `-Mode speak` only when audio is requested. The script requires HTTPS and chooses a device automatically only when exactly one is available.

## Delivery semantics
- `status=delivered, transport=websocket`: the connected Android app returned a successful task result.
- `status=queued, transport=queue`: the event is persisted for the next authenticated mobile reconnect; it has not yet been delivered.
- `status=acknowledged`: the Android client fetched the event and acknowledged successful handling; it does not mean a human read it.
- `status=expired`: the event was not acknowledged before expiry.

## Mobile → Jarvis
Chat messages use the authenticated `POST /v1/message` flow. Never ask the user to paste a mobile JWT into a prompt or logs. If chat submission fails, inspect the sanitized HTTP error, session refresh logs, and server health.

## Common failures
- `401`: invalid agent credential or mobile session.
- `404`: no matching registered/connected device or event.
- `409`: multiple devices match; specify device and user IDs.
- `502`: WebSocket delivery was not confirmed.
- `503`: event storage or service configuration is unavailable.

Never state that a message was delivered solely because the endpoint returned `queued` or because a WebSocket connected. Verify the explicit result or event ACK.
