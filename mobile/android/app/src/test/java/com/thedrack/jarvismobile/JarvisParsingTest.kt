package com.thedrack.jarvismobile

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class JarvisParsingTest {
    @Test
    fun successfulReplyKeepsText() {
        val reply = JarvisParsing.parseChatReply(200, """{"success":true,"response":"Olá, senhor.","error":null}""")
        assertTrue(reply.success)
        assertEquals("Olá, senhor.", reply.text)
        assertNull(reply.error)
    }

    @Test
    fun nullResponseFieldIsNotTreatedAsText() {
        val reply = JarvisParsing.parseChatReply(200, """{"success":false,"response":null,"error":"falhou"}""")
        assertFalse(reply.success)
        assertEquals("", reply.text)
        assertEquals("falhou", reply.error)
    }

    @Test
    fun unauthorizedAsksForNewLogin() {
        val reply = JarvisParsing.parseChatReply(401, "{}")
        assertFalse(reply.success)
        assertTrue(reply.error!!.contains("Entre novamente"))
    }

    @Test
    fun rateLimitIsExplained() {
        val reply = JarvisParsing.parseChatReply(429, "")
        assertTrue(reply.error!!.contains("Aguarde"))
    }

    @Test
    fun serverErrorIncludesStatus() {
        val reply = JarvisParsing.parseChatReply(500, "boom")
        assertTrue(reply.error!!.contains("500"))
    }

    @Test
    fun malformedBodyIsRejectedSafely() {
        val reply = JarvisParsing.parseChatReply(200, "não é json")
        assertFalse(reply.success)
        assertTrue(reply.error!!.contains("inválida"))
    }

    @Test
    fun statusParsesPublicFields() {
        val status = JarvisParsing.parseStatus(
            200,
            """{"app_name":"Jarvis","version":"1.2","is_active":true,"wake_word":"jarvis","language":"pt-BR"}"""
        )!!
        assertEquals("Jarvis", status.appName)
        assertTrue(status.isActive)
        assertEquals("jarvis", status.wakeWord)
    }

    @Test
    fun statusFailureReturnsNull() {
        assertNull(JarvisParsing.parseStatus(503, "{}"))
        assertNull(JarvisParsing.parseStatus(200, "{quebrado"))
    }
}
