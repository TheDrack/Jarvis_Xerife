package com.thedrack.jarvismobile

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertNotNull
import org.junit.Test

class TcpStreamReassemblerTest {
    @Test
    fun emitsContiguousPayloadAcrossInOrderSegments() {
        val reassembler = TcpStreamReassembler()

        assertArrayEquals("hello".toByteArray(), reassembler.append(100L, "hello".toByteArray()))
        assertArrayEquals("hello world".toByteArray(), reassembler.append(105L, " world".toByteArray()))
    }

    @Test
    fun buffersOutOfOrderSegmentUntilGapArrives() {
        val reassembler = TcpStreamReassembler()

        assertArrayEquals("world".toByteArray(), reassembler.append(106L, "world".toByteArray()))
        assertNull(reassembler.append(100L, "hello ".toByteArray()))
        // The gap-filling segment makes both pieces contiguous.
        assertArrayEquals("hello world", reassembler.snapshot())
    }

    @Test
    fun ignoresFullyRetransmittedBytesAndAppendsOnlyNewSuffix() {
        val reassembler = TcpStreamReassembler()
        reassembler.append(100L, "hello".toByteArray())

        assertNull(reassembler.append(100L, "hello".toByteArray()))
        assertArrayEquals("hello world".toByteArray(), reassembler.append(103L, "lo world".toByteArray()))
    }

    @Test
    fun handlesSequenceNumberWrapAround() {
        val reassembler = TcpStreamReassembler()

        assertArrayEquals("abc".toByteArray(), reassembler.append(0xffff_fffeL, "abc".toByteArray()))
        assertArrayEquals("abcdef".toByteArray(), reassembler.append(1L, "def".toByteArray()))
    }

    @Test
    fun rejectsSegmentsOutsideConfiguredGapAndMemoryBounds() {
        val reassembler = TcpStreamReassembler(maxBytes = 8, maxGapBytes = 8)

        assertNull(reassembler.append(100L, "a".toByteArray()))
        assertNull(reassembler.append(200L, "b".toByteArray()))
        assertNotNull(reassembler.snapshot())
        assertArrayEquals("a".toByteArray(), reassembler.snapshot())
    }
}
