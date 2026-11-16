package com.thedrack.jarvismobile

import java.io.ByteArrayOutputStream

/**
 * Bounded, per-direction TCP byte-stream reconstruction.
 *
 * The first observed payload anchors the sequence window. Segments arriving after
 * that point are appended in order, bounded out-of-order segments are buffered,
 * and retransmitted overlap is discarded. Sequence arithmetic is wrap-safe for
 * windows smaller than 2^31 bytes. This class does not parse protocols or retain
 * packet objects.
 */
internal class TcpStreamReassembler(
    private val maxBytes: Int = DEFAULT_MAX_BYTES,
    private val maxGapBytes: Int = DEFAULT_MAX_GAP_BYTES,
    private val maxOutOfOrderSegments: Int = DEFAULT_MAX_OUT_OF_ORDER_SEGMENTS
) {
    private data class Segment(val sequence: Long, val bytes: ByteArray)

    private val stream = ByteArrayOutputStream()
    private val pending = mutableListOf<Segment>()
    private var nextSequence: Long? = null
    private var failed = false

    init {
        require(maxBytes > 0)
        require(maxGapBytes >= 0)
        require(maxOutOfOrderSegments > 0)
    }

    /**
     * Adds one TCP payload segment and returns the contiguous stream snapshot
     * when new contiguous bytes were accepted. Returns null for duplicates,
     * buffered gaps, invalid sequence values, or a stream that exceeded its cap.
     */
    @Synchronized
    fun append(sequenceNumber: Long, payload: ByteArray): ByteArray? {
        if (failed || payload.isEmpty() || sequenceNumber !in 0..SEQUENCE_MASK) return null
        if (payload.size > maxBytes) {
            failClosed()
            return null
        }

        val expected = nextSequence
        if (expected == null) {
            if (!appendContiguous(payload)) return null
            nextSequence = (sequenceNumber + payload.size) and SEQUENCE_MASK
            drainPending()
            return snapshot()
        }

        val distance = sequenceDistance(sequenceNumber, expected)
        if (distance > 0) {
            if (distance > maxGapBytes || pending.size >= maxOutOfOrderSegments) return null
            if (pending.any { it.sequence == sequenceNumber }) return null
            val pendingBytes = pending.sumOf { it.bytes.size }
            if (pendingBytes + payload.size > maxBytes - stream.size()) return null
            pending += Segment(sequenceNumber, payload.copyOf())
            return null
        }

        val overlap = (-distance).coerceAtMost(payload.size.toLong()).toInt()
        if (overlap >= payload.size) return null
        if (!appendContiguous(payload.copyOfRange(overlap, payload.size))) return null
        drainPending()
        return snapshot()
    }

    @Synchronized
    fun snapshot(): ByteArray? = if (failed || stream.size() == 0) null else stream.toByteArray()

    @Synchronized
    fun clear() {
        stream.reset()
        pending.forEach { it.bytes.fill(0) }
        pending.clear()
        nextSequence = null
        failed = false
    }

    private fun drainPending() {
        while (true) {
            val expected = nextSequence ?: return
            val candidate = pending
                .map { it to sequenceDistance(it.sequence, expected) }
                .filter { (_, distance) -> distance <= 0 }
                .maxByOrNull { (_, distance) -> distance }
                ?: return
            val (segment, distance) = candidate
            pending.remove(segment)
            val overlap = (-distance).coerceAtMost(segment.bytes.size.toLong()).toInt()
            if (overlap < segment.bytes.size) {
                val suffix = segment.bytes.copyOfRange(overlap, segment.bytes.size)
                appendContiguous(suffix)
                suffix.fill(0)
            }
            segment.bytes.fill(0)
            if (failed) return
        }
    }

    private fun appendContiguous(bytes: ByteArray): Boolean {
        if (stream.size() + bytes.size > maxBytes) {
            failClosed()
            return false
        }
        stream.write(bytes)
        nextSequence = ((nextSequence ?: 0L) + bytes.size) and SEQUENCE_MASK
        return true
    }

    private fun failClosed() {
        failed = true
        stream.reset()
        pending.forEach { it.bytes.fill(0) }
        pending.clear()
        nextSequence = null
    }

    private fun sequenceDistance(sequence: Long, expected: Long): Long {
        val unsigned = (sequence - expected) and SEQUENCE_MASK
        return if (unsigned >= SEQUENCE_HALF_RANGE) unsigned - SEQUENCE_MODULUS else unsigned
    }

    private companion object {
        const val DEFAULT_MAX_BYTES = 16 * 1024
        const val DEFAULT_MAX_GAP_BYTES = 16 * 1024
        const val DEFAULT_MAX_OUT_OF_ORDER_SEGMENTS = 16
        const val SEQUENCE_MASK = 0xffff_ffffL
        const val SEQUENCE_HALF_RANGE = 0x8000_0000L
        const val SEQUENCE_MODULUS = 0x1_0000_0000L
    }
}
