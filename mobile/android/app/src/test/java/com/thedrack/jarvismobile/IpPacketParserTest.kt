package com.thedrack.jarvismobile

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertNotNull
import org.junit.Test

class IpPacketParserTest {
    @Test
    fun parsesIpv4TcpTupleAndTotalLength() {
        val packet = ipv4Packet(
            protocol = 6,
            source = byteArrayOf(10, 0, 0, 2),
            destination = byteArrayOf(1, 1, 1, 1),
            sourcePort = 49152,
            destinationPort = 443
        )

        val parsed = IpPacketParser.parse(packet)

        assertNotNull(parsed)
        assertEquals("tcp", parsed!!.protocol)
        assertEquals("10.0.0.2", parsed.sourceAddress.hostAddress)
        assertEquals(49152, parsed.sourcePort)
        assertEquals("1.1.1.1", parsed.destinationAddress.hostAddress)
        assertEquals(443, parsed.destinationPort)
        assertEquals(packet.size, parsed.packetBytes)
    }

    @Test
    fun parsesIpv4UdpWithHeaderOptions() {
        val packet = ipv4Packet(
            protocol = 17,
            source = byteArrayOf(192.toByte(), 168.toByte(), 1, 20),
            destination = byteArrayOf(8, 8, 8, 8),
            sourcePort = 53000,
            destinationPort = 53,
            ipv4OptionsBytes = 8
        )

        val parsed = IpPacketParser.parse(packet)

        assertNotNull(parsed)
        assertEquals("udp", parsed!!.protocol)
        assertEquals(53000, parsed.sourcePort)
        assertEquals(53, parsed.destinationPort)
    }

    @Test
    fun ignoresNonInitialIpv4FragmentsAndUnsupportedProtocols() {
        val fragment = ipv4Packet(
            protocol = 17,
            source = byteArrayOf(10, 0, 0, 2),
            destination = byteArrayOf(8, 8, 8, 8),
            sourcePort = 53000,
            destinationPort = 53,
            fragmentOffset = 1
        )
        val icmp = ipv4Packet(
            protocol = 1,
            source = byteArrayOf(10, 0, 0, 2),
            destination = byteArrayOf(8, 8, 8, 8),
            sourcePort = 0,
            destinationPort = 0
        )

        assertNull(IpPacketParser.parse(fragment))
        assertNull(IpPacketParser.parse(icmp))
    }

    @Test
    fun parsesIpv6UdpAfterHopByHopExtensionHeader() {
        val packet = ipv6PacketWithHopByHopUdp()

        val parsed = IpPacketParser.parse(packet)

        assertNotNull(parsed)
        assertEquals("udp", parsed!!.protocol)
        assertEquals("2001:db8::1", parsed.sourceAddress.hostAddress)
        assertEquals(55000, parsed.sourcePort)
        assertEquals("2001:db8::2", parsed.destinationAddress.hostAddress)
        assertEquals(443, parsed.destinationPort)
    }

    @Test
    fun parsesIpv6TcpAfterInitialFragmentHeader() {
        val packet = ipv6PacketWithFragmentTcp(fragmentOffset = 0)

        val parsed = IpPacketParser.parse(packet)

        assertNotNull(parsed)
        assertEquals("tcp", parsed!!.protocol)
        assertEquals(42000, parsed.sourcePort)
        assertEquals(443, parsed.destinationPort)
    }

    @Test
    fun ignoresNonInitialIpv6FragmentsAndMalformedLengths() {
        val fragment = ipv6PacketWithFragmentTcp(fragmentOffset = 1)
        val malformed = ipv4Packet(
            protocol = 6,
            source = byteArrayOf(10, 0, 0, 2),
            destination = byteArrayOf(1, 1, 1, 1),
            sourcePort = 49152,
            destinationPort = 443
        ).also { it[2] = 0; it[3] = 10 }

        assertNull(IpPacketParser.parse(fragment))
        assertNull(IpPacketParser.parse(malformed))
        assertNull(IpPacketParser.parse(byteArrayOf(0x60)))
    }

    private fun ipv4Packet(
        protocol: Int,
        source: ByteArray,
        destination: ByteArray,
        sourcePort: Int,
        destinationPort: Int,
        ipv4OptionsBytes: Int = 0,
        fragmentOffset: Int = 0
    ): ByteArray {
        val headerLength = 20 + ipv4OptionsBytes
        val transportLength = if (protocol == 6) 20 else 8
        val payloadLength = 4
        val totalLength = headerLength + transportLength + payloadLength
        val packet = ByteArray(totalLength)
        packet[0] = (0x40 or (headerLength / 4)).toByte()
        packet[2] = (totalLength shr 8).toByte()
        packet[3] = totalLength.toByte()
        packet[6] = (fragmentOffset shr 8).toByte()
        packet[7] = fragmentOffset.toByte()
        packet[9] = protocol.toByte()
        source.copyInto(packet, 12)
        destination.copyInto(packet, 16)
        packet[headerLength] = (sourcePort shr 8).toByte()
        packet[headerLength + 1] = sourcePort.toByte()
        packet[headerLength + 2] = (destinationPort shr 8).toByte()
        packet[headerLength + 3] = destinationPort.toByte()
        return packet
    }

    private fun ipv6PacketWithHopByHopUdp(): ByteArray {
        val packet = ByteArray(40 + 8 + 8 + 4)
        packet[0] = 0x60
        val payloadLength = packet.size - 40
        packet[4] = (payloadLength shr 8).toByte()
        packet[5] = payloadLength.toByte()
        packet[6] = 0 // Hop-by-hop extension.
        val source = byteArrayOf(
            0x20, 0x01, 0x0d, 0xb8.toByte(), 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 1
        )
        val destination = source.copyOf().also { it[15] = 2 }
        source.copyInto(packet, 8)
        destination.copyInto(packet, 24)
        packet[40] = 17 // Next header: UDP.
        packet[41] = 0 // Extension length: 8 bytes.
        val udpOffset = 48
        packet[udpOffset] = (55000 shr 8).toByte()
        packet[udpOffset + 1] = 55000.toByte()
        packet[udpOffset + 2] = 0x01
        packet[udpOffset + 3] = 0xbb.toByte()
        packet[udpOffset + 4] = 0
        packet[udpOffset + 5] = 12
        return packet
    }

    private fun ipv6PacketWithFragmentTcp(fragmentOffset: Int): ByteArray {
        val packet = ByteArray(40 + 8 + 20 + 4)
        packet[0] = 0x60
        val payloadLength = packet.size - 40
        packet[4] = (payloadLength shr 8).toByte()
        packet[5] = payloadLength.toByte()
        packet[6] = 44 // Fragment extension.
        val source = byteArrayOf(
            0x20, 0x01, 0x0d, 0xb8.toByte(), 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 1
        )
        val destination = source.copyOf().also { it[15] = 2 }
        source.copyInto(packet, 8)
        destination.copyInto(packet, 24)
        packet[40] = 6 // Next header: TCP.
        val fragmentField = fragmentOffset shl 3
        packet[42] = (fragmentField shr 8).toByte()
        packet[43] = fragmentField.toByte()
        val tcpOffset = 48
        packet[tcpOffset] = (42000 shr 8).toByte()
        packet[tcpOffset + 1] = 42000.toByte()
        packet[tcpOffset + 2] = 0x01
        packet[tcpOffset + 3] = 0xbb.toByte()
        return packet
    }
}
