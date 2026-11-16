package com.thedrack.jarvismobile

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class EnvironmentObservationTest {
    private val snapshot = MobileNetworkSnapshot(
        networkType = "wifi",
        internetAvailable = true,
        validated = true,
        metered = false,
        vpnActive = false
    )

    @Test
    fun payloadUsesVersionedMobileContractAndUniqueRequestIds() {
        val first = EnvironmentObservationPublisher.buildObservation(
            "phone-1", snapshot, observedAt = "2026-10-29T12:00:00Z", requestId = "req-1"
        )
        val second = EnvironmentObservationPublisher.buildObservation(
            "phone-1", snapshot, observedAt = "2026-10-29T12:00:00Z", requestId = "req-2"
        )
        assertEquals("mobile", first.getString("source_device_type"))
        assertEquals("network_snapshot", first.getString("observation_type"))
        assertEquals(1, first.getInt("schema_version"))
        assertEquals("req-1", first.getString("request_id"))
        assertTrue(first.getJSONObject("payload").getBoolean("validated"))
        assertFalse(first.getJSONObject("payload").has("ssid"))
        assertFalse(first.getJSONObject("payload").has("latitude"))
        assertTrue(first.getString("request_id") != second.getString("request_id"))
    }

    @Test
    fun networkPayloadIncludesDynamicVpnSelectionWithoutClaimingPacketCapture() {
        val vpnSnapshot = snapshot.copy(
            vpnActive = true,
            vpnProvider = "external_unknown",
            vpnCollectionMode = VpnCollectionMode.EXTERNAL_VPN_STATS.wireValue,
            vpnModePreference = VpnModePreference.AUTO.wireValue,
            tailscaleInstalled = true,
            vpnTransportActive = true
        )
        val payload = EnvironmentObservationPublisher.buildObservation(
            "phone-1", vpnSnapshot, requestId = "req-vpn"
        ).getJSONObject("payload")

        assertTrue(payload.getBoolean("vpn_active"))
        assertEquals("external_unknown", payload.getString("vpn_provider"))
        assertEquals("external_vpn_stats", payload.getString("vpn_collection_mode"))
        assertEquals("auto", payload.getString("vpn_mode_preference"))
        assertTrue(payload.getBoolean("tailscale_installed"))
        assertTrue(payload.getBoolean("vpn_transport_active"))
    }

    @Test
    fun networkPayloadPublishesOnlyAggregateHevTunnelCounters() {
        val vpnSnapshot = snapshot.copy(
            vpnActive = true,
            vpnProvider = "jarvis",
            vpnCollectionMode = VpnCollectionMode.JARVIS_VPN.wireValue,
            vpnTxPackets = 7,
            vpnTxBytes = 1024,
            vpnRxPackets = 9,
            vpnRxBytes = 2048
        )
        val payload = EnvironmentObservationPublisher.buildObservation(
            "phone-1", vpnSnapshot, requestId = "req-tunnel-stats"
        ).getJSONObject("payload")
        val stats = payload.getJSONObject("vpn_tunnel_stats")

        assertEquals(7L, stats.getLong("tx_packets"))
        assertEquals(1024L, stats.getLong("tx_bytes"))
        assertEquals(9L, stats.getLong("rx_packets"))
        assertEquals(2048L, stats.getLong("rx_bytes"))
        assertFalse(payload.has("packet_payload"))
        assertFalse(payload.has("message_body"))
    }

    @Test
    fun networkPayloadPublishesFlowTupleUidAndCountersWithoutPacketContents() {
        val flow = NetworkFlowSnapshot(
            flowId = "f68e4d54-2a93-4b52-bf6e-0f7f1ac30d20",
            protocol = "tcp",
            localIp = "10.0.0.2",
            localPort = 49152,
            remoteIp = "1.1.1.1",
            remotePort = 443,
            uid = 10123,
            packageNames = listOf("com.example.app"),
            appLabel = "Example",
            attributionStatus = "resolved",
            firstSeenAt = "2026-11-16T10:00:00Z",
            lastSeenAt = "2026-11-16T10:00:02Z",
            txPackets = 2,
            txBytes = 120,
            rxPackets = 3,
            rxBytes = 180,
            closed = false
        )
        val networkPayload = EnvironmentObservationPublisher.buildObservation(
            "phone-1", snapshot.copy(flows = listOf(flow)), requestId = "req-flow"
        ).getJSONObject("payload")
        val jsonFlow = networkPayload.getJSONArray("flows").getJSONObject(0)

        assertEquals("tcp", jsonFlow.getString("protocol"))
        assertEquals("10.0.0.2", jsonFlow.getString("local_ip"))
        assertEquals(49152, jsonFlow.getInt("local_port"))
        assertEquals("1.1.1.1", jsonFlow.getString("remote_ip"))
        assertEquals(443, jsonFlow.getInt("remote_port"))
        assertEquals(10123, jsonFlow.getInt("uid"))
        assertEquals("com.example.app", jsonFlow.getJSONArray("package_names").getString(0))
        assertEquals("resolved", jsonFlow.getString("attribution_status"))
        assertEquals(120L, jsonFlow.getLong("tx_bytes"))
        assertEquals(180L, jsonFlow.getLong("rx_bytes"))
        assertFalse(networkPayload.has("packet_payload"))
        assertFalse(networkPayload.has("message_body"))

        val presencePayload = EnvironmentObservationPublisher.buildObservation(
            "phone-1", snapshot.copy(flows = listOf(flow)), observationType = "presence"
        ).getJSONObject("payload")
        assertFalse(presencePayload.has("flows"))
    }

    @Test
    fun locationPayloadIsSeparateAndOptIn() {
        val location = JSONObject().put("latitude", -27.5954).put("longitude", -48.5480)
            .put("accuracy_m", 18.0).put("captured_at", "2026-10-29T12:00:00Z").put("precision", "fine")
        val json = EnvironmentObservationPublisher.buildObservation(
            "phone-1", snapshot, observationType = "location_snapshot",
            observedAt = "2026-10-29T12:00:00Z", requestId = "req-location", location = location
        )
        assertEquals("location_snapshot", json.getString("observation_type"))
        assertTrue(json.getJSONObject("payload").getBoolean("location_opt_in"))
        assertEquals(-27.5954, json.getJSONObject("payload").getJSONObject("location").getDouble("latitude"), 0.0001)
    }

    @Test
    fun presencePayloadStatesServiceActivityWithoutSensitiveFields() {
        val json: JSONObject = EnvironmentObservationPublisher.buildObservation(
            "phone-1", snapshot, observationType = "presence", presenceActive = true,
            observedAt = "2026-10-29T12:00:00Z", requestId = "req-presence"
        )
        val payload = json.getJSONObject("payload")
        assertTrue(payload.getBoolean("active"))
        assertEquals("foreground_service", payload.getString("app_state"))
        assertFalse(payload.has("ssid"))
        assertFalse(payload.has("location"))
    }

    @Test(expected = IllegalArgumentException::class)
    fun rejectsInvalidDeviceId() {
        EnvironmentObservationPublisher.buildObservation("", snapshot)
    }
}

