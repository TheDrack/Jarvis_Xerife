package com.thedrack.jarvismobile

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class LocationSharingPolicyTest {
    @Test
    fun sharingIsOffUnlessEveryGateIsSatisfied() {
        assertFalse(LocationSharingPolicy.isAuthorized(false, true, true, true))
        assertFalse(LocationSharingPolicy.isAuthorized(true, false, true, true))
        assertFalse(LocationSharingPolicy.isAuthorized(true, true, false, true))
        assertFalse(LocationSharingPolicy.isAuthorized(true, true, true, false))
        assertTrue(LocationSharingPolicy.isAuthorized(true, true, true, true))
    }
}
