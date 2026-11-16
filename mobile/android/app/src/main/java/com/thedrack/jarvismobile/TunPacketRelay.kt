package com.thedrack.jarvismobile

import android.os.ParcelFileDescriptor
import android.system.ErrnoException
import android.system.Os
import android.system.OsConstants
import android.system.StructPollfd
import android.util.Log
import java.io.Closeable
import java.io.FileDescriptor
import java.io.IOException
import java.util.ArrayDeque
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Relays packet-preserving AF_UNIX datagrams between Android's TUN fd and Hev.
 * This provides a safe observation point without adding a second reader to the TUN fd.
 */
internal class TunPacketRelay private constructor(
    private val tun: ParcelFileDescriptor,
    private val bridge: ParcelFileDescriptor,
    private val flowCollector: FlowAttributionCollector,
    private val onFailure: (Throwable) -> Unit
) : Closeable {
    private val running = AtomicBoolean(false)
    @Volatile private var worker: Thread? = null
    private val toHev = ArrayDeque<ByteArray>()
    private val toTun = ArrayDeque<ByteArray>()

    val isRunning: Boolean
        get() = running.get() && worker?.isAlive == true

    fun start() {
        check(running.compareAndSet(false, true)) { "TUN packet relay already started" }
        worker = Thread(::runLoop, "Jarvis-TunPacketRelay").apply {
            isDaemon = true
            start()
        }
    }

    private fun runLoop() {
        val tunPoll = StructPollfd().apply { fd = tun.fileDescriptor }
        val bridgePoll = StructPollfd().apply { fd = bridge.fileDescriptor }
        val tunBuffer = ByteArray(MAX_PACKET_SIZE)
        val bridgeBuffer = ByteArray(MAX_PACKET_SIZE)

        try {
            while (running.get()) {
                tunPoll.events = (
                    (if (toHev.size < MAX_QUEUED_PACKETS) OsConstants.POLLIN else 0) or
                        (if (toTun.isNotEmpty()) OsConstants.POLLOUT else 0)
                    ).toShort()
                bridgePoll.events = (
                    (if (toTun.size < MAX_QUEUED_PACKETS) OsConstants.POLLIN else 0) or
                        (if (toHev.isNotEmpty()) OsConstants.POLLOUT else 0)
                    ).toShort()

                try {
                    Os.poll(arrayOf(tunPoll, bridgePoll), POLL_TIMEOUT_MS)
                } catch (error: ErrnoException) {
                    if (error.errno == OsConstants.EINTR) continue
                    throw error
                }
                if (!running.get()) break

                val tunEvents = tunPoll.revents.toInt()
                val bridgeEvents = bridgePoll.revents.toInt()
                checkNoPollError(tunEvents, "Android TUN")
                checkNoPollError(bridgeEvents, "Hev packet socket")

                if (tunEvents and OsConstants.POLLIN != 0) {
                    val count = readPacket(tun.fileDescriptor, tunBuffer)
                    if (count > 0) {
                        val packet = tunBuffer.copyOf(count)
                        runCatching {
                            IpPacketParser.parse(packet)?.let {
                                flowCollector.record(it, FlowPacketDirection.OUTBOUND)
                            }
                        }.onFailure { Log.w(TAG, "Outbound flow attribution failed", it) }
                        enqueue(toHev, packet)
                    }
                }

                if (bridgeEvents and OsConstants.POLLIN != 0) {
                    val count = readPacket(bridge.fileDescriptor, bridgeBuffer)
                    if (count > 0) {
                        val packet = bridgeBuffer.copyOf(count)
                        runCatching {
                            IpPacketParser.parse(packet)?.let {
                                flowCollector.record(it, FlowPacketDirection.INBOUND)
                            }
                        }.onFailure { Log.w(TAG, "Inbound flow attribution failed", it) }
                        enqueue(toTun, packet)
                    }
                }

                if (bridgeEvents and OsConstants.POLLOUT != 0) {
                    flushOne(bridge.fileDescriptor, toHev)
                }
                if (tunEvents and OsConstants.POLLOUT != 0) {
                    flushOne(tun.fileDescriptor, toTun)
                }
            }
        } catch (error: Throwable) {
            if (running.get()) {
                running.set(false)
                Log.e(TAG, "TUN packet relay stopped unexpectedly", error)
                runCatching { onFailure(error) }
            }
        } finally {
            running.set(false)
        }
    }

    private fun readPacket(fd: FileDescriptor, buffer: ByteArray): Int {
        return try {
            Os.read(fd, buffer, 0, buffer.size)
        } catch (error: ErrnoException) {
            if (error.errno == OsConstants.EAGAIN || error.errno == OsConstants.EWOULDBLOCK) 0
            else throw error
        }
    }

    private fun enqueue(queue: ArrayDeque<ByteArray>, packet: ByteArray) {
        if (queue.size >= MAX_QUEUED_PACKETS) {
            throw IOException("TUN relay packet queue reached its safety limit")
        }
        queue.addLast(packet)
    }

    private fun flushOne(fd: FileDescriptor, queue: ArrayDeque<ByteArray>) {
        val packet = queue.peekFirst() ?: return
        try {
            val written = Os.write(fd, packet, 0, packet.size)
            if (written != packet.size) {
                throw IOException("Partial packet write: $written/${packet.size}")
            }
            queue.removeFirst()
        } catch (error: ErrnoException) {
            if (error.errno != OsConstants.EAGAIN && error.errno != OsConstants.EWOULDBLOCK) {
                throw error
            }
        }
    }

    private fun checkNoPollError(events: Int, label: String) {
        val errorMask = OsConstants.POLLERR or OsConstants.POLLHUP or OsConstants.POLLNVAL
        if (events and errorMask != 0) throw IOException("$label poll failure: 0x${events.toString(16)}")
    }

    override fun close() {
        running.set(false)
        runCatching { bridge.close() }
        worker?.interrupt()
        runCatching { worker?.join(STOP_JOIN_TIMEOUT_MS) }
        worker = null
        toHev.clear()
        toTun.clear()
    }

    companion object {
        private const val TAG = "JarvisTunRelay"
        private const val MAX_PACKET_SIZE = 65_535
        private const val MAX_QUEUED_PACKETS = 128
        private const val POLL_TIMEOUT_MS = 200
        private const val STOP_JOIN_TIMEOUT_MS = 500L

        data class Pair(
            val hevDescriptor: ParcelFileDescriptor,
            val relay: TunPacketRelay
        )

        fun create(
            tun: ParcelFileDescriptor,
            flowCollector: FlowAttributionCollector,
            onFailure: (Throwable) -> Unit
        ): Pair {
            val descriptors = arrayOf(FileDescriptor(), FileDescriptor())
            Os.socketpair(
                OsConstants.AF_UNIX,
                OsConstants.SOCK_DGRAM,
                0,
                descriptors
            )
            var hev: ParcelFileDescriptor? = null
            var bridge: ParcelFileDescriptor? = null
            try {
                hev = ParcelFileDescriptor.dup(descriptors[0])
                bridge = ParcelFileDescriptor.dup(descriptors[1])
                setNonBlocking(tun.fileDescriptor)
                setNonBlocking(bridge.fileDescriptor)
                return Pair(
                    hevDescriptor = hev,
                    relay = TunPacketRelay(tun, bridge, flowCollector, onFailure)
                )
            } catch (error: Throwable) {
                runCatching { hev?.close() }
                runCatching { bridge?.close() }
                throw error
            } finally {
                runCatching { Os.close(descriptors[0]) }
                runCatching { Os.close(descriptors[1]) }
            }
        }

        private fun setNonBlocking(fd: FileDescriptor) {
            val flags = Os.fcntlInt(fd, OsConstants.F_GETFL, 0)
            Os.fcntlInt(fd, OsConstants.F_SETFL, flags or OsConstants.O_NONBLOCK)
        }
    }
}