class AppUsageObservationTest {
    @Test
    fun collectionRequiresBothUserConsentAndAndroidUsageAccess() {
        assertFalse(AppUsageStatsCollector.isAuthorized(false, false))
        assertFalse(AppUsageStatsCollector.isAuthorized(false, true))
        assertFalse(AppUsageStatsCollector.isAuthorized(true, false))
        assertTrue(AppUsageStatsCollector.isAuthorized(true, true))
    }

    @Test
    fun appUsagePayloadIncludesResolvedPackageIdentityWithoutChangingUidCounters() {
        val snapshot = AppUsageSnapshot(
            windowStart = "2026-11-16T10:00:00Z",
            windowEnd = "2026-11-16T11:00:00Z",
            apps = listOf(
                AppUsageEntry(
                    uid = 10123,
                    packageNames = listOf("com.example.app"),
                    wifiRxBytes = 100L,
                    wifiTxBytes = 50L,
                    mobileRxBytes = 20L,
                    mobileTxBytes = 10L,
                    packageIdentities = listOf(
                        AppPackageIdentity("com.example.app", "Example", false)
                    )
                )
            )
        )

        val app = snapshot.toPayload().getJSONArray("apps").getJSONObject(0)
        val identity = app.getJSONArray("packages").getJSONObject(0)
        assertEquals("com.example.app", identity.getString("package_name"))
        assertEquals("Example", identity.getString("app_label"))
        assertFalse(identity.getBoolean("is_system_app"))
        assertEquals(100L, app.getJSONObject("wifi").getLong("rx_bytes"))
        assertEquals(10L, app.getJSONObject("mobile").getLong("tx_bytes"))
    }

    @Test
    fun selectedPackageFilterKeepsOnlyMatchingUidEntriesAndEmptyMeansAll() {
        val entries = listOf(
            AppUsageEntry(10123, listOf("com.example.one"), 10, 0, 0, 0),
            AppUsageEntry(10124, listOf("com.example.two"), 20, 0, 0, 0),
            AppUsageEntry(10125, listOf("com.example.shared", "com.example.companion"), 30, 0, 0, 0)
        )

        assertEquals(3, AppUsageStatsCollector.filterEntries(entries, emptySet()).size)
        assertEquals(2, AppUsageStatsCollector.filterEntries(entries, setOf("com.example.two", "com.example.companion")).size)
        assertEquals(10125, AppUsageStatsCollector.filterEntries(entries, setOf("com.example.companion")).single().uid)
    }

    @Test
    fun appUsagePayloadContainsOnlyOptedInAggregateCounters() {
        val snapshot = AppUsageSnapshot(
            windowStart = "2026-11-16T10:00:00Z",
            windowEnd = "2026-11-16T11:00:00Z",
            apps = listOf(
                AppUsageEntry(10123, listOf("com.example.app"), 100L, 50L, 20L, 10L)
            )
        )
        val observation = EnvironmentObservationPublisher.buildAppUsageObservation(
            "phone-1", snapshot, observedAt = "2026-11-16T11:00:00Z", requestId = "req-usage"
        )
        val payload = observation.getJSONObject("payload")
        val app = payload.getJSONArray("apps").getJSONObject(0)
        assertEquals("app_usage_snapshot", observation.getString("observation_type"))
        assertTrue(payload.getBoolean("usage_access_opt_in"))
        assertEquals(100L, app.getJSONObject("wifi").getLong("rx_bytes"))
        assertEquals(10L, app.getJSONObject("mobile").getLong("tx_bytes"))
        assertFalse(payload.has("url"))
        assertFalse(payload.has("destination"))
        assertFalse(payload.has("payload"))
    }

    @Test(expected = IllegalArgumentException::class)
    fun appUsageObservationRejectsMoreThanFiftyApps() {
        val entries = (1..51).map { uid -> AppUsageEntry(uid, emptyList(), 0L, 0L, 0L, 0L) }
        EnvironmentObservationPublisher.buildAppUsageObservation(
            "phone-1", AppUsageSnapshot("2026-11-16T10:00:00Z", "2026-11-16T11:00:00Z", entries)
        )
    }
}
