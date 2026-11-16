package com.thedrack.jarvismobile

import java.util.Locale

/**
 * Extracts bounded protocol metadata from a single transport payload.
 *
 * This inspector never stores or returns raw payload bytes. It deliberately does
 * not decrypt TLS, inspect credentials, retain HTTP paths, or bypass app trust
 * policies. TCP stream reassembly is a separate layer and is not implied here:
 * TLS ClientHello and HTTP headers must be present in the supplied segment.
 */
data class NetworkProtocolObservation(
    val kind: String,
    val value: String,
    val source: String
)

object PassivePayloadInspector {
    const val MAX_INSPECTED_PAYLOAD_BYTES = 16 * 1024
    private const val DNS_PORT = 53
    private const val MDNS_PORT = 5353
    private const val HTTP_PORT = 80
    private const val ALT_HTTP_PORT = 8080
    private const val ALT_HTTP_PORT_2 = 8000
    private const val MAX_DNS_QUESTIONS = 8
    private const val MAX_DNS_POINTER_HOPS = 16
    private const val MAX_HTTP_HEADER_BYTES = 8 * 1024

    fun inspect(
        protocolNumber: Int,
        sourcePort: Int,
        destinationPort: Int,
        payload: ByteArray
    ): List<NetworkProtocolObservation> {
        if (payload.isEmpty() || payload.size > MAX_INSPECTED_PAYLOAD_BYTES) return emptyList()

        return when (protocolNumber) {
            17 -> if (sourcePort in setOf(DNS_PORT, MDNS_PORT) ||
                destinationPort in setOf(DNS_PORT, MDNS_PORT)
            ) parseDns(payload) else emptyList()
            6 -> {
                val dns = if (sourcePort in DNS_PORTS || destinationPort in DNS_PORTS) {
                    parseDnsTcp(payload)
                } else null
                val http = if (sourcePort in HTTP_PORTS || destinationPort in HTTP_PORTS) {
                    parseHttpHost(payload)
                } else null
                val tls = parseTlsServerName(payload)
                listOfNotNull(dns, http, tls).distinct()
            }
            else -> emptyList()
        }
    }

    private fun parseDnsTcp(payload: ByteArray): NetworkProtocolObservation? {
        if (payload.size < 14) return null
        val messageLength = u16(payload, 0)
        if (messageLength < 12 || messageLength > payload.size - 2) return null
        val message = payload.copyOfRange(2, 2 + messageLength)
        return try {
            parseDns(message).firstOrNull()
        } finally {
            message.fill(0)
        }
    }

    private fun parseDns(payload: ByteArray): List<NetworkProtocolObservation> {
        if (payload.size < 12) return emptyList()
        val flags = u16(payload, 2)
        val questionCount = u16(payload, 4)
        if (questionCount !in 1..MAX_DNS_QUESTIONS) return emptyList()

        val parsed = readDnsName(payload, 12) ?: return emptyList()
        if (parsed.second + 4 > payload.size) return emptyList()
        val normalized = normalizeHostname(parsed.first) ?: return emptyList()
        val kind = if (flags and 0x8000 == 0) "dns_query" else "dns_response_question"
        return listOf(NetworkProtocolObservation(kind, normalized, "dns"))
    }

    /**
     * Reads one DNS name, including compression pointers, without following
     * unbounded pointer chains or reading outside the supplied message.
     */
    private fun readDnsName(message: ByteArray, start: Int): Pair<String, Int>? {
        if (start !in message.indices) return null
        val labels = mutableListOf<String>()
        val visited = HashSet<Int>()
        var cursor = start
        var nextOffset = -1
        var pointerHops = 0
        var expandedLength = 0

        while (cursor < message.size) {
            val length = message[cursor].toInt() and 0xff
            when {
                length == 0 -> {
                    if (nextOffset < 0) nextOffset = cursor + 1
                    val name = labels.joinToString(".")
                    return if (name.isEmpty()) null else name to nextOffset
                }
                length and 0xc0 == 0xc0 -> {
                    if (cursor + 1 >= message.size) return null
                    val pointer = ((length and 0x3f) shl 8) or (message[cursor + 1].toInt() and 0xff)
                    if (pointer < 12 || pointer >= cursor || !visited.add(pointer)) return null
                    if (nextOffset < 0) nextOffset = cursor + 2
                    cursor = pointer
                    pointerHops += 1
                    if (pointerHops > MAX_DNS_POINTER_HOPS) return null
                }
                length and 0xc0 != 0 || length > 63 -> return null
                else -> {
                    val end = cursor + 1 + length
                    if (end > message.size) return null
                    val labelBytes = message.copyOfRange(cursor + 1, end)
                    if (labelBytes.any { (it.toInt() and 0xff) !in 0x21..0x7e }) return null
                    labels += labelBytes.toString(Charsets.US_ASCII)
                    expandedLength += length + 1
                    if (expandedLength > 255) return null
                    cursor = end
                }
            }
        }
        return null
    }

