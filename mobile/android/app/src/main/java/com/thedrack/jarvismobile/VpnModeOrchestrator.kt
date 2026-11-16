package com.thedrack.jarvismobile

/** User-selected policy for choosing the network telemetry provider. */
enum class VpnModePreference(val wireValue: String) {
    AUTO("auto"),
    JARVIS("jarvis"),
    TAILSCALE("tailscale");

    companion object {
        fun fromWireValue(value: String?): VpnModePreference =
            entries.firstOrNull { it.wireValue == value } ?: AUTO
    }
}

enum class VpnCollectionMode(val wireValue: String) {
    NETWORK_STATS("network_stats"),
    JARVIS_VPN("jarvis_vpn"),
    TAILSCALE("tailscale"),
    EXTERNAL_VPN_UNSUPPORTED("external_vpn_unsupported"),
    WAITING_FOR_TAILSCALE("waiting_for_tailscale")
}

data class VpnModeDecision(
    val mode: VpnCollectionMode,
    /** Provider is deliberately "external_unknown" unless Tailscale integration is verified. */
    val provider: String,
    val mayStartJarvisVpn: Boolean
)

/**
 * Pure policy. Detection and collection engines are deliberately separate.
 *
 * A VPN transport plus an installed Tailscale package does not prove that
 * Tailscale owns the active tunnel. Tailscale is selected only when its
 * telemetry adapter explicitly reports ready.
 */
object VpnModeOrchestrator {
    fun decide(
        preference: VpnModePreference,
        externalVpnActive: Boolean,
        tailscaleInstalled: Boolean,
        jarvisVpnActive: Boolean,
        tailscaleAdapterReady: Boolean,
        jarvisPacketEngineReady: Boolean
    ): VpnModeDecision {
        if (jarvisVpnActive) {
            if (preference == VpnModePreference.TAILSCALE) {
                return VpnModeDecision(VpnCollectionMode.WAITING_FOR_TAILSCALE, "jarvis", false)
            }
            return VpnModeDecision(VpnCollectionMode.JARVIS_VPN, "jarvis", false)
        }

        if (externalVpnActive) {
            if (
                preference != VpnModePreference.JARVIS &&
                tailscaleInstalled &&
                tailscaleAdapterReady
            ) {
                return VpnModeDecision(VpnCollectionMode.TAILSCALE, "tailscale", false)
            }
            return VpnModeDecision(VpnCollectionMode.EXTERNAL_VPN_UNSUPPORTED, "external_unknown", false)
        }

        if (preference == VpnModePreference.TAILSCALE) {
            return VpnModeDecision(VpnCollectionMode.WAITING_FOR_TAILSCALE, "none", false)
        }

        if (jarvisPacketEngineReady) {
            return VpnModeDecision(VpnCollectionMode.JARVIS_VPN, "jarvis", true)
        }

        // Safe fallback until a complete TUN-to-network forwarding engine is installed.
        return VpnModeDecision(VpnCollectionMode.NETWORK_STATS, "none", false)
    }
}
