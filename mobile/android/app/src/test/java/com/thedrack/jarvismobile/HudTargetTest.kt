package com.thedrack.jarvismobile

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
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
}