    private fun parseHttpHost(payload: ByteArray): NetworkProtocolObservation? {
        val inspectedLength = minOf(payload.size, MAX_HTTP_HEADER_BYTES)
        val headerEnd = indexOfHeaderEnd(payload, inspectedLength)
        if (headerEnd < 0) return null

        // Inspect only the method token and Host value. Do not materialize the
        // request target or unrelated headers (which may contain credentials).
        val firstLineEnd = findCrlf(payload, 0, headerEnd + 2)
        if (firstLineEnd <= 0) return null
        val isResponse = startsWithAscii(payload, 0, firstLineEnd, "HTTP/1.")
        val firstSpace = findByte(payload, 0, firstLineEnd, ' '.code)
        val isRequest = if (firstSpace > 0) {
            val secondSpace = findByte(payload, firstSpace + 1, firstLineEnd, ' '.code)
            val method = payload.copyOfRange(0, firstSpace)
                .toString(Charsets.US_ASCII)
                .uppercase(Locale.ROOT)
            secondSpace > firstSpace + 1 && method in HTTP_METHODS
        } else {
            false
        }
        if (!isResponse && !isRequest) return null

        var lineStart = firstLineEnd + 2
        var hostHeader: String? = null
        while (lineStart < headerEnd) {
            val lineEnd = findCrlf(payload, lineStart, headerEnd + 2)
            if (lineEnd < 0) return null
            val separator = findByte(payload, lineStart, lineEnd, ':'.code)
            if (separator > lineStart &&
                asciiEqualsIgnoreCase(payload, lineStart, separator, "host")
            ) {
                // Multiple Host fields are ambiguous and must not be attributed.
                if (hostHeader != null) return null
                var valueStart = separator + 1
                var valueEnd = lineEnd
                while (valueStart < valueEnd &&
                    (payload[valueStart] == ' '.code.toByte() || payload[valueStart] == '\\t'.code.toByte())
                ) valueStart++
                while (valueEnd > valueStart &&
                    (payload[valueEnd - 1] == ' '.code.toByte() || payload[valueEnd - 1] == '\\t'.code.toByte())
                ) valueEnd--
                if (valueStart >= valueEnd) return null
                hostHeader = payload.copyOfRange(valueStart, valueEnd)
                    .toString(Charsets.ISO_8859_1)
            }
            lineStart = lineEnd + 2
        }

        val host = normalizeHostHeader(hostHeader ?: return null) ?: return null
        return NetworkProtocolObservation("http_host", host, "http")
    }

    private fun findCrlf(bytes: ByteArray, start: Int, endExclusive: Int): Int {
        var index = start
        while (index + 1 < endExclusive) {
            if (bytes[index] == 13.toByte() && bytes[index + 1] == 10.toByte()) return index
            index++
        }
        return -1
    }

    private fun findByte(bytes: ByteArray, start: Int, endExclusive: Int, value: Int): Int {
        for (index in start until endExclusive) {
            if ((bytes[index].toInt() and 0xff) == value) return index
        }
        return -1
    }

    private fun startsWithAscii(bytes: ByteArray, start: Int, endExclusive: Int, value: String): Boolean {
        if (endExclusive - start < value.length) return false
        for (index in value.indices) {
            if ((bytes[start + index].toInt() and 0xff) != value[index].code) return false
        }
        return true
    }

    private fun asciiEqualsIgnoreCase(
        bytes: ByteArray,
        start: Int,
        endExclusive: Int,
        value: String
    ): Boolean {
        if (endExclusive - start != value.length) return false
        for (index in value.indices) {
            val actual = (bytes[start + index].toInt() and 0xff).toChar().lowercaseChar()
            if (actual != value[index]) return false
        }
        return true
    }

