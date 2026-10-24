package com.thedrack.jarvismobile

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import androidx.core.app.NotificationCompat
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.Locale
import java.util.concurrent.TimeUnit
import kotlin.math.min

/**
 * User-started, visible background connection to Jarvis.
 *
 * This is an opt-in foreground service, not a hidden always-on process. Android
 * may still stop/restrict it; the service reports its state in a persistent
 * notification and reconnects with bounded backoff while it remains alive.
 */
class BridgeService : Service() {
    private val handler = Handler(Looper.getMainLooper())
    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .build()
    @Volatile private var socket: WebSocket? = null
    private var tts: TextToSpeech? = null
    private lateinit var tokenVault: TokenVault
    private var ttsReady = false
    private var apiBaseUrl = ""
    private var token = ""
    private var deviceId = ""
    private var retryCount = 0
    private var stopping = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        isRunning = true
        tokenVault = TokenVault(applicationContext)
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopping = true
            stopSelf(startId)
            return START_NOT_STICKY
        }
        apiBaseUrl = intent?.getStringExtra(EXTRA_BASE_URL).orEmpty().trim().trimEnd('/')
        token = intent?.getStringExtra(EXTRA_TOKEN).orEmpty()
        deviceId = getSharedPreferences("jarvis_session", MODE_PRIVATE)
            .getString("bridge_device_id", null) ?: java.util.UUID.randomUUID().toString().also {
                getSharedPreferences("jarvis_session", MODE_PRIVATE).edit()
                    .putString("bridge_device_id", it).apply()
            }
        if (!apiBaseUrl.startsWith("https://") || token.isBlank()) {
            stopSelf(startId)
            return START_NOT_STICKY
        }

        stopping = false
        startForeground(NOTIFICATION_ID, buildNotification("Iniciando conexão segura…"))
        if (tts == null) {
            tts = TextToSpeech(applicationContext) { status ->
                ttsReady = status == TextToSpeech.SUCCESS
                if (ttsReady) {
                    tts?.language = Locale("pt", "BR")
                    tts?.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                        override fun onStart(utteranceId: String?) = Unit
                        override fun onDone(utteranceId: String?) {
                            if (!utteranceId.isNullOrBlank()) sendTaskResult(utteranceId, true, "speech_completed")
                        }
                        @Deprecated("Deprecated by Android; required for API compatibility")
                        override fun onError(utteranceId: String?) {
                            if (!utteranceId.isNullOrBlank()) sendTaskResult(utteranceId, false, "speech_failed")
                        }
                        override fun onError(utteranceId: String?, errorCode: Int) {
                            if (!utteranceId.isNullOrBlank()) sendTaskResult(utteranceId, false, "speech_failed_" + errorCode)
                        }
                    })
                    connect()
                } else {
                    updateNotification("Voz indisponível; conexão não iniciada")
                }
            }
        } else if (ttsReady) {
            connect()
        }
        return START_NOT_STICKY
    }

    private fun connect() {
        if (stopping || socket != null || !ttsReady) return
        try {
            val url = (apiBaseUrl + "/v1/local-bridge").toHttpUrl().newBuilder()
                .addQueryParameter("device_id", deviceId)
                .addQueryParameter("device_type", "mobile")
                .addQueryParameter("capabilities", "tts,notifications")
                .build()
            val request = Request.Builder().url(url).header("Authorization", "Bearer " + token).build()
            socket = client.newWebSocket(request, object : WebSocketListener() {
                override fun onOpen(webSocket: WebSocket, response: Response) {
                    retryCount = 0
                    updateNotification("Conectado ao Jarvis")
                    webSocket.send(JSONObject().put("type", "status").put("status", "ready").toString())
                }

                override fun onMessage(webSocket: WebSocket, text: String) {
                    handleMessage(webSocket, text)
                }

                override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                    socket = null
                    if (!stopping) scheduleReconnect()
                }

                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                    socket = null
                    if (response?.code == 403 || response?.code == 401) {
                        updateNotification("Sessão expirou; tentando renovação segura")
                        if (refreshSession()) {
                            retryCount = 0
                            scheduleReconnect()
                        } else {
                            updateNotification("Sessão expirada/revogada; reabra o app para entrar novamente")
                            stopping = true
                            stopSelf()
                        }
                        return
                    }
                    val detail = response?.code?.let { "Resposta HTTP $it" } ?: "sem resposta HTTP"
                    updateNotification("Canal do Jarvis indisponível ($detail); tentando reconectar")
                    if (!stopping) scheduleReconnect()
                }
            })
        } catch (_: Exception) {
            socket = null
            updateNotification("Não foi possível iniciar o canal do Jarvis; nova tentativa agendada")
            if (!stopping) scheduleReconnect()
        }
    }

    private fun handleMessage(webSocket: WebSocket, raw: String) {
        val message = try { JSONObject(raw) } catch (_: Exception) { return }
        if (message.optString("type") != "task") return
        val taskId = message.optString("task_id")
        if (taskId.isBlank() || taskId.length > 200) return
        val action = message.optString("action")
        if (action != "speak") {
            sendTaskResult(taskId, false, "unsupported_action")
            return
        }
        val parameters = message.optJSONObject("parameters") ?: JSONObject()
        val speechText = parameters.optString("text")
        if (speechText.isBlank() || speechText.length > 1000) {
            sendTaskResult(taskId, false, "invalid_text")
            return
        }
        if (!ttsReady || tts?.speak(speechText, TextToSpeech.QUEUE_ADD, null, taskId) != TextToSpeech.SUCCESS) {
            sendTaskResult(taskId, false, "tts_unavailable")
        }
    }

    private fun sendTaskResult(taskId: String, success: Boolean, result: String) {
        val payload = JSONObject()
            .put("type", "task_result")
            .put("task_id", taskId)
            .put("success", success)
            .put("result", result)
        socket?.send(payload.toString())
    }

    /** Rotate the refresh token after an expired access token; never log credentials. */
    private fun refreshSession(): Boolean {
        val refreshToken = tokenVault.readRefreshToken() ?: return false
        if (!apiBaseUrl.startsWith("https://") || deviceId.isBlank()) return false
        var connection: HttpURLConnection? = null
        return try {
            connection = (URL(apiBaseUrl.trimEnd('/') + "/v1/mobile/session/refresh")
                .openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"
                connectTimeout = 10000
                readTimeout = 10000
                doOutput = true
                setRequestProperty("Content-Type", "application/json")
            }
            val body = JSONObject()
                .put("refresh_token", refreshToken)
                .put("device_id", deviceId)
                .toString()
            connection.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            val response = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            if (code !in 200..299) return false
            val payload = JSONObject(response)
            val access = payload.optString("access_token")
            val replacement = payload.optString("refresh_token")
            if (access.isBlank() || replacement.isBlank()) return false
            tokenVault.save(access, replacement)
            token = access
            true
        } catch (_: Exception) {
            false
        } finally {
            connection?.disconnect()
        }
    }

    private fun scheduleReconnect() {
        if (stopping) return
        val delay = min(60_000L, 1_000L * (1L shl min(retryCount, 6)))
        retryCount += 1
        handler.removeCallbacks(reconnectRunnable)
        handler.postDelayed(reconnectRunnable, delay)
    }

    private val reconnectRunnable = Runnable {
        if (!stopping) connect()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Presença do Jarvis",
                NotificationManager.IMPORTANCE_LOW
            ).apply { description = "Conexão ativa do Jarvis Mobile" }
            getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
    }

    private fun buildNotification(status: String): Notification {
        val stopIntent = Intent(this, BridgeService::class.java).setAction(ACTION_STOP)
        val stopPendingIntent = PendingIntent.getService(
            this, 1, stopIntent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("Jarvis Mobile")
            .setContentText(status)
            .setOngoing(true)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .addAction(0, "Parar presença", stopPendingIntent)
            .build()
    }

    private fun updateNotification(status: String) {
        val manager = getSystemService(NotificationManager::class.java)
        manager.notify(NOTIFICATION_ID, buildNotification(status))
    }

    override fun onDestroy() {
        stopping = true
        isRunning = false
        handler.removeCallbacksAndMessages(null)
        socket?.close(1000, "service stopped")
        socket = null
        tts?.stop()
        tts?.shutdown()
        tts = null
        client.dispatcher.executorService.shutdown()
        super.onDestroy()
    }

    @Suppress("DEPRECATION")
    override fun onTimeout(startId: Int, fgsType: Int) {
        // Android 15+ caps dataSync foreground-service runtime. Stop cleanly
        // instead of repeatedly attempting a forbidden background restart.
        stopping = true
        stopSelf(startId)
    }

    companion object {
        const val ACTION_STOP = "com.thedrack.jarvismobile.STOP_BRIDGE"
        const val EXTRA_BASE_URL = "api_base_url"
        const val EXTRA_TOKEN = "access_token"
        private const val CHANNEL_ID = "jarvis_presence"
        private const val NOTIFICATION_ID = 5821
        @Volatile var isRunning: Boolean = false
            private set
    }
}
