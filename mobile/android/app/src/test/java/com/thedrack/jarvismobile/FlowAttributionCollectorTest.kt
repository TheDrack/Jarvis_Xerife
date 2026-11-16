package com.thedrack.jarvismobile

import java.net.InetAddress
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class FlowAttributionCollectorTest {
    @Test
    fun mapsOutboundAndInboundPacketsToOneAndroidUidFlow() {
        var now = 1_000L
        val resolvedTuples = mutableListOf<List<Any>>()
        val collector = FlowAttributionCollector(
            ownerResolver = ConnectionOwnerResolver { protocol, local, localPort, remote, remotePort ->
                resolvedTuples += listOf(protocol, local.hostAddress, localPort, remote.hostAddress, remotePort)
                10123
            },
            packageResolver = PackageIdentityResolver {
                listOf(AppPackageIdentity("com.example.chat", "Example Chat", false))
            },
            clock = { now }
        )

        collector.record(packet(OUTBOUND, tcpFlags = 0x02, packetBytes = 60), FlowPacketDirection.OUTBOUND)
        now += 100
        collector.record(packet(INBOUND, packetBytes = 52), FlowPacketDirection.INBOUND)
        now += 100
        collector.record(packet(OUTBOUND, tcpFlags = 0x10, packetBytes = 48), FlowPacketDirection.OUTBOUND)

        val flow = collector.snapshot().single()
        assertEquals("tcp", flow.protocol)
        assertEquals("10.0.0.2", flow.localIp)
        assertEquals(49152, flow.localPort)
        assertEquals("1.1.1.1", flow.remoteIp)
        assertEquals(443, flow.remotePort)
        assertEquals(10123, flow.uid)
        assertEquals(listOf("com.example.chat"), flow.packageNames)
        assertEquals("Example Chat", flow.appLabel)
        assertEquals("resolved", flow.attributionStatus)
        assertEquals(2L, flow.txPackets)
        assertEquals(108L, flow.txBytes)
        assertEquals(1L, flow.rxPackets)
        assertEquals(52L, flow.rxBytes)
        assertEquals(1, resolvedTuples.size)
        assertEquals(listOf(6, "10.0.0.2", 49152, "1.1.1.1", 443), resolvedTuples.single())
    }

    @Test
    fun marksSharedUidAsAmbiguousInsteadOfClaimingOneApplication() {
        val collector = FlowAttributionCollector(
            ownerResolver = ConnectionOwnerResolver { _, _, _, _, _ -> 10123 },
            packageResolver = PackageIdentityResolver {
                listOf(
                    AppPackageIdentity("com.example.primary", "Primary", false),
                    AppPackageIdentity("com.example.companion", "Companion", false)
                )
            },
            clock = { 1_500L }
        )

        collector.record(packet(OUTBOUND, tcpFlags = 0x02), FlowPacketDirection.OUTBOUND)

        val flow = collector.snapshot().single()
        assertEquals("shared_uid", flow.attributionStatus)
        assertEquals(
            listOf("com.example.companion", "com.example.primary"),
            flow.packageNames
        )
        assertNull(flow.appLabel)
    }

    @Test
    fun recordsUnresolvedUidWithoutInventingPackageIdentity() {
        val collector = FlowAttributionCollector(
            ownerResolver = ConnectionOwnerResolver { _, _, _, _, _ -> -1 },
            packageResolver = PackageIdentityResolver { emptyList() },
            clock = { 2_000L }
        )

        collector.record(packet(OUTBOUND, tcpFlags = 0x02), FlowPacketDirection.OUTBOUND)

        val flow = collector.snapshot().single()
        assertNull(flow.uid)
        assertTrue(flow.packageNames.isEmpty())
        assertNull(flow.appLabel)
        assertEquals("unresolved", flow.attributionStatus)
    }

    @Test
    fun retriesTransientUidMissesOnLaterPackets() {
        var now = 2_500L
        var attempts = 0
        val collector = FlowAttributionCollector(
            ownerResolver = ConnectionOwnerResolver { _, _, _, _, _ ->
                attempts += 1
                if (attempts == 1) -1 else 10022
            },
            packageResolver = PackageIdentityResolver {
                listOf(AppPackageIdentity("com.example.retry", "Retry App", false))
            },
            clock = { now }
        )

        collector.record(packet(OUTBOUND, tcpFlags = 0x02), FlowPacketDirection.OUTBOUND)
        assertNull(collector.snapshot().single().uid)

        now += 300
        collector.record(packet(OUTBOUND, tcpFlags = 0x10), FlowPacketDirection.OUTBOUND)

        val flow = collector.snapshot().single()
        assertEquals(2, attempts)
        assertEquals(10022, flow.uid)
        assertEquals("resolved", flow.attributionStatus)
    }

    @Test
    fun retransmittedSynKeepsSameFlowAndNewSynAfterResetCreatesNewFlow() {
        var now = 3_000L
        val collector = FlowAttributionCollector(
            ownerResolver = ConnectionOwnerResolver { _, _, _, _, _ -> 10001 },
            packageResolver = PackageIdentityResolver { emptyList() },
            clock = { now }
        )

        collector.record(packet(OUTBOUND, tcpFlags = 0x02), FlowPacketDirection.OUTBOUND)
        val firstId = collector.snapshot().single().flowId
        now += 100
        collector.record(packet(OUTBOUND, tcpFlags = 0x02), FlowPacketDirection.OUTBOUND)
        assertEquals(firstId, collector.snapshot().single().flowId)

        now += 100
        collector.record(packet(OUTBOUND, tcpFlags = 0x04), FlowPacketDirection.OUTBOUND)
        now += 100
        collector.record(packet(OUTBOUND, tcpFlags = 0x02), FlowPacketDirection.OUTBOUND)
        assertNotEquals(firstId, collector.snapshot().single().flowId)
        assertFalse(collector.snapshot().single().closed)
    }

    @Test
    fun expiresIdleFlowsAndBoundsSnapshotSize() {
        var now = 10_000L
        val collector = FlowAttributionCollector(
            ownerResolver = ConnectionOwnerResolver { _, _, _, _, _ -> -1 },
            packageResolver = PackageIdentityResolver { emptyList() },
            clock = { now },
            maxFlows = 3,
            maxAgeMillis = 1_000,
            idleSessionMillis = 500
        )

        repeat(4) { index ->
            collector.record(
                packet(
                    OUTBOUND,
                    sourcePort = 40000 + index,
                    destinationPort = 443,
                    packetBytes = 60
                ),
                FlowPacketDirection.OUTBOUND
            )
        }
        assertEquals(3, collector.snapshot().size)

        now += 2_000
        assertTrue(collector.snapshot().isEmpty())
    }

    @Test
    fun revokingFlowConsentImmediatelyClearsAndStopsMetadataCollection() {
        val collector = FlowAttributionCollector(
            ownerResolver = ConnectionOwnerResolver { _, _, _, _, _ -> 10001 },
            packageResolver = PackageIdentityResolver { emptyList() },
            clock = { 6_000L }
        )
        collector.record(packet(OUTBOUND, tcpFlags = 0x02), FlowPacketDirection.OUTBOUND)
        assertEquals(1, collector.snapshot().size)

        collector.setEnabled(false)
        assertTrue(collector.snapshot().isEmpty())
        collector.record(packet(OUTBOUND, tcpFlags = 0x10), FlowPacketDirection.OUTBOUND)
        assertTrue(collector.snapshot().isEmpty())

        collector.setEnabled(true)
        assertTrue(collector.snapshot().isEmpty())
        collector.record(packet(OUTBOUND, tcpFlags = 0x02), FlowPacketDirection.OUTBOUND)
        assertEquals(1, collector.snapshot().size)
    }

    @Test
    fun reverseDirectionNormalizesUdpFlowToOriginalAppTuple() {
        val collector = FlowAttributionCollector(
            ownerResolver = ConnectionOwnerResolver { _, _, _, _, _ -> 10055 },
            packageResolver = PackageIdentityResolver { emptyList() },
            clock = { 5_000L }
        )
        val outbound = packet(
            OUTBOUND,
            protocol = "udp",
            protocolNumber = 17,
            sourcePort = 53000,
            destinationPort = 53,
            packetBytes = 40
        )
        val inbound = packet(
            INBOUND,
            protocol = "udp",
            protocolNumber = 17,
            sourcePort = 53,
            destinationPort = 53000,
            packetBytes = 72
        )

        collector.record(outbound, FlowPacketDirection.OUTBOUND)
        collector.record(inbound, FlowPacketDirection.INBOUND)

        val flow = collector.snapshot().single()
        assertEquals("udp", flow.protocol)
        assertEquals(53000, flow.localPort)
        assertEquals(53, flow.remotePort)
        assertEquals(1L, flow.txPackets)
        assertEquals(40L, flow.txBytes)
        assertEquals(1L, flow.rxPackets)
        assertEquals(72L, flow.rxBytes)
    }

    @Test
    fun protocolMetadataRequiresSeparateOptInAndIsClearedWhenRevoked() {
        val dnsPayload = byteArrayOf(
            0x12, 0x34, 0x01, 0x00, 0x00, 0x01,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
            3, 'a'.code.toByte(), 'p'.code.toByte(), 'i'.code.toByte(),
            7, 'e'.code.toByte(), 'x'.code.toByte(), 'a'.code.toByte(),
            'm'.code.toByte(), 'p'.code.toByte(), 'l'.code.toByte(), 'e'.code.toByte(),
            3, 'c'.code.toByte(), 'o'.code.toByte(), 'm'.code.toByte(), 0,
            0, 1, 0, 1
        )
        val dnsPacket = packet(
            OUTBOUND,
            protocol = "udp",
            protocolNumber = 17,
            sourcePort = 53000,
            destinationPort = 53
        ).copy(payloadOffset = 0, payloadLength = dnsPayload.size)

        val disabledByDefault = FlowAttributionCollector(
            ownerResolver = ConnectionOwnerResolver { _, _, _, _, _ -> 10001 },
            packageResolver = PackageIdentityResolver { emptyList() },
            clock = { 7_000L }
        )
        disabledByDefault.record(dnsPacket, FlowPacketDirection.OUTBOUND, dnsPayload)
        assertTrue(disabledByDefault.snapshot().single().protocolObservations.isEmpty())

        val enabled = FlowAttributionCollector(
            ownerResolver = ConnectionOwnerResolver { _, _, _, _, _ -> 10001 },
            packageResolver = PackageIdentityResolver { emptyList() },
            clock = { 7_000L },
            payloadMetadataEnabled = true
        )
        enabled.record(dnsPacket, FlowPacketDirection.OUTBOUND, dnsPayload)
        assertEquals(
            listOf(NetworkProtocolObservation("dns_query", "api.example.com", "dns")),
            enabled.snapshot().single().protocolObservations
        )

        enabled.setPayloadMetadataEnabled(false)
        assertTrue(enabled.snapshot().single().protocolObservations.isEmpty())
        enabled.record(dnsPacket, FlowPacketDirection.OUTBOUND, dnsPayload)
        assertTrue(enabled.snapshot().single().protocolObservations.isEmpty())
    }

    @Test
    fun reconstructsSplitHttpHeadersBeforeExtractingHostMetadata() {
        val collector = FlowAttributionCollector(
            ownerResolver = ConnectionOwnerResolver { _, _, _, _, _ -> 10001 },
            packageResolver = PackageIdentityResolver { emptyList() },
            clock = { 9_000L },
            payloadMetadataEnabled = true
        )
        val request = "GET /private HTTP/1.1\\r\\nHost: api.example.com\\r\\n\\r\\n"
            .toByteArray(Charsets.US_ASCII)
        val split = 19
        val first = request.copyOfRange(0, split)
        val second = request.copyOfRange(split, request.size)
        val firstPacket = packet(
            OUTBOUND,
            sourcePort = 49152,
            destinationPort = 80
        ).copy(payloadOffset = 0, payloadLength = first.size, tcpSequenceNumber = 100L)
        val secondPacket = firstPacket.copy(
            payloadLength = second.size,
            tcpSequenceNumber = 100L + first.size
        )

        collector.record(firstPacket, FlowPacketDirection.OUTBOUND, first)
        assertTrue(collector.snapshot().single().protocolObservations.isEmpty())

        collector.record(secondPacket, FlowPacketDirection.OUTBOUND, second)

        assertEquals(
            listOf(NetworkProtocolObservation("http_host", "api.example.com", "http")),
            collector.snapshot().single().protocolObservations
        )
    }

    private fun packet(
        direction: Int,
        protocol: String = "tcp",
        protocolNumber: Int = 6,
        sourcePort: Int = if (direction == OUTBOUND) 49152 else 443,
        destinationPort: Int = if (direction == OUTBOUND) 443 else 49152,
        packetBytes: Int = 60,
        tcpFlags: Int? = null,
        tcpSequenceNumber: Long? = null
    ) = ParsedIpPacket(
        protocol = protocol,
        protocolNumber = protocolNumber,
        sourceAddress = InetAddress.getByName(if (direction == OUTBOUND) "10.0.0.2" else "1.1.1.1"),
        sourcePort = sourcePort,
        destinationAddress = InetAddress.getByName(if (direction == OUTBOUND) "1.1.1.1" else "10.0.0.2"),
        destinationPort = destinationPort,
        packetBytes = packetBytes,
        tcpFlags = tcpFlags,
        tcpSequenceNumber = tcpSequenceNumber
    )

    private companion object {
        const val OUTBOUND = 1
        const val INBOUND = 2
    }
}
