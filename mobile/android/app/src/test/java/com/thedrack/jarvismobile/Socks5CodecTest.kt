package com.thedrack.jarvismobile

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.net.InetAddress

class Socks5CodecTest {
    @Test
    fun decodesIpv4UdpRequestAndPayload() {
        val packet = byteArrayOf(
            0, 0, 0, 1, 8, 8, 8, 8, 0, 53, 1, 2, 3
        )
        val decoded = Socks5Codec.decodeUdp(packet)!!
        assertEquals("8.8.8.8", decoded.host)
        assertEquals(53, decoded.port)
        assertArrayEquals(byteArrayOf(1, 2, 3), decoded.payload)
    }

    @Test
    fun decodesDomainNameUdpRequest() {
        val host = "dns.google".toByteArray()
        val packet = byteArrayOf(0, 0, 0, 3, host.size.toByte()) +
            host + byteArrayOf(0, 53, 9)
        val decoded = Socks5Codec.decodeUdp(packet)!!
        assertEquals("dns.google", decoded.host)
        assertEquals(53, decoded.port)
        assertArrayEquals(byteArrayOf(9), decoded.payload)
    }

    @Test
    fun rejectsFragmentedAndMalformedUdpPackets() {
        assertNull(Socks5Codec.decodeUdp(byteArrayOf(0, 0, 1, 1, 8, 8, 8, 8, 0, 53)))
        assertNull(Socks5Codec.decodeUdp(byteArrayOf(0, 0, 0, 99)))
        assertNull(Socks5Codec.decodeUdp(byteArrayOf(0, 0, 0, 1, 8, 8, 8)))
    }

    @Test
    fun encodesIpv6UdpResponse() {
        val payload = byteArrayOf(4, 5)
        val encoded = Socks5Codec.encodeUdp(InetAddress.getByName("2001:4860:4860::8888"), 53, payload)
        assertEquals(0, encoded[0].toInt())
        assertEquals(0, encoded[1].toInt())
        assertEquals(0, encoded[2].toInt())
        assertEquals(4, encoded[3].toInt())
        assertArrayEquals(payload, encoded.copyOfRange(encoded.size - payload.size, encoded.size))
    }
}
