package com.thedrack.jarvismobile

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Per-installation pairing secret encrypted with Android Keystore.
 * It is shown only on the local pairing screen and never sent to the cloud.
 */
object AccessibilityBridgeCredentials {
    private const val PREFS = "jarvis_accessibility"
    private const val IV_KEY = "local_bridge_iv"
    private const val BODY_KEY = "local_bridge_body"
    private const val KEY_ALIAS = "jarvis_accessibility_bridge_key"

    fun getOrCreate(context: Context): String {
        read(context)?.let { return it }
        val bytes = ByteArray(32)
        SecureRandom().nextBytes(bytes)
        val token = Base64.encodeToString(bytes, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
        save(context, token)
        return token
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

    private fun read(context: Context): String? {
        val preferences = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val iv = preferences.getString(IV_KEY, null) ?: return null
        val body = preferences.getString(BODY_KEY, null) ?: return null
        return try {
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(
                Cipher.DECRYPT_MODE,
                getOrCreateKey(),
                GCMParameterSpec(128, Base64.decode(iv, Base64.NO_WRAP))
            )
            String(cipher.doFinal(Base64.decode(body, Base64.NO_WRAP)), Charsets.UTF_8)
                .takeIf { it.length == 43 }
        } catch (_: Exception) {
            preferences.edit().remove(IV_KEY).remove(BODY_KEY).commit()
            null
        }
    }

    private fun save(context: Context, token: String) {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey())
        val encrypted = cipher.doFinal(token.toByteArray(Charsets.UTF_8))
        val preferences = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        check(preferences.edit()
            .putString(IV_KEY, Base64.encodeToString(cipher.iv, Base64.NO_WRAP))
            .putString(BODY_KEY, Base64.encodeToString(encrypted, Base64.NO_WRAP))
            .commit()) { "Could not persist encrypted accessibility pairing token." }
    }

    private fun getOrCreateKey(): SecretKey {
        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (keyStore.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(
            KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true)
                .build()
        )
        return generator.generateKey()
    }
}
