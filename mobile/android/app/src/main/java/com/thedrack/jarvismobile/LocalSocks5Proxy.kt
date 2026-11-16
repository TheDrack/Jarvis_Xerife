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
    private val port: Int = DEFAULT_PORT
) : AutoCloseable {
    private val running = AtomicBoolean(false)
    private val workers: ExecutorService = Executors.newCachedThreadPool()
    private var server: ServerSocket? = null
    private val udpSockets = ConcurrentHashMap.newKeySet<DatagramSocket>()

    fun start() {
        check(running.compareAndSet(false, true)) { "SOCKS5 proxy already started" }
        try {
            server = ServerSocket().apply {
                reuseAddress = true
                bind(InetSocketAddress(InetAddress.getByName("127.0.0.1"), port), 32)
            }
            workers.execute {
                while (running.get()) {
                    try {
                        val client = server?.accept() ?: break
                        workers.execute { handleClient(client) }
                    } catch (error: SocketException) {
                        if (running.get()) Log.w(TAG, "SOCKS5 accept failed", error)
                        break
                    } catch (error: Exception) {
                        if (running.get()) Log.w(TAG, "SOCKS5 client failed", error)
                    }
                }
            }
        } catch (error: Exception) {
            close()
            throw error
        }
    }

    private fun handleClient(client: Socket) {
        client.use { socket ->
            socket.soTimeout = CONTROL_TIMEOUT_MS
            val input = BufferedInputStream(socket.getInputStream())
            val output = BufferedOutputStream(socket.getOutputStream())
            try {
                if (readU8(input) != SOCKS_VERSION) return
                val methodCount = readU8(input)
                var noAuthOffered = false
                repeat(methodCount) { if (readU8(input) == METHOD_NO_AUTH) noAuthOffered = true }
                output.write(byteArrayOf(SOCKS_VERSION.toByte(), (if (noAuthOffered) METHOD_NO_AUTH else METHOD_REJECT).toByte()))
                output.flush()
                if (!noAuthOffered) return

                if (readU8(input) != SOCKS_VERSION) return
                val command = readU8(input)
                if (readU8(input) != 0) return
                val target = readAddress(input)
                val targetPort = readU16(input)
                when (command) {
                    CMD_CONNECT -> connectAndRelay(socket, output, target, targetPort)
                    CMD_UDP_ASSOCIATE -> udpAssociate(socket, output)
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
        output: OutputStream,
        host: String,
        port: Int
    ) {
        val upstream = Socket()
        try {
            if (!vpnService.protect(upstream)) throw SocketException("VpnService.protect(TCP) failed")
            upstream.tcpNoDelay = true
            upstream.connect(InetSocketAddress(host, port), CONNECT_TIMEOUT_MS)
            writeReply(output, REP_SUCCEEDED)
            client.soTimeout = 0
            upstream.soTimeout = 0
            val down = workers.submit { copyStream(upstream.getInputStream(), client.getOutputStream()) }
            copyStream(client.getInputStream(), upstream.getOutputStream())
            down.cancel(true)
        } catch (error: Exception) {
            runCatching { writeReply(output, REP_HOST_UNREACHABLE) }
            throw error
        } finally {
            runCatching { upstream.close() }
        }
    }

    private fun udpAssociate(control: Socket, output: OutputStream) {
        val relay = DatagramSocket(null)
        try {
            if (!vpnService.protect(relay)) throw SocketException("VpnService.protect(UDP) failed")
            relay.reuseAddress = false
            relay.bind(InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0))
            udpSockets.add(relay)
            writeReply(output, REP_SUCCEEDED, InetAddress.getByName("127.0.0.1"), relay.localPort)
            val clientAddress = AtomicReference<InetSocketAddress?>(null)
            val buffer = ByteArray(MAX_UDP_PACKET)
            while (running.get() && !control.isClosed && !relay.isClosed) {
                val packet = DatagramPacket(buffer, buffer.size)
                relay.receive(packet)
                val source = InetSocketAddress(packet.address, packet.port)
                if (packet.address.isLoopbackAddress) {
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
        udpSockets.toList().forEach { runCatching { it.close() } }
        workers.shutdownNow()
    }

    companion object {
        const val DEFAULT_PORT = 10808
        private const val TAG = "JarvisSocks5"
        private const val SOCKS_VERSION = 5
        private const val METHOD_NO_AUTH = 0
        private const val METHOD_REJECT = 0xff
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
        private const val CONTROL_TIMEOUT_MS = 30_000
        private const val MAX_UDP_PACKET = 65_507
        private const val STREAM_BUFFER_SIZE = 32 * 1024
    }
}
