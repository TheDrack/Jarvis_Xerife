package com.thedrack.jarvismobile

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class Socks5AuthenticatorTest {
    @Test
    fun acceptsOnlyExactCredentials() {
        assertTrue(
            Socks5Authenticator.matches(
                "user".toByteArray(), "secret".toByteArray(), "user", "secret"
            )
        )
    }

    @Test
    fun rejectsWrongUsernameOrPassword() {
        assertFalse(
            Socks5Authenticator.matches(
                "other".toByteArray(), "secret".toByteArray(), "user", "secret"
            )
        )
        assertFalse(
            Socks5Authenticator.matches(
                "user".toByteArray(), "wrong".toByteArray(), "user", "secret"
            )
        )
    }
}
