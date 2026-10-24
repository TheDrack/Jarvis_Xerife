package com.thedrack.jarvismobile

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Encrypts short-lived access and rotating refresh tokens using Android Keystore. */
class TokenVault(context: Context) {
    private val prefs = context.getSharedPreferences("jarvis_session", Context.MODE_PRIVATE)
    private val alias = "jarvis_mobile_token_key"

    fun save(accessToken: String, refreshToken: String? = null) {
        require(accessToken.isNotBlank()) { "Access token must not be blank" }
        val payload = accessToken + if (refreshToken.isNullOrBlank()) "" else "\n" + refreshToken
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey())
        val ciphertext = cipher.doFinal(payload.toByteArray(Charsets.UTF_8))
        val iv = Base64.encodeToString(cipher.iv, Base64.NO_WRAP)
        val body = Base64.encodeToString(ciphertext, Base64.NO_WRAP)
        check(prefs.edit().putString("iv", iv).putString("body", body).commit()) {
            "Could not persist encrypted session"
        }
    }

    fun read(): String? = readPayload()?.substringBefore('\n')?.takeIf { it.isNotBlank() }

    fun readRefreshToken(): String? = readPayload()?.let {
        it.substringAfter('\n', "").takeIf { refresh -> refresh.isNotBlank() }
    }

    private fun readPayload(): String? {
        val iv = prefs.getString("iv", null) ?: return null
        val body = prefs.getString("body", null) ?: return null
        return try {
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(
                Cipher.DECRYPT_MODE,
                getOrCreateKey(),
                GCMParameterSpec(128, Base64.decode(iv, Base64.NO_WRAP))
            )
            String(cipher.doFinal(Base64.decode(body, Base64.NO_WRAP)), Charsets.UTF_8)
        } catch (_: Exception) {
            clear()
            null
        }
    }

    fun savePushToken(token: String) {
        require(token.isNotBlank()) { "FCM token must not be blank" }
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey())
        val encrypted = cipher.doFinal(token.toByteArray(Charsets.UTF_8))
        check(
            prefs.edit()
                .putString("push_iv", Base64.encodeToString(cipher.iv, Base64.NO_WRAP))
                .putString("push_body", Base64.encodeToString(encrypted, Base64.NO_WRAP))
                .commit()
        ) { "Could not persist encrypted FCM token" }
    }

    fun readPushToken(): String? {
        val iv = prefs.getString("push_iv", null) ?: return null
        val body = prefs.getString("push_body", null) ?: return null
        return try {
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(
                Cipher.DECRYPT_MODE,
                getOrCreateKey(),
                GCMParameterSpec(128, Base64.decode(iv, Base64.NO_WRAP))
            )
            String(cipher.doFinal(Base64.decode(body, Base64.NO_WRAP)), Charsets.UTF_8)
                .takeIf { it.isNotBlank() }
        } catch (_: Exception) {
            prefs.edit().remove("push_iv").remove("push_body").commit()
            null
        }
    }

    fun clear() {
        prefs.edit().remove("iv").remove("body").remove("push_iv").remove("push_body").commit()
        try {
            KeyStore.getInstance("AndroidKeyStore").apply { load(null) }.deleteEntry(alias)
        } catch (_: Exception) {
            // Encrypted credentials are already removed; key cleanup is best-effort.
        }
    }

    private fun getOrCreateKey(): SecretKey {
        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (keyStore.getKey(alias, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(
            KeyGenParameterSpec.Builder(
                alias,
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
