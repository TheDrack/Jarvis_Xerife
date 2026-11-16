package com.thedrack.jarvismobile

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class NetworkFlowSnapshotPayloadTest {
    private fun sampleFlow() = NetworkFlowSnapshot(
        flowId = "flow-1",
        protocol = "tcp",
        localIp = "10.0.0.2",
        localPort = 50000,
        remoteIp = "203.0.113.10",
        remotePort = 443,
        uid = 10123,
        packageNames = listOf("com.example.chat"),
        appLabel = "Example Chat",
        attributionStatus = "resolved",
        firstSeenAt = "2026-11-16T18:00:00Z",
        lastSeenAt = "2026-11-16T18:00:05Z",
        txPackets = 3,
        txBytes = 900,
        rxPackets = 4,
        rxBytes = 1200,
        closed = false,
        protocolObservations = listOf(
            NetworkProtocolObservation("tls_sni", "api.example.test", "tls_client_hello")
        )
    )

    @Test
    fun exposesVersionedFlowMetadataOnlyWhenJarvisOwnsVpnAndConsentsAreEnabled() {
        val result = NetworkFlowSnapshotPayload.build(
            runtime = VpnRuntimeState(vpnTransportActive = true, tailscaleInstalled = true, jarvisVpnActive = true),
            flowSharingEnabled = true,
            payloadMetadataEnabled = true,
            flows = listOf(sampleFlow()),
            packageVersion = { PackageVersionSnapshot("4.2.1", 42001L) }
        )

        assertEquals("jarvis", result.captureOwner)
        assertTrue(result.flowMetadataOptIn)
        assertTrue(result.payloadMetadataOptIn)
        val flow = result.flows.single()
        assertEquals("com.example.chat", flow.flow.packageNames.single())
        assertEquals("4.2.1", flow.packageVersions.single().second.versionName)
        assertEquals(42001L, flow.packageVersions.single().second.versionCode)
        assertEquals("api.example.test", flow.protocolObservations.single().value)
    }

    @Test
    fun neverClaimsVisibilityIntoAnExternalVpn() {
        val result = NetworkFlowSnapshotPayload.build(
            runtime = VpnRuntimeState(vpnTransportActive = true, tailscaleInstalled = true, jarvisVpnActive = false),
            flowSharingEnabled = true,
            payloadMetadataEnabled = true,
            flows = listOf(sampleFlow()),
            packageVersion = { null }
        )

        assertEquals("external", result.captureOwner)
        assertEquals("external_vpn_not_owned", result.captureReason)
        assertTrue(result.flows.isEmpty())
    }

    @Test
    fun doesNotExposeFlowsWhenVpnServiceFlagIsStaleAndNoVpnTransportExists() {
        val result = NetworkFlowSnapshotPayload.build(
            runtime = VpnRuntimeState(vpnTransportActive = false, tailscaleInstalled = false, jarvisVpnActive = true),
            flowSharingEnabled = true,
            payloadMetadataEnabled = true,
            flows = listOf(sampleFlow()),
            packageVersion = { null }
        )

        assertEquals("none", result.captureOwner)
        assertEquals("vpn_not_active", result.captureReason)
        assertTrue(result.flows.isEmpty())
    }

    @Test
    fun hidesProtocolObservationsWhenPayloadMetadataConsentIsOff() {
        val result = NetworkFlowSnapshotPayload.build(
            runtime = VpnRuntimeState(vpnTransportActive = true, tailscaleInstalled = false, jarvisVpnActive = true),
            flowSharingEnabled = true,
            payloadMetadataEnabled = false,
            flows = listOf(sampleFlow()),
            packageVersion = { null }
        )

        val flow = result.flows.single()
        assertTrue(flow.protocolObservations.isEmpty())
        assertFalse(result.payloadMetadataOptIn)
    }

    @Test
    fun hidesAllFlowDataWhenFlowSharingConsentIsOff() {
        val result = NetworkFlowSnapshotPayload.build(
            runtime = VpnRuntimeState(vpnTransportActive = true, tailscaleInstalled = false, jarvisVpnActive = true),
            flowSharingEnabled = false,
            payloadMetadataEnabled = true,
            flows = listOf(sampleFlow()),
            packageVersion = { null }
        )

        assertTrue(result.flows.isEmpty())
        assertEquals("flow_metadata_consent_disabled", result.captureReason)
    }
}
