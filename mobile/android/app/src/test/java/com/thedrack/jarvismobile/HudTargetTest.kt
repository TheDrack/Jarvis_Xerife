package com.thedrack.jarvismobile

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class HudTargetTest {

    @Test
    fun fillsTheSchemeWhenTheOperatorTypesOnlyHostAndPort() {
        assertEquals("http://192.168.0.15:8777", HudTarget.normalize("192.168.0.15:8777"))
    }

    @Test
    fun keepsHttpsAndDropsTrailingPath() {
        assertEquals("https://jarvis.example.com", HudTarget.normalize("https://jarvis.example.com/"))
    }

    @Test
    fun dropsPathAndQueryFromTheCoreAddress() {
        assertEquals("http://100.80.1.2:8777", HudTarget.normalize("http://100.80.1.2:8777/hud?area=europe"))
    }

    @Test
    fun rejectsBlankAndUnparsableAddresses() {
        assertNull(HudTarget.normalize("   "))
        assertNull(HudTarget.normalize("ftp://192.168.0.15:8777"))
    }

    @Test
    fun allowsOnlyTheExactConfiguredOrigin() {
        val expected = "http://192.168.0.15:8777"

        assertTrue(HudTarget.isSameOrigin(expected, expected))
        assertFalse(HudTarget.isSameOrigin("http://192.168.0.16:8777", expected))
        assertFalse(HudTarget.isSameOrigin("https://192.168.0.15:8777", expected))
        assertFalse(HudTarget.isSameOrigin("http://192.168.0.15:8777.evil", expected))
        assertFalse(HudTarget.isSameOrigin(null, expected))
    }

    @Test
    fun comparesDefaultPortsAndHostNamesCanonically() {
        assertTrue(HudTarget.isSameOrigin("http://EXAMPLE.com", "http://example.com:80"))
        assertTrue(HudTarget.isSameOrigin("https://EXAMPLE.com", "https://example.com:443"))
    }

    @Test
    fun rejectsUserInfoAndNonOriginPaths() {
        assertFalse(HudTarget.isSameOrigin("http://user@example.com", "http://example.com"))
        assertFalse(HudTarget.isSameOrigin("http://example.com/path", "http://example.com"))
    }
}
