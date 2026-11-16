package com.thedrack.jarvismobile

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class PassivePayloadInspectorTest {
    @Test
    fun extractsDnsQuestionNameWithoutRetainingDnsPayload() {
        val observations = PassivePayloadInspector.inspect(
            protocolNumber = 17,
            sourcePort = 53000,
            destinationPort = 53,
            payload = dnsQuery("api.example.com")
        )

        assertEquals(
            listOf(NetworkProtocolObservation("dns_query", "api.example.com", "dns")),
            observations
        )
    }

    @Test
    fun extractsHttpHostButNeverRequestPathOrHeaders() {
        val observations = PassivePayloadInspector.inspect(
            protocolNumber = 6,
            sourcePort = 51000,
            destinationPort = 80,
            payload = "GET /private/account?token=secret HTTP/1.1\r\nHost: Example.COM:8080\r\nAuthorization: Bearer secret\r\n\r\n"
                .toByteArray(Charsets.US_ASCII)
        )

        assertEquals(
            listOf(NetworkProtocolObservation("http_host", "example.com", "http")),
            observations
        )
        assertTrue(observations.none { it.value.contains("private") || it.value.contains("secret") })
    }

    @Test
    fun extractsTlsServerNameFromCompleteClientHello() {
        val observations = PassivePayloadInspector.inspect(
            protocolNumber = 6,
            sourcePort = 51000,
            destinationPort = 443,
            payload = tlsClientHello("api.example.com")
        )

        assertEquals(
            listOf(NetworkProtocolObservation("tls_sni", "api.example.com", "tls_client_hello")),
            observations
        )
    }

    @Test
    fun ignoresMalformedDnsAndTlsRecords() {
        assertTrue(
            PassivePayloadInspector.inspect(
                protocolNumber = 17,
                sourcePort = 53000,
                destinationPort = 53,
                payload = byteArrayOf(0, 1, 0)
            ).isEmpty()
        )
        assertTrue(
            PassivePayloadInspector.inspect(
                protocolNumber = 6,
                sourcePort = 51000,
                destinationPort = 443,
                payload = byteArrayOf(0x16, 0x03, 0x03, 0x7f, 0x7f)
            ).isEmpty()
        )
    }

    @Test
    fun ignoresUnsupportedPortsAndOversizedPayloads() {
        assertTrue(
            PassivePayloadInspector.inspect(
                protocolNumber = 6,
                sourcePort = 51000,
                destinationPort = 22,
                payload = "SSH-2.0-example".toByteArray()
            ).isEmpty()
        )
        assertTrue(
            PassivePayloadInspector.inspect(
                protocolNumber = 6,
                sourcePort = 51000,
                destinationPort = 443,
                payload = ByteArray(PassivePayloadInspector.MAX_INSPECTED_PAYLOAD_BYTES + 1)
            ).isEmpty()
        )
    }

    private fun dnsQuery(host: String): ByteArray {
        val qname = host.split(".").flatMap { label ->
            listOf(label.length.toByte()) + label.toByteArray(Charsets.US_ASCII).toList()
        } + listOf(0.toByte())
        val question = qname.toByteArray() + byteArrayOf(0, 1, 0, 1)
        return byteArrayOf(
            0x12, 0x34, 0x01, 0x00, 0x00, 0x01,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00
        ) + question
    }

    private fun tlsClientHello(host: String): ByteArray {
        val hostname = host.toByteArray(Charsets.US_ASCII)
        val serverName = byteArrayOf(
            0, (hostname.size + 5).toByte(),
            0, 0, hostname.size.toByte()
        ) + hostname
        val sniExtension = byteArrayOf(
            0, 0,
            (serverName.size shr 8).toByte(), serverName.size.toByte()
        ) + serverName
        val extensions = sniExtension
        val body = byteArrayOf(
            0x03, 0x03
        ) + ByteArray(32) + byteArrayOf(
            0, // session ID length
            0, 2, 0x13, 0x01, // cipher suites
            1, 0, // compression methods
            (extensions.size shr 8).toByte(), extensions.size.toByte()
        ) + extensions
        val handshake = byteArrayOf(
            1,
            (body.size shr 16).toByte(),
            (body.size shr 8).toByte(),
            body.size.toByte()
        ) + body
        return byteArrayOf(
            0x16, 0x03, 0x01,
            (handshake.size shr 8).toByte(), handshake.size.toByte()
        ) + handshake
    }
}
