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