    private fun parseTlsServerName(payload: ByteArray): NetworkProtocolObservation? {
        if (payload.size < 9 || payload[0].toInt() and 0xff != 22) return null
        if (payload[1].toInt() and 0xff != 3) return null
        val recordLength = u16(payload, 3)
        if (recordLength < 4 || recordLength > payload.size - 5) return null

        val handshakeStart = 5
        if (payload[handshakeStart].toInt() and 0xff != 1) return null
        val handshakeLength = u24(payload, handshakeStart + 1)
        if (handshakeLength < 38 || handshakeLength > recordLength - 4) return null
        val bodyStart = handshakeStart + 4
        val bodyEnd = bodyStart + handshakeLength
        var cursor = bodyStart

        // legacy_version + random
        if (cursor + 34 > bodyEnd) return null
        cursor += 34

        // session_id
        if (cursor >= bodyEnd) return null
        val sessionIdLength = payload[cursor++].toInt() and 0xff
        cursor += sessionIdLength
        if (cursor + 2 > bodyEnd) return null

        // cipher_suites
        val cipherLength = u16(payload, cursor)
        cursor += 2
        if (cipherLength < 2 || cipherLength % 2 != 0 || cursor + cipherLength > bodyEnd) return null
        cursor += cipherLength

        // compression_methods
        if (cursor >= bodyEnd) return null
        val compressionLength = payload[cursor++].toInt() and 0xff
        cursor += compressionLength
        if (cursor == bodyEnd) return null
        if (cursor + 2 > bodyEnd) return null

        // extensions
        val extensionsLength = u16(payload, cursor)
        cursor += 2
        val extensionsEnd = cursor + extensionsLength
        if (extensionsEnd > bodyEnd) return null

        while (cursor < extensionsEnd) {
            if (cursor + 4 > extensionsEnd) return null
            val extensionType = u16(payload, cursor)
            val extensionLength = u16(payload, cursor + 2)
            cursor += 4
            val extensionEnd = cursor + extensionLength
            if (extensionEnd > extensionsEnd) return null
            if (extensionType == 0) {
                val host = parseServerNameExtension(payload, cursor, extensionEnd) ?: return null
                return NetworkProtocolObservation("tls_sni", host, "tls_client_hello")
            }
            cursor = extensionEnd
        }
        return null
    }

    private fun parseServerNameExtension(
        payload: ByteArray,
        start: Int,
        end: Int
    ): String? {
        if (start + 2 > end) return null
        val listLength = u16(payload, start)
        if (start + 2 + listLength != end) return null
        var cursor = start + 2
        var serverName: String? = null
        while (cursor < end) {
            if (cursor + 3 > end) return null
            val nameType = payload[cursor].toInt() and 0xff
            val nameLength = u16(payload, cursor + 1)
            cursor += 3
            if (cursor + nameLength > end) return null
            if (nameType == 0) {
                if (serverName != null) return null
                val bytes = payload.copyOfRange(cursor, cursor + nameLength)
                val raw = bytes.toString(Charsets.US_ASCII)
                serverName = normalizeHostname(raw) ?: return null
            }
            cursor += nameLength
        }
        return serverName
    }

    private fun normalizeHostHeader(value: String): String? {
        val host: String
        val port: String?
        when {
            value.startsWith("[") -> {
                val close = value.indexOf(']')
                if (close <= 1) return null
                host = value.substring(1, close)
                val suffix = value.substring(close + 1)
                if (suffix.isEmpty()) {
                    port = null
                } else {
                    if (!suffix.startsWith(":")) return null
                    port = suffix.drop(1)
                }
            }
            value.count { it == ':' } == 1 -> {
                host = value.substringBeforeLast(':')
                port = value.substringAfterLast(':')
            }
            value.contains(':') -> return null
            else -> {
                host = value
                port = null
            }
        }
        if (port != null && (
                port.isEmpty() || port.any { !it.isDigit() } ||
                    port.toIntOrNull()?.let { it !in 1..65535 } != false
            )
        ) return null
        return normalizeHostname(host)
    }

    private fun normalizeHostname(value: String): String? {
        var host = value.trim().lowercase(Locale.ROOT)
        if (host.endsWith(".")) host = host.dropLast(1)
        if (host.isEmpty() || host.endsWith(".") || host.length > 253 ||
            host.any { it.code !in 0x21..0x7e }
        ) return null
        if (host.startsWith(".") || ".." in host) return null
        val labels = host.split(".")
        if (labels.any { label ->
                label.isEmpty() || label.length > 63 ||
                    label.first() == '-' || label.last() == '-' ||
                    label.any { !(it in 'a'..'z' || it in '0'..'9' || it == '-') }
            }
        ) return null
        return host
    }

    private fun indexOfHeaderEnd(bytes: ByteArray, length: Int): Int {
        for (index in 0 until (length - 3).coerceAtLeast(0)) {
            if (bytes[index] == 13.toByte() && bytes[index + 1] == 10.toByte() &&
                bytes[index + 2] == 13.toByte() && bytes[index + 3] == 10.toByte()
            ) return index
        }
        return -1
    }

    private fun u16(bytes: ByteArray, offset: Int): Int =
        ((bytes[offset].toInt() and 0xff) shl 8) or (bytes[offset + 1].toInt() and 0xff)

    private fun u24(bytes: ByteArray, offset: Int): Int =
        ((bytes[offset].toInt() and 0xff) shl 16) or
            ((bytes[offset + 1].toInt() and 0xff) shl 8) or
            (bytes[offset + 2].toInt() and 0xff)

    private val DNS_PORTS = setOf(DNS_PORT, MDNS_PORT)
    private val HTTP_PORTS = setOf(HTTP_PORT, ALT_HTTP_PORT, ALT_HTTP_PORT_2)
    private val HTTP_METHODS = setOf(
        "GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS", "PATCH", "CONNECT", "TRACE"
    )
}
