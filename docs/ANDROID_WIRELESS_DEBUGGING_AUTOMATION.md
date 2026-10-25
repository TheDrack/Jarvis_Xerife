# Android wireless debugging automation

## MCP tools

- android_device_status() lists ADB device states and the selected target.
- android_connect(pairing_address, pairing_code, device_address) runs adb pair with the temporary six-digit code, then adb connect to the separate connection endpoint shown by Android Wireless debugging.
- After a successful connection, Jarvis persists only the selected endpoint to %LOCALAPPDATA%\Jarvis\android-device.json. It never saves the pairing code. JARVIS_ANDROID_DEVICE, when explicitly configured, takes precedence over this selected endpoint.
- Existing android_observe_screen, android_tap, android_swipe, android_press_key, and android_type_text tools then use the selected endpoint without requiring a manual environment-variable edit.

## Phone setup and automatic reconnection

1. Enable Wireless debugging and ensure the phone is reachable on the chosen private transport (for example, Tailscale).
2. In Android Developer options, open Pair device with pairing code. Copy the pairing IP:port and the temporary six-digit code.
3. Separately copy the main Wireless debugging IP:port used for connecting. The pairing port and connect port are different.
4. Call android_connect with those three values. The code is used only for the pairing call and is not persisted.
5. Verify with android_device_status, then android_observe_screen.

ADB remembers a successfully paired host. Once the host/device pairing persists, reconnecting after a disconnect can use adb connect <device_address> without another pairing code. The endpoint may change after Wi-Fi/network changes, so refresh it from Android settings if necessary. Keep Wireless debugging enabled while using it.

## Safety

Only private RFC1918 IPv4 and Tailscale CGNAT IPv4 endpoints are accepted. Public IP endpoints are rejected. ADB pairing grants powerful device control: use only the user's own authorized device and never expose ADB ports to the public internet. Pairing codes are short-lived and must not be logged or stored. No automatic pairing is attempted at server startup; the user explicitly invokes android_connect.
