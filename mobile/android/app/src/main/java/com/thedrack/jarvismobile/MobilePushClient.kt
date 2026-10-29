package com.thedrack.jarvismobile

import android.content.Context
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

data class MobilePushEvent(val eventId: String, val text: String)

object MobilePushClient {
    private val refreshLock = Any()

    internal data class HttpResult(val code: Int, val body: String)

    fun registerCurrentDevice(context: Context, fcmToken: String) {
        if (fcmToken.isBlank()) return
        TokenVault(context).savePushToken(fcmToken)
        val prefs = context.getSharedPreferences("jarvis_session", Context.MODE_PRIVATE)
        if (!prefs.getBoolean("presence_enabled", false)) return
        Thread {
            val deviceId = prefs.getString("bridge_device_id", null) ?: return@Thread
            request(
                context,
                "/v1/mobile/push/register",
                "POST",
                JSONObject().put("device_id", deviceId).put("fcm_token", fcmToken).toString()
            )
        }.start()
    }

    fun fetchEvent(context: Context, eventId: String): MobilePushEvent? {
        val result = request(context, "/v1/mobile/push/events/$eventId", "GET", null) ?: return null
        return try {
            val root = JSONObject(result.body)
            val payload = root.optJSONObject("payload") ?: return null
            if (payload.optString("action") != "speak") return null
            val parameters = payload.optJSONObject("parameters") ?: return null
            val text = parameters.optString("text").trim()
            if (text.isBlank() || text.length > 1000) return null
            MobilePushEvent(eventId, text)
        } catch (_: Exception) {
            null
        }
    }

    fun acknowledge(context: Context, eventId: String): Boolean =
        request(context, "/v1/mobile/push/events/$eventId/ack", "POST", null) != null

    fun revokePushNow(context: Context): Boolean {
        val prefs = context.getSharedPreferences("jarvis_session", Context.MODE_PRIVATE)
        val deviceId = prefs.getString("bridge_device_id", null) ?: return false
        return request(
            context,
            "/v1/mobile/push/revoke",
            "POST",
            JSONObject().put("device_id", deviceId).toString()
        ) != null
    }

    private fun request(
        context: Context,
        path: String,
        method: String,
        body: String?
    ): HttpResult? = authenticatedRequest(context, path, method, body)?.takeIf { it.code in 200..299 }

    /**
     * Chamada autenticada que devolve o status HTTP mesmo em erro (o chat mostra a mensagem do servidor).
     * Renova a sessão uma vez em 401.
     */
    internal fun authenticatedRequest(
        context: Context,
        path: String,
        method: String,
        body: String?
    ): HttpResult? {
        val vault = TokenVault(context)
        var accessToken = vault.read() ?: refreshAccessToken(context) ?: return null
        var result = perform(context, path, method, body, accessToken) ?: return null
        if (result.code == 401) {
            accessToken = refreshAccessToken(context, accessToken) ?: return null
            result = perform(context, path, method, body, accessToken) ?: return null
        }
        return result
    }

    /** GET sem autenticação (ex.: /v1/status). */
    internal fun publicGet(context: Context, path: String): HttpResult? =
        perform(context, path, "GET", null, null)

    /**
     * Single-flight refresh shared by the Activity, push client, and foreground bridge.
     * If another caller already rotated the token, reuse the newer access token instead
     * of replaying the old refresh token (which correctly revokes its token family).
     */
    internal fun refreshAccessToken(
        context: Context,
        rejectedAccessToken: String? = null
    ): String? = synchronized(refreshLock) {
        val vault = TokenVault(context)
        val latestAccess = vault.read()
        if (
            !rejectedAccessToken.isNullOrBlank() &&
            !latestAccess.isNullOrBlank() &&
            latestAccess != rejectedAccessToken
        ) {
            return@synchronized latestAccess
        }

        val refreshToken = vault.readRefreshToken() ?: return@synchronized null
        val prefs = context.getSharedPreferences("jarvis_session", Context.MODE_PRIVATE)
        val deviceId = prefs.getString("bridge_device_id", null) ?: return@synchronized null
        val body = JSONObject().put("refresh_token", refreshToken).put("device_id", deviceId).toString()
        val result = perform(context, "/v1/mobile/session/refresh", "POST", body, null)
            ?: return@synchronized null
        if (result.code !in 200..299) return@synchronized null
        try {
            val payload = JSONObject(result.body)
            val access = payload.optString("access_token")
            val replacement = payload.optString("refresh_token")
            if (access.isBlank() || replacement.isBlank()) return@synchronized null
            vault.save(access, replacement)
            access
        } catch (_: Exception) {
            null
        }
    }

    private fun perform(
        context: Context,
        path: String,
        method: String,
        body: String?,
        accessToken: String?
    ): HttpResult? {
        val prefs = context.getSharedPreferences("jarvis_session", Context.MODE_PRIVATE)
        val baseUrl = (prefs.getString("api_base_url", BuildConfig.DEFAULT_API_BASE_URL)
            ?: BuildConfig.DEFAULT_API_BASE_URL).trimEnd('/')
        if (!baseUrl.startsWith("https://")) return null
        var connection: HttpURLConnection? = null
        return try {
            connection = (URL(baseUrl + path).openConnection() as HttpURLConnection).apply {
                requestMethod = method
                connectTimeout = 8000
                readTimeout = 8000
                setRequestProperty("Accept", "application/json")
                if (!accessToken.isNullOrBlank()) setRequestProperty("Authorization", "Bearer $accessToken")
                if (body != null) {
                    doOutput = true
                    setRequestProperty("Content-Type", "application/json")
                }
            }
            if (body != null) connection.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            val response = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            HttpResult(code, response)
        } catch (_: Exception) {
            null
        } finally {
            connection?.disconnect()
        }
    }
}
