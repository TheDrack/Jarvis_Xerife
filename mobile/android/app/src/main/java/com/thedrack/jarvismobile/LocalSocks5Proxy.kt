package com.thedrack.jarvismobile

import android.net.VpnService
import android.util.Log
import java.io.BufferedInputStream
import java.io.BufferedOutputStream
import java.io.EOFException
import java.io.InputStream
import java.io.OutputStream
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.ServerSocket
import java.net.Socket
import java.net.SocketException
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.Semaphore
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference

/**
 * Loopback-only SOCKS5 server used as the upstream for Hev tun2socks.
 *
 * Outbound TCP and UDP sockets are protected from the Jarvis TUN interface,
 * preventing recursive capture. The proxy never logs or persists payloads.
 */
internal class LocalSocks5Proxy(
    private val vpnService: VpnService,
    private val username: String,
    private val password: String,
    private val port: Int = 0
) : AutoCloseable {
    private val running = AtomicBoolean(false)
    private val workers: ExecutorService = Executors.newCachedThreadPool()
    private val clientSlots = Semaphore(MAX_CLIENT_SESSIONS)
    @Volatile private var server: ServerSocket? = null
    private val udpSockets = ConcurrentHashMap.newKeySet<DatagramSocket>()
    private val clientSockets = ConcurrentHashMap.newKeySet<Socket>()

    fun isRunning(): Boolean = running.get() && server?.isClosed == false

    fun start(): Int {
        check(running.compareAndSet(false, true)) { "SOCKS5 proxy already started" }
        try {
            server = ServerSocket().apply {
                reuseAddress = true
                bind(InetSocketAddress(InetAddress.getByName("127.0.0.1"), port), 32)
            }
            val listeningPort = checkNotNull(server).localPort
            workers.execute {
                while (running.get()) {
                    try {
                        val client = server?.accept() ?: break
                        if (!clientSlots.tryAcquire()) {
                            client.close()
                            continue
                        }
                        clientSockets.add(client)
                        try {
                            workers.execute {
                                try { handleClient(client) }
                                finally {
                                    clientSockets.remove(client)
                                    clientSlots.release()
                                }
                            }
                        } catch (error: Exception) {
                            clientSockets.remove(client)
                            clientSlots.release()
                            runCatching { client.close() }
                            if (running.get()) Log.w(TAG, "SOCKS5 worker rejected", error)
                        }
                    } catch (error: SocketException) {
                        if (running.get()) Log.w(TAG, "SOCKS5 accept failed", error)
                        break
                    } catch (error: Exception) {
                        if (running.get()) Log.w(TAG, "SOCKS5 client failed", error)
                    }
                }
            }
            return listeningPort
        } catch (error: Exception) {
            close()
            throw error
        }
    }

    /** Verifies authenticated TCP and UDP forwarding before the TUN interface is established. */
    fun selfTest() {
        val loopback = InetAddress.getByName("127.0.0.1")
        val probe = byteArrayOf(0x4a, 0x41, 0x52, 0x56, 0x49, 0x53)

        val tcpEchoServer = ServerSocket(0, 1, loopback).apply { soTimeout = SELF_TEST_TIMEOUT_MS }
        val tcpEchoThread = Thread {
            runCatching {
                tcpEchoServer.accept().use { accepted ->
                    val buffer = ByteArray(probe.size)
                    val count = accepted.getInputStream().read(buffer)
                    if (count > 0) accepted.getOutputStream().write(buffer, 0, count)
                }
            }
        }.apply { isDaemon = true; start() }

        try {
            Socket().use { client ->
                client.connect(InetSocketAddress(loopback, checkNotNull(server).localPort), SELF_TEST_TIMEOUT_MS)
                client.soTimeout = SELF_TEST_TIMEOUT_MS
                val input = BufferedInputStream(client.getInputStream())
                val output = BufferedOutputStream(client.getOutputStream())
                authenticate(input, output)
                val echoPort = tcpEchoServer.localPort
                output.write(byteArrayOf(
                    SOCKS_VERSION.toByte(), CMD_CONNECT.toByte(), 0, ATYP_IPV4.toByte(),
                    127, 0, 0, 1, (echoPort shr 8).toByte(), echoPort.toByte()
                ))
                output.flush()
                readSocksReply(input)
                output.write(probe)
                output.flush()
                check(readExactly(input, probe.size).contentEquals(probe)) {
                    "SOCKS5 TCP self-test did not return the probe bytes"
                }
            }
        } finally {
            runCatching { tcpEchoServer.close() }
            runCatching { tcpEchoThread.join(SELF_TEST_TIMEOUT_MS.toLong()) }
        }

        val udpEchoServer = DatagramSocket(null).apply {
            bind(InetSocketAddress(loopback, 0))
            soTimeout = SELF_TEST_TIMEOUT_MS
        }
        val udpEchoThread = Thread {
            runCatching {
                val buffer = ByteArray(128)
                val packet = DatagramPacket(buffer, buffer.size)
                udpEchoServer.receive(packet)
                udpEchoServer.send(
                    DatagramPacket(packet.data, packet.offset, packet.length, packet.socketAddress)
                )
            }
        }.apply { isDaemon = true; start() }

        try {
            Socket().use { control ->
                control.connect(InetSocketAddress(loopback, checkNotNull(server).localPort), SELF_TEST_TIMEOUT_MS)
                control.soTimeout = SELF_TEST_TIMEOUT_MS
                val input = BufferedInputStream(control.getInputStream())
                val output = BufferedOutputStream(control.getOutputStream())
                authenticate(input, output)
                output.write(byteArrayOf(
                    SOCKS_VERSION.toByte(), CMD_UDP_ASSOCIATE.toByte(), 0, ATYP_IPV4.toByte(),
                    0, 0, 0, 0, 0, 0
                ))
                output.flush()
                val relay = readSocksReply(input)
                DatagramSocket(InetSocketAddress(loopback, 0)).use { clientUdp ->
                    clientUdp.soTimeout = SELF_TEST_TIMEOUT_MS
                    val request = Socks5Codec.encodeUdp(loopback, udpEchoServer.localPort, probe)
                    clientUdp.send(DatagramPacket(request, request.size, relay))
                    val responseBuffer = ByteArray(256)
                    val response = DatagramPacket(responseBuffer, responseBuffer.size)
                    clientUdp.receive(response)
                    val decoded = Socks5Codec.decodeUdp(
                        response.data.copyOfRange(response.offset, response.offset + response.length)
                    )
                    check(decoded?.payload?.contentEquals(probe) == true) {
                        "SOCKS5 UDP self-test did not return the probe bytes"
                    }
                }
            }
        } finally {
            udpEchoServer.close()
            runCatching { udpEchoThread.join(SELF_TEST_TIMEOUT_MS.toLong()) }
        }
    }

    private fun authenticate(input: InputStream, output: OutputStream) {
        output.write(byteArrayOf(SOCKS_VERSION.toByte(), 1, METHOD_USER_PASSWORD.toByte()))
        output.flush()
        check(readU8(input) == SOCKS_VERSION && readU8(input) == METHOD_USER_PASSWORD) {
            "SOCKS5 proxy did not negotiate username/password authentication"
        }
        val userBytes = username.toByteArray(Charsets.US_ASCII)
        val passwordBytes = password.toByteArray(Charsets.US_ASCII)
        output.write(byteArrayOf(AUTH_VERSION.toByte(), userBytes.size.toByte()))
        output.write(userBytes)
        output.write(byteArrayOf(passwordBytes.size.toByte()))
        output.write(passwordBytes)
        output.flush()
        check(readU8(input) == AUTH_VERSION && readU8(input) == 0) {
            "SOCKS5 proxy authentication self-test failed"
        }
    }

    private fun readSocksReply(input: InputStream): InetSocketAddress {
        check(readU8(input) == SOCKS_VERSION) { "Invalid SOCKS5 reply version" }
        val status = readU8(input)
        check(readU8(input) == 0) { "Invalid SOCKS5 reply reserved field" }
        val host = readAddress(input)
        val port = readU16(input)
        check(status == REP_SUCCEEDED) { "SOCKS5 command failed with status $status" }
        return InetSocketAddress(host, port)
    }

    private fun readExactly(input: InputStream, length: Int): ByteArray {
        val bytes = ByteArray(length)
        var offset = 0
        while (offset < length) {
            val count = input.read(bytes, offset, length - offset)
            if (count < 0) throw EOFException("Unexpected end of SOCKS5 self-test stream")
            offset += count
        }
        return bytes
    }

    private fun handleClient(client: Socket) {
        client.use { socket ->
            socket.soTimeout = CONTROL_TIMEOUT_MS
            val input = BufferedInputStream(socket.getInputStream())
            val output = BufferedOutputStream(socket.getOutputStream())
            try {
                if (readU8(input) != SOCKS_VERSION) return
                val methodCount = readU8(input)
                var userPassOffered = false
                repeat(methodCount) { if (readU8(input) == METHOD_USER_PASSWORD) userPassOffered = true }
                output.write(byteArrayOf(SOCKS_VERSION.toByte(), (if (userPassOffered) METHOD_USER_PASSWORD else METHOD_REJECT).toByte()))
                output.flush()
                if (!userPassOffered) return

                if (readU8(input) != AUTH_VERSION) return
                val usernameLength = readU8(input)
                val suppliedUsername = ByteArray(usernameLength) { readU8(input).toByte() }
                val passwordLength = readU8(input)
                val suppliedPassword = ByteArray(passwordLength) { readU8(input).toByte() }
                val authenticated = Socks5Authenticator.matches(
                    suppliedUsername, suppliedPassword, username, password
                )
                output.write(byteArrayOf(AUTH_VERSION.toByte(), (if (authenticated) 0 else 1).toByte()))
                output.flush()
                if (!authenticated) return

                if (readU8(input) != SOCKS_VERSION) return
                val command = readU8(input)
                if (readU8(input) != 0) return
                val target = readAddress(input)
                val targetPort = readU16(input)
                when (command) {
                    CMD_CONNECT -> connectAndRelay(socket, input, output, target, targetPort)
                    CMD_UDP_ASSOCIATE -> udpAssociate(socket, input, output)
                    else -> writeReply(output, REP_COMMAND_UNSUPPORTED)
                }
            } catch (_: EOFException) {
                // Client closed before completing the SOCKS handshake.
            } catch (error: Exception) {
                if (running.get()) Log.d(TAG, "SOCKS5 session ended: ${error.javaClass.simpleName}")
                runCatching { writeReply(output, REP_GENERAL_FAILURE) }
            }
        }
    }

    private fun connectAndRelay(
        client: Socket,
        clientInput: InputStream,
        output: OutputStream,
        host: String,
        port: Int
    ) {
        val upstream = Socket()
        try {
            val destinationAddresses = InetAddress.getAllByName(host)
            val destinationIsLoopback = destinationAddresses.isNotEmpty() &&
                destinationAddresses.all { it.isLoopbackAddress }

            // Loopback traffic is local to this device and must remain reachable
            // by the SOCKS self-test even when the VPN service protects external sockets.
            if (!destinationIsLoopback && !vpnService.protect(upstream)) {
                Log.e(TAG, "VpnService.protect(TCP) returned false for an external destination")
                runCatching { writeReply(output, REP_GENERAL_FAILURE) }
                runCatching { upstream.close() }
                return
            }

            upstream.tcpNoDelay = true
            upstream.connect(InetSocketAddress(host, port), CONNECT_TIMEOUT_MS)
        } catch (error: Exception) {
            Log.e(TAG, "SOCKS5 TCP upstream connection failed: ${error.javaClass.simpleName}")
            runCatching { writeReply(output, REP_HOST_UNREACHABLE) }
            runCatching { upstream.close() }
            return
        }

        writeReply(output, REP_SUCCEEDED)
        client.soTimeout = 0
        upstream.soTimeout = 0
        try {
            val down = workers.submit {
                try {
                    copyStream(upstream.getInputStream(), client.getOutputStream())
                } finally {
                    runCatching { client.shutdownOutput() }
                }
            }
            try {
                copyStream(clientInput, upstream.getOutputStream())
            } finally {
                runCatching { upstream.shutdownOutput() }
            }
            down.get()
        } finally {
            runCatching { upstream.close() }
        }
    }

    private fun udpAssociate(control: Socket, controlInput: InputStream, output: OutputStream) {
        control.soTimeout = 0
        val relay = DatagramSocket(null)
        try {
            if (!vpnService.protect(relay)) throw SocketException("VpnService.protect(UDP) failed")
            relay.reuseAddress = false
            relay.bind(InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0))
            udpSockets.add(relay)
            writeReply(output, REP_SUCCEEDED, InetAddress.getByName("127.0.0.1"), relay.localPort)
            workers.execute {
                try { while (controlInput.read() >= 0) Unit } catch (_: Exception) { }
                runCatching { relay.close() }
            }
            val clientAddress = AtomicReference<InetSocketAddress?>(null)
            val buffer = ByteArray(MAX_UDP_PACKET)
            while (running.get() && !relay.isClosed) {
                val packet = DatagramPacket(buffer, buffer.size)
                try {
                    relay.receive(packet)
                    val source = InetSocketAddress(packet.address, packet.port)
                    val knownClient = clientAddress.get()
                    if (packet.address.isLoopbackAddress && (knownClient == null || knownClient == source)) {
                        clientAddress.set(source)
                        val frame = Socks5Codec.decodeUdp(packet.data.copyOfRange(packet.offset, packet.offset + packet.length))
                            ?: continue
                        val destination = InetAddress.getByName(frame.host)
                        val outgoing = DatagramPacket(frame.payload, frame.payload.size, destination, frame.port)
                        relay.send(outgoing)
                    } else {
                        val clientEndpoint = clientAddress.get() ?: continue
                        val encoded = Socks5Codec.encodeUdp(packet.address, packet.port,
                            packet.data.copyOfRange(packet.offset, packet.offset + packet.length))
                        relay.send(DatagramPacket(encoded, encoded.size, clientEndpoint))
                    }
                } catch (error: SocketException) {
                    if (running.get() && !relay.isClosed) throw error
                    break
                } catch (_: Exception) {
                    // Drop one malformed or unreachable datagram without terminating the VPN.
                }
            }
        } finally {
            udpSockets.remove(relay)
            relay.close()
        }
    }

    private fun copyStream(input: InputStream, output: OutputStream) {
        val buffer = ByteArray(STREAM_BUFFER_SIZE)
        try {
            while (running.get()) {
                val count = input.read(buffer)
                if (count < 0) break
                output.write(buffer, 0, count)
                output.flush()
            }
        } catch (_: Exception) {
            // One side closing terminates the relay; no payload is logged.
        }
    }

    private fun readAddress(input: InputStream): String = when (readU8(input)) {
        ATYP_IPV4 -> InetAddress.getByAddress(ByteArray(4) { readU8(input).toByte() }).hostAddress!!
        ATYP_DOMAIN -> {
            val length = readU8(input)
            require(length in 1..255) { "Invalid SOCKS5 domain length" }
            ByteArray(length) { readU8(input).toByte() }.toString(Charsets.US_ASCII)
        }
        ATYP_IPV6 -> InetAddress.getByAddress(ByteArray(16) { readU8(input).toByte() }).hostAddress!!
        else -> throw IllegalArgumentException("Unsupported SOCKS5 address type")
    }

    private fun readU8(input: InputStream): Int {
        val value = input.read()
        if (value < 0) throw EOFException()
        return value
    }

    private fun readU16(input: InputStream): Int = (readU8(input) shl 8) or readU8(input)

    private fun writeReply(
        output: OutputStream,
        reply: Int,
        address: InetAddress = InetAddress.getByName("0.0.0.0"),
        port: Int = 0
    ) {
        val raw = address.address
        val atyp = if (raw.size == 16) ATYP_IPV6 else ATYP_IPV4
        output.write(byteArrayOf(SOCKS_VERSION.toByte(), reply.toByte(), 0, atyp.toByte()))
        output.write(raw)
        output.write(byteArrayOf((port shr 8).toByte(), port.toByte()))
        output.flush()
    }

    override fun close() {
        if (!running.compareAndSet(true, false)) return
        runCatching { server?.close() }
        server = null
        clientSockets.toList().forEach { runCatching { it.close() } }
        clientSockets.clear()
        udpSockets.toList().forEach { runCatching { it.close() } }
        workers.shutdownNow()
    }

    companion object {
        private const val TAG = "JarvisSocks5"
        private const val SOCKS_VERSION = 5
        private const val METHOD_USER_PASSWORD = 2
        private const val METHOD_REJECT = 0xff
        private const val AUTH_VERSION = 1
        private const val CMD_CONNECT = 1
        private const val CMD_UDP_ASSOCIATE = 3
        private const val ATYP_IPV4 = 1
        private const val ATYP_DOMAIN = 3
        private const val ATYP_IPV6 = 4
        private const val REP_SUCCEEDED = 0
        private const val REP_GENERAL_FAILURE = 1
        private const val REP_COMMAND_UNSUPPORTED = 7
        private const val REP_HOST_UNREACHABLE = 4
        private const val CONNECT_TIMEOUT_MS = 12_000
        private const val CONTROL_TIMEOUT_MS = 5_000
        private const val MAX_CLIENT_SESSIONS = 32
        private const val MAX_UDP_PACKET = 65_507
        private const val STREAM_BUFFER_SIZE = 32 * 1024
        private const val SELF_TEST_TIMEOUT_MS = 1_000
    }
}
