---
name: jarvis-mobile-notifications
description: Send authenticated Jarvis notifications or speech to a registered Android device and verify delivery status without exposing mobile bearer tokens.
---

# Jarvis Mobile Notifications

## When to use
Use this skill when an authorized user or agent needs to send a notification or short spoken message from Jarvis to the Android companion, or verify whether an FCM event was acknowledged.

## Preconditions
- The backend must be deployed with the agent notification endpoints.
- The dedicated service credential `JARVIS_MOBILE_NOTIFY_KEY` must be configured in the process environment or in the protected file `%LOCALAPPDATA%\Jarvis_Xerife\config\mobile_notify\mobile_notify.key`.
- Never display, echo, log, commit, or transmit the credential anywhere except the `X-Jarvis-Mobile-Notify-Key` request header.
- Never use the phone's Bearer token, `API_KEY_LOCAL`, or `JARVIS_RETURN_ACTIVITY_KEY` as a substitute.

## Sending
Run the repository script with Windows PowerShell 5.1 or later:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\send_mobile_notification.ps1 -Text "Teste do Jarvis" -Mode notification
```

Use `-Mode speak` only when audio is requested. The script requires HTTPS, chooses a device automatically only when exactly one is available, and can accept explicit `-DeviceId` and `-UserId` when multiple devices exist.

## Delivery semantics
- `status=delivered, transport=websocket`: the connected Android app returned a successful task result after posting the notification or completing speech.
- `status=queued, transport=fcm`: FCM accepted the event for delivery; this is **not** proof the app received it.
- `delivery_status=acknowledged`: the Android app fetched the authenticated event, posted the notification, and ACKed it. It does not mean a human read it.
- `delivery_status=pending_ack`: do not claim delivery; inspect device connectivity, FCM registration, notification permission, and backend logs.
- `delivery_status=expired`: the event was not acknowledged before expiry.

## Mobile → Jarvis
Chat messages from the Android app use its authenticated `POST /v1/message` flow. Do not ask the user to paste a mobile JWT into a prompt or logs. If chat submission fails, inspect the app's sanitized HTTP error, session refresh logs, and server health.

## Common failures
- `401`: the supplied dedicated notification credential is incorrect.\n- `503`: the server-side notification credential or Firebase configuration is missing.
- `404`: no matching registered/connected device or no active FCM registration.
- `409`: multiple devices match; specify both device and user IDs.
- `502`: delivery was not confirmed or the provider failed.
- `503`: Firebase/server-side storage configuration is unavailable.

Never state that a message was delivered solely because an endpoint returned `queued` or because the WebSocket connected. Verify the explicit result or event ACK.
