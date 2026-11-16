package com.thedrack.jarvismobile

import java.security.MessageDigest
import java.nio.charset.StandardCharsets

object Socks5Authenticator {
    fun matches(
        suppliedUsername: ByteArray,
        suppliedPassword: ByteArray,
        expectedUsername: String,
        expectedPassword: String
    ): Boolean {
        val usernameMatches = MessageDigest.isEqual(
            suppliedUsername,
            expectedUsername.toByteArray(StandardCharsets.US_ASCII)
        )
        val passwordMatches = MessageDigest.isEqual(
            suppliedPassword,
            expectedPassword.toByteArray(StandardCharsets.US_ASCII)
        )
        return usernameMatches and passwordMatches
    }
}
