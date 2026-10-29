package com.thedrack.jarvismobile

import android.content.Context
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

object MobileApiClient {
    internal data class HttpResult(val code: Int, val body: String)

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
        var accessToken = vault.read() ?: refreshSession(context) ?: return null
        var result = perform(context, path, method, body, accessToken) ?: return null
        if (result.code == 401) {
            accessToken = refreshSession(context) ?: return null
            result = perform(context, path, method, body, accessToken) ?: return null
        }
        return result
    }

    /** GET sem autenticação (ex.: /v1/status). */
    internal fun publicGet(context: Context, path: String): HttpResult? =
        perform(context, path, "GET", null, null)

    private fun refreshSession(context: Context): String? {
        val vault = TokenVault(context)
        val refreshToken = vault.readRefreshToken() ?: return null
        val prefs = context.getSharedPreferences("jarvis_session", Context.MODE_PRIVATE)
        val deviceId = prefs.getString("bridge_device_id", null) ?: return null
        val body = JSONObject().put("refresh_token", refreshToken).put("device_id", deviceId).toString()
        val result = perform(context, "/v1/mobile/session/refresh", "POST", body, null) ?: return null
        if (result.code !in 200..299) return null
        return try {
            val payload = JSONObject(result.body)
            val access = payload.optString("access_token")
            val replacement = payload.optString("refresh_token")
            if (access.isBlank() || replacement.isBlank()) return null
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
