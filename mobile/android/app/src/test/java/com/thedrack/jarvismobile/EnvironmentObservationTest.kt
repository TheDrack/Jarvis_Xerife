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
