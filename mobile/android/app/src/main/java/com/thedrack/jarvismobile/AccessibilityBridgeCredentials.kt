package com.thedrack.jarvismobile

import android.content.Context
import android.util.Base64
import java.security.SecureRandom

/**
 * Pairing secret shared manually between the native app and its Termux MCP host.
 * It is generated per installation, stored in app-private preferences, and never
 * sent to the cloud or written to logs.
 */
object AccessibilityBridgeCredentials {
    private const val PREFS = "jarvis_accessibility"
    private const val TOKEN_KEY = "local_bridge_token"

    fun getOrCreate(context: Context): String {
        val preferences = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        preferences.getString(TOKEN_KEY, null)?.takeIf { it.length >= 40 }?.let { return it }

        val bytes = ByteArray(32)
        SecureRandom().nextBytes(bytes)
        return Base64.encodeToString(bytes, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
            .also { preferences.edit().putString(TOKEN_KEY, it).apply() }
    }

    fun isAuthorized(context: Context, authorization: String?): Boolean {
        if (authorization.isNullOrBlank() || !authorization.startsWith("Bearer ")) return false
        val supplied = authorization.removePrefix("Bearer ")
        val expected = getOrCreate(context)
        if (supplied.length != expected.length) return false
        var difference = 0
        for (index in expected.indices) difference = difference or (expected[index].code xor supplied[index].code)
        return difference == 0
    }
}
