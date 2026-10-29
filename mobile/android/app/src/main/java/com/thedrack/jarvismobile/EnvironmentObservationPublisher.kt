package com.thedrack.jarvismobile

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationManager
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Build
import androidx.core.content.ContextCompat
import org.json.JSONObject
import java.time.Instant
import java.util.UUID
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference

data class MobileNetworkSnapshot(
    val networkType: String,
    val internetAvailable: Boolean,
    val validated: Boolean,
    val metered: Boolean,
    val vpnActive: Boolean
)

/**
 * Publishes network/presence observations and location only after explicit user opt-in.
 * Location is collected only when requested by the foreground activity, a location permission
 * is currently granted, and the user preference is enabled. It never reads SSID/BSSID or
 * discovers other LAN devices.
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

    fun collectLocation(context: Context, consentEnabled: Boolean): JSONObject? {
        if (!consentEnabled) return null
        val fine = ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
        val coarse = ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED
        if (!fine && !coarse) return null
        val manager = context.getSystemService(Context.LOCATION_SERVICE) as? LocationManager ?: return null
        val providers = listOf(LocationManager.NETWORK_PROVIDER, LocationManager.GPS_PROVIDER)
            .filter { runCatching { manager.isProviderEnabled(it) }.getOrDefault(false) }
        val locations = providers.mapNotNull { provider ->
            try {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                    val result = AtomicReference<Location?>()
                    val latch = CountDownLatch(1)
                    manager.getCurrentLocation(provider, null, ContextCompat.getMainExecutor(context)) {
                        result.set(it); latch.countDown()
                    }
                    latch.await(3, TimeUnit.SECONDS)
                    result.get() ?: manager.getLastKnownLocation(provider)
                } else manager.getLastKnownLocation(provider)
            } catch (_: Exception) { null }
        }
        val now = System.currentTimeMillis()
        val location = locations.filter { now >= it.time && now - it.time <= 120_000L }.maxByOrNull { it.time } ?: return null
        return JSONObject()
            .put("latitude", location.latitude).put("longitude", location.longitude)
            .put("accuracy_m", location.accuracy.toDouble())
            .put("captured_at", Instant.ofEpochMilli(location.time).toString())
            .put("precision", if (fine) "fine" else "coarse")
    }

    fun buildObservation(
        deviceId: String,
        snapshot: MobileNetworkSnapshot,
        observationType: String = "network_snapshot",
        presenceActive: Boolean = false,
        observedAt: String = Instant.now().toString(),
        requestId: String = UUID.randomUUID().toString(),
        location: JSONObject? = null
    ): JSONObject {
        require(deviceId.isNotBlank() && deviceId.length <= 128)
        require(observationType in setOf("network_snapshot", "presence", "location_snapshot"))
        val payload = if (observationType == "location_snapshot") {
            require(location != null) { "location_snapshot requires a location" }
            JSONObject().put("platform", "android").put("location_opt_in", true).put("location", location)
        } else {
            JSONObject().put("platform", "android")
                .put("network_type", snapshot.networkType)
                .put("internet_available", snapshot.internetAvailable)
                .put("validated", snapshot.validated).put("metered", snapshot.metered)
                .put("vpn_active", snapshot.vpnActive)
        }
        if (observationType == "presence") {
            payload.put("active", presenceActive)
            payload.put("app_state", if (presenceActive) "foreground_service" else "app")
        }
        return JSONObject().put("device_id", deviceId).put("source_device_type", "mobile")
            .put("observation_type", observationType).put("schema_version", 1)
            .put("request_id", requestId).put("observed_at", observedAt).put("payload", payload)
    }

    /** Background presence calls omit location; only an explicit foreground opt-in call can send it. */
    fun publish(context: Context, deviceId: String, presenceActive: Boolean, includeLocation: Boolean = false) {
        val snapshot = collect(context)
        val observations = mutableListOf(
            buildObservation(deviceId, snapshot, "network_snapshot", presenceActive),
            buildObservation(deviceId, snapshot, "presence", presenceActive)
        )
        val enabled = includeLocation && context.getSharedPreferences("jarvis_session", Context.MODE_PRIVATE)
            .getBoolean("location_sharing_enabled", false)
        if (enabled) collectLocation(context, true)?.let { location ->
            observations += buildObservation(deviceId, snapshot, "location_snapshot", location = location)
        }
        observations.forEach { observation ->
            MobileApiClient.authenticatedRequest(context, "/v1/environment/observations", "POST", observation.toString())
        }
    }
}
