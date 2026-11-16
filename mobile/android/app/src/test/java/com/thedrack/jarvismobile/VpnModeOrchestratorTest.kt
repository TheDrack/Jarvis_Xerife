package com.thedrack.jarvismobile

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class VpnModeOrchestratorTest {
    @Test
    fun autoUsesTailscaleAdapterWhenExternalVpnAndTailscaleArePresent() {
        val decision = VpnModeOrchestrator.decide(
            preference = VpnModePreference.AUTO,
            externalVpnActive = true,
            tailscaleInstalled = true,
            jarvisVpnActive = false,
            tailscaleAdapterReady = true,
            jarvisPacketEngineReady = true
        )

        assertEquals(VpnCollectionMode.TAILSCALE, decision.mode)
        assertEquals("tailscale", decision.provider)
    }

    @Test
    fun autoNeverStartsJarvisVpnOverAnExistingExternalVpn() {
        val decision = VpnModeOrchestrator.decide(
            preference = VpnModePreference.AUTO,
            externalVpnActive = true,
            tailscaleInstalled = false,
            jarvisVpnActive = false,
            tailscaleAdapterReady = false,
            jarvisPacketEngineReady = true
        )

        assertEquals(VpnCollectionMode.EXTERNAL_VPN_UNSUPPORTED, decision.mode)
        assertFalse(decision.mayStartJarvisVpn)
    }

    @Test
    fun autoSelectsJarvisWhenNoOtherVpnIsActiveAndEngineIsReady() {
        val decision = VpnModeOrchestrator.decide(
            preference = VpnModePreference.AUTO,
            externalVpnActive = false,
            tailscaleInstalled = false,
            jarvisVpnActive = false,
            tailscaleAdapterReady = false,
            jarvisPacketEngineReady = true
        )

        assertEquals(VpnCollectionMode.JARVIS_VPN, decision.mode)
        assertTrue(decision.mayStartJarvisVpn)
    }

    @Test
    fun autoFallsBackToAggregateStatsUntilPacketEngineIsReady() {
        val decision = VpnModeOrchestrator.decide(
            preference = VpnModePreference.AUTO,
            externalVpnActive = false,
            tailscaleInstalled = false,
            jarvisVpnActive = false,
            tailscaleAdapterReady = false,
            jarvisPacketEngineReady = false
        )

        assertEquals(VpnCollectionMode.NETWORK_STATS, decision.mode)
        assertFalse(decision.mayStartJarvisVpn)
    }

    @Test
    fun tailscalePreferenceWaitsInsteadOfStartingJarvisVpn() {
        val decision = VpnModeOrchestrator.decide(
            preference = VpnModePreference.TAILSCALE,
            externalVpnActive = false,
            tailscaleInstalled = true,
            jarvisVpnActive = false,
            tailscaleAdapterReady = false,
            jarvisPacketEngineReady = true
        )

        assertEquals(VpnCollectionMode.WAITING_FOR_TAILSCALE, decision.mode)
        assertFalse(decision.mayStartJarvisVpn)
    }

    @Test
    fun activeJarvisVpnWinsOnlyWhenPreferenceAllowsIt() {
        val automatic = VpnModeOrchestrator.decide(
            preference = VpnModePreference.AUTO,
            externalVpnActive = false,
            tailscaleInstalled = true,
            jarvisVpnActive = true,
            tailscaleAdapterReady = false,
            jarvisPacketEngineReady = true
        )
        val tailscalePreferred = VpnModeOrchestrator.decide(
            preference = VpnModePreference.TAILSCALE,
            externalVpnActive = false,
            tailscaleInstalled = true,
            jarvisVpnActive = true,
            tailscaleAdapterReady = false,
            jarvisPacketEngineReady = true
        )

        assertEquals(VpnCollectionMode.JARVIS_VPN, automatic.mode)
        assertEquals(VpnCollectionMode.WAITING_FOR_TAILSCALE, tailscalePreferred.mode)
    }
}
