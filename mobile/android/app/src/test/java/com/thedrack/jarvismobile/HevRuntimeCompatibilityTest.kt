package com.thedrack.jarvismobile

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class HevRuntimeCompatibilityTest {
    @Test
    fun requiresAndroidApi29BecauseUpstreamAarUsesAndroid29NdkPlatform() {
        assertFalse(HevRuntimeCompatibility.isSupported(26))
        assertFalse(HevRuntimeCompatibility.isSupported(28))
        assertTrue(HevRuntimeCompatibility.isSupported(29))
        assertTrue(HevRuntimeCompatibility.isSupported(35))
    }
}
