package com.thedrack.jarvismobile

import java.net.InetAddress

data class Socks5UdpFrame(val host: String, val port: Int, val payload: ByteArray)

object Socks5Codec {
    fun decodeUdp(packet: ByteArray): Socks5UdpFrame? {
        if (packet.size < 4 || packet[0].toInt() != 0 || packet[1].toInt() != 0 || packet[2].toInt() != 0) return null
        var offset = 4
        val host = when (packet[3].toInt() and 0xff) {
            1 -> {
                if (packet.size < offset + 4 + 2) return null
                val bytes = packet.copyOfRange(offset, offset + 4)
                offset += 4
                InetAddress.getByAddress(bytes).hostAddress
            }
            3 -> {
                if (packet.size <= offset) return null
                val length = packet[offset++].toInt() and 0xff
                if (length == 0 || packet.size < offset + length + 2) return null
                String(packet, offset, length, Charsets.US_ASCII).also { offset += length }
            }
            4 -> {
                if (packet.size < offset + 16 + 2) return null
                val bytes = packet.copyOfRange(offset, offset + 16)
                offset += 16
                InetAddress.getByAddress(bytes).hostAddress
            }
            else -> return null
        }
        if (packet.size < offset + 2) return null
        val port = ((packet[offset].toInt() and 0xff) shl 8) or (packet[offset + 1].toInt() and 0xff)
        offset += 2
        if (port == 0) return null
        return Socks5UdpFrame(host, port, packet.copyOfRange(offset, packet.size))
    }

    fun encodeUdp(address: InetAddress, port: Int, payload: ByteArray): ByteArray {
        require(port in 1..65535)
        val raw = address.address
        val atyp = when (raw.size) {
            4 -> 1
            16 -> 4
            else -> error("Unsupported address size")
        }
        return byteArrayOf(0, 0, 0, atyp.toByte()) + raw +
            byteArrayOf((port shr 8).toByte(), port.toByte()) + payload
    }
}
