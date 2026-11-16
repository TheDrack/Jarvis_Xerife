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
import org.json.JSONArray
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
    val vpnActive: Boolean,
    val vpnProvider: String = "none",
    val vpnCollectionMode: String = VpnCollectionMode.NETWORK_STATS.wireValue,
    val vpnModePreference: String = VpnModePreference.AUTO.wireValue,
    val tailscaleInstalled: Boolean = false,
    val vpnTransportActive: Boolean = vpnActive,
    val vpnTxPackets: Long = 0,
    val vpnTxBytes: Long = 0,
    val vpnRxPackets: Long = 0,
    val vpnRxBytes: Long = 0,
    val flowMetadataEnabled: Boolean = false,
    val payloadMetadataEnabled: Boolean = false,
    val flows: List<NetworkFlowSnapshot> = emptyList()
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
        val preferences = context.getSharedPreferences("jarvis_session", Context.MODE_PRIVATE)
        val preference = VpnModePreference.fromWireValue(
            preferences.getString("vpn_mode_preference", VpnModePreference.AUTO.wireValue)
        )
        val runtime = VpnStateDetector.detect(context, jarvisVpnActive = JarvisVpnService.isRunning)
        val tunnelStats = JarvisVpnService.currentStats()
        val flowMetadataEnabled = preferences.getBoolean("vpn_flow_sharing_enabled", false)
        val payloadMetadataEnabled = flowMetadataEnabled &&
            preferences.getBoolean("vpn_payload_metadata_enabled", false)
        val flows = if (flowMetadataEnabled) JarvisVpnService.currentFlows() else emptyList()
        // The Jarvis TUN engine is user-started only; AUTO never takes over a VPN in this phase.
        // Tailscale flow telemetry still requires an adapter inside the Tailscale client.
        val decision = VpnModeOrchestrator.decide(
            preference = preference,
            externalVpnActive = runtime.externalVpnActive,
            tailscaleInstalled = runtime.tailscaleInstalled,
            jarvisVpnActive = runtime.jarvisVpnActive,
            tailscaleAdapterReady = false,
            jarvisPacketEngineReady = false
        )
        val capabilities = if (manager != null) {
            manager.activeNetwork?.let { activeNetwork -> manager.getNetworkCapabilities(activeNetwork) }
        } else null
        val vpn = runtime.vpnTransportActive
        val type = when {
            vpn -> "vpn"
            capabilities?.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) == true -> "wifi"
            capabilities?.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) == true -> "cellular"
            capabilities?.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET) == true -> "ethernet"
            else -> "unknown"
        }
        return MobileNetworkSnapshot(
            networkType = type,
            internetAvailable = capabilities?.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) == true,
            validated = capabilities?.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED) == true,
            metered = capabilities?.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_METERED) != true,
            vpnActive = vpn,
            vpnProvider = decision.provider,
            vpnCollectionMode = decision.mode.wireValue,
            vpnModePreference = preference.wireValue,
            tailscaleInstalled = runtime.tailscaleInstalled,
            vpnTransportActive = vpn,
            vpnTxPackets = tunnelStats.txPackets,
            vpnTxBytes = tunnelStats.txBytes,
            vpnRxPackets = tunnelStats.rxPackets,
            vpnRxBytes = tunnelStats.rxBytes,
            flowMetadataEnabled = flowMetadataEnabled,
            payloadMetadataEnabled = payloadMetadataEnabled,
            flows = flows
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

    fun buildAppUsageObservation(
        deviceId: String,
        usage: AppUsageSnapshot,
        observedAt: String = Instant.now().toString(),
        requestId: String = UUID.randomUUID().toString()
    ): JSONObject {
        require(deviceId.isNotBlank() && deviceId.length <= 128)
        require(usage.apps.size <= 50)
        return JSONObject().put("device_id", deviceId)
            .put("source_device_type", "mobile")
            .put("observation_type", "app_usage_snapshot")
            .put("schema_version", 1)
            .put("request_id", requestId)
            .put("observed_at", observedAt)
            .put("payload", usage.toPayload())
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
                .put("vpn_provider", snapshot.vpnProvider)
                .put("vpn_collection_mode", snapshot.vpnCollectionMode)
                .put("vpn_mode_preference", snapshot.vpnModePreference)
                .put("tailscale_installed", snapshot.tailscaleInstalled)
                .put("vpn_transport_active", snapshot.vpnTransportActive)
        }
        if (observationType == "network_snapshot") {
            payload.put("flow_metadata_opt_in", snapshot.flowMetadataEnabled)
                .put("payload_metadata_opt_in", snapshot.payloadMetadataEnabled)
                .put("vpn_tunnel_stats", JSONObject()
                    .put("tx_packets", snapshot.vpnTxPackets)
                    .put("tx_bytes", snapshot.vpnTxBytes)
                    .put("rx_packets", snapshot.vpnRxPackets)
                    .put("rx_bytes", snapshot.vpnRxBytes))
        }
        if (observationType == "network_snapshot" && snapshot.flows.isNotEmpty()) {
            val flowLimit = if (snapshot.payloadMetadataEnabled) 15 else FlowAttributionCollector.DEFAULT_SNAPSHOT_LIMIT
            payload.put("flows", JSONArray().apply {
                snapshot.flows.take(flowLimit).forEach { flow ->
                    put(JSONObject()
                        .put("flow_id", flow.flowId)
                        .put("protocol", flow.protocol)
                        .put("local_ip", flow.localIp)
                        .put("local_port", flow.localPort)
                        .put("remote_ip", flow.remoteIp)
                        .put("remote_port", flow.remotePort)
                        .put("uid", flow.uid ?: JSONObject.NULL)
                        .put("package_names", JSONArray(flow.packageNames.take(2)))
                        .put("app_label", flow.appLabel ?: JSONObject.NULL)
                        .put("attribution_status", flow.attributionStatus)
                        .put("first_seen_at", flow.firstSeenAt)
                        .put("last_seen_at", flow.lastSeenAt)
                        .put("tx_packets", flow.txPackets)
                        .put("tx_bytes", flow.txBytes)
                        .put("rx_packets", flow.rxPackets)
                        .put("rx_bytes", flow.rxBytes)
                        .put("closed", flow.closed)
                        .put("protocol_observations", if (snapshot.payloadMetadataEnabled) {
                            JSONArray().apply {
                                flow.protocolObservations.take(3).forEach { observation ->
                                    put(JSONObject()
                                        .put("kind", observation.kind)
                                        .put("value", observation.value)
                                        .put("source", observation.source))
                                }
                            }
                        } else JSONArray()))
                }
            })
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
        val preferences = context.getSharedPreferences("jarvis_session", Context.MODE_PRIVATE)
        val appUsageEnabled = preferences.getBoolean("app_usage_sharing_enabled", false)
        val selectedPackages = preferences.getString("app_usage_package_filter", "")
            .orEmpty().split(Regex("[,;\\s]+"))
            .map(String::trim).filter(String::isNotEmpty).toSet()
        if (AppUsageStatsCollector.isAuthorized(appUsageEnabled, AppUsageStatsCollector.hasUsageAccess(context))) {
            AppUsageStatsCollector.collect(context, selectedPackages = selectedPackages)?.let { usage ->
                observations += buildAppUsageObservation(deviceId, usage)
            }
        }
        observations.forEach { observation ->
            MobilePushClient.authenticatedRequest(context, "/v1/environment/observations", "POST", observation.toString())
        }
    }
}
