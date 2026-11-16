package com.thedrack.jarvismobile

import java.net.InetAddress

/** Parsed transport tuple. Packet payload bytes are never copied or retained. */
data class ParsedIpPacket(
    val protocol: String,
    val protocolNumber: Int,
    val sourceAddress: InetAddress,
    val sourcePort: Int,
    val destinationAddress: InetAddress,
    val destinationPort: Int,
    val packetBytes: Int,
    val tcpFlags: Int? = null
)

/**
 * Minimal IPv4/IPv6 TCP/UDP header parser for packets read from the VPN TUN.
 * It deliberately returns only tuple metadata and total packet length.
 */
object IpPacketParser {
    private const val IPPROTO_TCP = 6
    private const val IPPROTO_UDP = 17
    private const val IPV6_HOP_BY_HOP = 0
    private const val IPV6_ROUTING = 43
    private const val IPV6_FRAGMENT = 44
    private const val IPV6_AUTHENTICATION = 51
    private const val IPV6_DESTINATION_OPTIONS = 60
    private const val IPV6_MOBILITY = 135
    private const val IPV6_HIP = 139
    private const val IPV6_SHIM6 = 140
    private const val MAX_IPV6_EXTENSION_HEADERS = 8

    fun parse(packet: ByteArray, length: Int = packet.size): ParsedIpPacket? {
        if (length < 1 || length > packet.size) return null
        return when ((packet[0].toInt() ushr 4) and 0x0f) {
            4 -> parseIpv4(packet, length)
            6 -> parseIpv6(packet, length)
            else -> null
        }
    }

    private fun parseIpv4(packet: ByteArray, length: Int): ParsedIpPacket? {
        if (length < 20) return null
        val headerLength = (packet[0].toInt() and 0x0f) * 4
        if (headerLength < 20 || headerLength > 60 || headerLength > length) return null

        val totalLength = unsignedShort(packet, 2)
        if (totalLength < headerLength + 4 || totalLength > length) return null

        // Later fragments do not contain the transport header and cannot be attributed by tuple.
        if ((unsignedShort(packet, 6) and 0x1fff) != 0) return null

        val protocolNumber = packet[9].toInt() and 0xff
        val protocol = protocolName(protocolNumber) ?: return null
        val transportHeaderLength = if (protocolNumber == IPPROTO_TCP) 20 else 8
        if (headerLength + transportHeaderLength > totalLength) return null

        val source = packet.copyOfRange(12, 16)
        val destination = packet.copyOfRange(16, 20)
        return ParsedIpPacket(
            protocol = protocol,
            protocolNumber = protocolNumber,
            sourceAddress = InetAddress.getByAddress(source),
            sourcePort = unsignedShort(packet, headerLength),
            destinationAddress = InetAddress.getByAddress(destination),
            destinationPort = unsignedShort(packet, headerLength + 2),
            packetBytes = totalLength,
            tcpFlags = if (protocolNumber == IPPROTO_TCP) packet[headerLength + 13].toInt() and 0xff else null
        )
    }

    private fun parseIpv6(packet: ByteArray, length: Int): ParsedIpPacket? {
        if (length < 40) return null
        val payloadLength = unsignedShort(packet, 4)
        // IPv6 jumbograms require the Jumbo Payload option and are not emitted by this TUN MTU.
        if (payloadLength == 0) return null
        val totalLength = 40 + payloadLength
        if (totalLength > length) return null

        var nextHeader = packet[6].toInt() and 0xff
        var offset = 40
        var extensionCount = 0

        while (nextHeader != IPPROTO_TCP && nextHeader != IPPROTO_UDP) {
            if (extensionCount++ >= MAX_IPV6_EXTENSION_HEADERS) return null
            if (offset + 2 > totalLength) return null

            when (nextHeader) {
                IPV6_HOP_BY_HOP, IPV6_ROUTING, IPV6_DESTINATION_OPTIONS,
                IPV6_MOBILITY, IPV6_HIP, IPV6_SHIM6 -> {
                    val extensionLength = ((packet[offset + 1].toInt() and 0xff) + 1) * 8
                    if (extensionLength < 8 || offset + extensionLength > totalLength) return null
                    nextHeader = packet[offset].toInt() and 0xff
                    offset += extensionLength
                }
                IPV6_FRAGMENT -> {
                    if (offset + 8 > totalLength) return null
                    val fragmentOffsetAndFlags = unsignedShort(packet, offset + 2)
                    if ((fragmentOffsetAndFlags and 0xfff8) != 0) return null
                    nextHeader = packet[offset].toInt() and 0xff
                    offset += 8
                }
                IPV6_AUTHENTICATION -> {
                    val extensionLength = ((packet[offset + 1].toInt() and 0xff) + 2) * 4
                    if (extensionLength < 8 || offset + extensionLength > totalLength) return null
                    nextHeader = packet[offset].toInt() and 0xff
                    offset += extensionLength
                }
                else -> return null
            }
        }

        val protocol = protocolName(nextHeader) ?: return null
        val transportHeaderLength = if (nextHeader == IPPROTO_TCP) 20 else 8
        if (offset + transportHeaderLength > totalLength) return null

        val source = packet.copyOfRange(8, 24)
        val destination = packet.copyOfRange(24, 40)
        return ParsedIpPacket(
            protocol = protocol,
            protocolNumber = nextHeader,
            sourceAddress = InetAddress.getByAddress(source),
            sourcePort = unsignedShort(packet, offset),
            destinationAddress = InetAddress.getByAddress(destination),
            destinationPort = unsignedShort(packet, offset + 2),
            packetBytes = totalLength,
            tcpFlags = if (nextHeader == IPPROTO_TCP) packet[offset + 13].toInt() and 0xff else null
        )
    }

    private fun protocolName(number: Int): String? = when (number) {
        IPPROTO_TCP -> "tcp"
        IPPROTO_UDP -> "udp"
        else -> null
    }

    private fun unsignedShort(bytes: ByteArray, offset: Int): Int =
        ((bytes[offset].toInt() and 0xff) shl 8) or (bytes[offset + 1].toInt() and 0xff)
}
