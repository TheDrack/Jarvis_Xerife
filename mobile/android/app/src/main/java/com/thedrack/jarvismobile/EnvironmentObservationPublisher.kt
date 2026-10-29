package com.thedrack.jarvismobile

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import org.json.JSONObject
import java.time.Instant
import java.util.UUID

data class MobileNetworkSnapshot(
    val networkType: String,
    val internetAvailable: Boolean,
    val validated: Boolean,
    val metered: Boolean,
    val vpnActive: Boolean
)

/**
 * Publishes permission-minimal environment observations through the existing authenticated API.
 * Does not read SSID/BSSID, request location permission, or discover other LAN devices.
 */
object EnvironmentObservationPublisher {
    fun collect(context: Context): MobileNetworkSnapshot {
        val manager = context.getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager
            ?: return MobileNetworkSnapshot("unknown", false, false, true, false)
        val network = manager.activeNetwork
            ?: return MobileNetworkSnapshot("unknown", false, false, true, false)
        val capabilities = manager.getNetworkCapabilities(network)
            ?: return MobileNetworkSnapshot("unknown", false, false, true, false)

        val vpn = capabilities.hasTransport(NetworkCapabilities.TRANSPORT_VPN)
        val type = when {
            vpn -> "vpn"
            capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> "wifi"
            capabilities.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> "cellular"
            capabilities.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET) -> "ethernet"
            else -> "unknown"
        }
        return MobileNetworkSnapshot(
            networkType = type,
            internetAvailable = capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET),
            validated = capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED),
            metered = !capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_METERED),
            vpnActive = vpn
        )
    }

    fun buildObservation(
        deviceId: String,
        snapshot: MobileNetworkSnapshot,
        observationType: String = "network_snapshot",
        presenceActive: Boolean = false,
        observedAt: String = Instant.now().toString(),
        requestId: String = UUID.randomUUID().toString()
    ): JSONObject {
        require(deviceId.isNotBlank() && deviceId.length <= 128)
        require(observationType == "network_snapshot" || observationType == "presence")
        val payload = JSONObject()
            .put("platform", "android")
            .put("network_type", snapshot.networkType)
            .put("internet_available", snapshot.internetAvailable)
            .put("validated", snapshot.validated)
            .put("metered", snapshot.metered)
            .put("vpn_active", snapshot.vpnActive)
        if (observationType == "presence") {
            payload.put("active", presenceActive)
            payload.put("app_state", if (presenceActive) "foreground_service" else "app")
        }
        return JSONObject()
            .put("device_id", deviceId)
            .put("source_device_type", "mobile")
            .put("observation_type", observationType)
            .put("schema_version", 1)
            .put("request_id", requestId)
            .put("observed_at", observedAt)
            .put("payload", payload)
    }

    /** Call only from a worker/background thread; auth helper renews the existing mobile session. */
    fun publish(context: Context, deviceId: String, presenceActive: Boolean) {
        val snapshot = collect(context)
        listOf(
            buildObservation(deviceId, snapshot, "network_snapshot", presenceActive),
            buildObservation(deviceId, snapshot, "presence", presenceActive)
        ).forEach { observation ->
            MobilePushClient.authenticatedRequest(
                context,
                "/v1/environment/observations",
                "POST",
                observation.toString()
            )
        }
    }
}
