package com.thedrack.jarvismobile

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
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
import java.util.concurrent.ConcurrentHashMap
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
        .pingInterval(25, TimeUnit.SECONDS)
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
    private val queuedEventIds = ConcurrentHashMap.newKeySet<String>()
    private var networkCallbackRegistered = false
    private val vpnNetworkCallback = object : ConnectivityManager.NetworkCallback() {
        override fun onAvailable(network: Network) = scheduleVpnObservation()
        override fun onLost(network: Network) = scheduleVpnObservation()
        override fun onCapabilitiesChanged(network: Network, capabilities: NetworkCapabilities) =
            scheduleVpnObservation()
    }
    private val vpnObservationRunnable = Runnable {
        if (!stopping) {
            reconcileVpnHandoff()
            publishEnvironmentObservations()
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        isRunning = true
        tokenVault = TokenVault(applicationContext)
        createNotificationChannel()
        registerVpnNetworkObserver()
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
                            if (!utteranceId.isNullOrBlank()) onSpeechCompleted(utteranceId, true, "speech_completed")
                        }
                        @Deprecated("Deprecated by Android; required for API compatibility")
                        override fun onError(utteranceId: String?) {
                            if (!utteranceId.isNullOrBlank()) onSpeechCompleted(utteranceId, false, "speech_failed")
                        }
                        override fun onError(utteranceId: String?, errorCode: Int) {
                            if (!utteranceId.isNullOrBlank()) onSpeechCompleted(utteranceId, false, "speech_failed_" + errorCode)
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
                    Thread {
                        try {
                            MobilePushClient.registerCurrentDevice(applicationContext, deviceId)
                            val pending = MobilePushClient.fetchPendingEvents(applicationContext)
                            handler.post { pending.forEach { handleQueuedEvent(it) } }
                        } catch (_: Exception) {
                            updateNotification("Conectado; fila móvel será sincronizada na próxima tentativa")
                        }
                    }.start()
                    publishEnvironmentObservations()
                    handler.removeCallbacks(observationRunnable)
                    handler.postDelayed(observationRunnable, OBSERVATION_INTERVAL_MS)
                }

                override fun onMessage(webSocket: WebSocket, text: String) {
                    handleMessage(webSocket, text)
                }

                override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                    if (socket !== webSocket) return
                    socket = null
                    if (!stopping) {
                        val closeReason = reason.take(60).ifBlank { "sem detalhe" }
                        updateNotification("Canal do Jarvis encerrado ($code: $closeReason); reconectando")
                        scheduleReconnect()
                    }
                }

                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                    if (socket !== webSocket) return
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
        val parameters = message.optJSONObject("parameters") ?: JSONObject()
        val text = parameters.optString("text").trim()
        when (action) {
            "speak" -> {
                if (text.isBlank() || text.length > 1000) {
                    sendTaskResult(taskId, false, "invalid_text")
                } else {
                    // The notification is best-effort; speech must continue when notifications are disabled.
                    showTaskNotification(taskId, "Jarvis", text)
                    if (!ttsReady || tts?.speak(text, TextToSpeech.QUEUE_ADD, null, taskId) != TextToSpeech.SUCCESS) {
                        sendTaskResult(taskId, false, "tts_unavailable")
                    }
                }
            }
            "notification" -> {
                val title = parameters.optString("title", "Jarvis").trim().ifBlank { "Jarvis" }
                if (text.isBlank() || text.length > 1000 || title.length > 80) {
                    sendTaskResult(taskId, false, "invalid_notification")
                } else if (showTaskNotification(taskId, title, text)) {
                    sendTaskResult(taskId, true, "notification_posted")
                } else {
                    sendTaskResult(taskId, false, "notifications_unavailable")
                }
            }
            else -> sendTaskResult(taskId, false, "unsupported_action")
        }
    }

    private fun showTaskNotification(taskId: String, title: String, text: String): Boolean {
        if (!NotificationManagerCompat.from(this).areNotificationsEnabled()) return false
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) return false
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            getSystemService(NotificationManager::class.java).createNotificationChannel(
                NotificationChannel(
                    EVENT_CHANNEL_ID,
                    "Jarvis — avisos e presença",
                    NotificationManager.IMPORTANCE_HIGH
                ).apply { description = "Notificações e avisos do Jarvis" }
            )
        }
        val intent = Intent(this, MainActivity::class.java)
        val pending = PendingIntent.getActivity(
            this, taskId.hashCode(), intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val notification = NotificationCompat.Builder(this, EVENT_CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(title)
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setContentIntent(pending)
            .setCategory(NotificationCompat.CATEGORY_MESSAGE)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .build()
        return try {
            NotificationManagerCompat.from(this).notify(taskId.hashCode(), notification)
            true
        } catch (_: SecurityException) {
            false
        }
    }

    private fun handleQueuedEvent(event: MobilePushEvent) {
        if (!queuedEventIds.add(event.eventId)) return
        when (event.eventType) {
            "notification" -> {
                if (showTaskNotification(event.eventId, event.title, event.text)) {
                    Thread { MobilePushClient.acknowledge(applicationContext, event.eventId) }.start()
                    queuedEventIds.remove(event.eventId)
                } else queuedEventIds.remove(event.eventId)
            }
            "speak" -> {
                if (!ttsReady || tts?.speak(event.text, TextToSpeech.QUEUE_ADD, null, event.eventId) != TextToSpeech.SUCCESS) queuedEventIds.remove(event.eventId)
            }
        }
    }

    private fun onSpeechCompleted(taskId: String, success: Boolean, result: String) {
        if (queuedEventIds.remove(taskId)) {
            if (success) Thread { MobilePushClient.acknowledge(applicationContext, taskId) }.start()
        } else sendTaskResult(taskId, success, result)
    }

    private fun sendTaskResult(taskId: String, success: Boolean, result: String) {
        val payload = JSONObject()
            .put("type", "task_result")
            .put("task_id", taskId)
            .put("success", success)
            .put("result", result)
        socket?.send(payload.toString())
    }

    /** Share the process-wide refresh coordinator to avoid concurrent token rotation. */
    private fun refreshSession(): Boolean {
        if (!apiBaseUrl.startsWith("https://") || deviceId.isBlank()) return false
        val refreshedAccessToken = MobilePushClient.refreshAccessToken(applicationContext, token)
            ?: return false
        token = refreshedAccessToken
        return true
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

    private val observationRunnable = object : Runnable {
        override fun run() {
            if (stopping) return
            reconcileVpnHandoff()
            publishEnvironmentObservations()
            handler.postDelayed(this, OBSERVATION_INTERVAL_MS)
        }
    }

    private fun registerVpnNetworkObserver() {
        val manager = getSystemService(ConnectivityManager::class.java) ?: return
        try {
            manager.registerDefaultNetworkCallback(vpnNetworkCallback)
            networkCallbackRegistered = true
        } catch (error: RuntimeException) {
            android.util.Log.w("JarvisMobile", "VPN network observer unavailable: " + error.javaClass.simpleName)
        }
    }

    private fun scheduleVpnObservation() {
        if (stopping) return
        handler.removeCallbacks(vpnObservationRunnable)
        handler.postDelayed(vpnObservationRunnable, 1_500L)
    }

    /**
     * Android owns VPN arbitration. When an external provider takes the VPN slot,
     * this service records the handoff and keeps publishing aggregate observations.
     * When that provider disappears, it asks the user to reactivate Jarvis from an
     * Activity so VpnService.prepare() can display Android's consent UI if required.
     */
    private fun reconcileVpnHandoff() {
        val preferences = getSharedPreferences("jarvis_session", MODE_PRIVATE)
        val runtime = VpnStateDetector.detect(
            applicationContext,
            jarvisVpnActive = JarvisVpnService.isRunning
        )
        val modePreference = VpnModePreference.fromWireValue(
            preferences.getString("vpn_mode_preference", VpnModePreference.AUTO.wireValue)
        )
        val externalWasActive = preferences.getBoolean(PREF_EXTERNAL_VPN_HANDOFF, false)
        val action = VpnHandoffPolicy.decide(
            externalVpnActive = runtime.externalVpnActive,
            jarvisVpnActive = runtime.jarvisVpnActive,
            externalVpnWasActive = externalWasActive,
            jarvisResumeAllowed = modePreference != VpnModePreference.TAILSCALE
        )

        when (action) {
            VpnHandoffAction.USE_EXTERNAL_VPN -> {
                preferences.edit()
                    .putBoolean(PREF_EXTERNAL_VPN_HANDOFF, true)
                    .putBoolean(PREF_VPN_RESUME_PROMPT_PENDING, false)
                    .apply()
                if (JarvisVpnService.isRunning) {
                    startService(
                        Intent(this, JarvisVpnService::class.java)
                            .setAction(JarvisVpnService.ACTION_STOP)
                    )
                }
                updateNotification("VPN externa ativa; Jarvis em observação agregada")
            }
            VpnHandoffAction.KEEP_JARVIS -> {
                preferences.edit()
                    .putBoolean(PREF_EXTERNAL_VPN_HANDOFF, false)
                    .putBoolean(PREF_VPN_RESUME_PROMPT_PENDING, false)
                    .apply()
            }
            VpnHandoffAction.PROMPT_JARVIS_RESUME -> {
                val alreadyPending = preferences.getBoolean(PREF_VPN_RESUME_PROMPT_PENDING, false)
                preferences.edit()
                    .putBoolean(PREF_EXTERNAL_VPN_HANDOFF, false)
                    .putBoolean(PREF_VPN_RESUME_PROMPT_PENDING, true)
                    .apply()
                if (!alreadyPending) showVpnResumeNotification()
            }
            VpnHandoffAction.WAIT_FOR_EXTERNAL_OR_USER -> {
                if (externalWasActive) {
                    preferences.edit()
                        .putBoolean(PREF_EXTERNAL_VPN_HANDOFF, false)
                        .putBoolean(PREF_VPN_RESUME_PROMPT_PENDING, false)
                        .apply()
                }
            }
        }
    }

    private fun showVpnResumeNotification() {
        if (!NotificationManagerCompat.from(this).areNotificationsEnabled()) {
            updateNotification("VPN externa desativada; abra Jarvis para reativar a VPN própria")
            return
        }
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            updateNotification("VPN externa desativada; abra Jarvis para reativar a VPN própria")
            return
        }
        val launchIntent = Intent(this, MainActivity::class.java)
            .setAction(MainActivity.ACTION_RESUME_JARVIS_VPN)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        val pendingIntent = PendingIntent.getActivity(
            this,
            VPN_RESUME_REQUEST_CODE,
            launchIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val notification = NotificationCompat.Builder(this, VPN_HANDOFF_CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_sys_warning)
            .setContentTitle("Jarvis VPN disponível")
            .setContentText("A VPN externa foi desativada. Toque para solicitar a reativação da VPN Jarvis.")
            .setStyle(
                NotificationCompat.BigTextStyle().bigText(
                    "A VPN externa foi desativada. Toque para solicitar a reativação da VPN Jarvis. O Android poderá pedir confirmação."
                )
            )
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
            .setCategory(NotificationCompat.CATEGORY_STATUS)
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .build()
        try {
            NotificationManagerCompat.from(this).notify(VPN_HANDOFF_NOTIFICATION_ID, notification)
        } catch (error: SecurityException) {
            updateNotification("VPN externa desativada; abra Jarvis para reativar a VPN própria")
        }
    }

    private fun publishEnvironmentObservations() {
        if (deviceId.isBlank() || token.isBlank()) return
        Thread {
            try {
                EnvironmentObservationPublisher.publish(applicationContext, deviceId, true)
            } catch (error: Exception) {
                android.util.Log.w("JarvisMobile", "Environment observation publish failed: " + error.javaClass.simpleName)
            }
        }.start()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Presença do Jarvis",
                NotificationManager.IMPORTANCE_LOW
            ).apply { description = "Conexão ativa do Jarvis Mobile" }
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
            manager.createNotificationChannel(
                NotificationChannel(
                    VPN_HANDOFF_CHANNEL_ID,
                    "Alternância de VPN",
                    NotificationManager.IMPORTANCE_DEFAULT
                ).apply { description = "Avisos de transferência entre a VPN Jarvis e provedores externos" }
            )
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
        if (networkCallbackRegistered) {
            runCatching {
                getSystemService(ConnectivityManager::class.java)?.unregisterNetworkCallback(vpnNetworkCallback)
            }
            networkCallbackRegistered = false
        }
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
        private const val VPN_HANDOFF_CHANNEL_ID = "jarvis_vpn_handoff"
        private const val VPN_HANDOFF_NOTIFICATION_ID = 5822
        private const val VPN_RESUME_REQUEST_CODE = 5823
        private const val PREF_EXTERNAL_VPN_HANDOFF = "vpn_external_handoff_active"
        private const val PREF_VPN_RESUME_PROMPT_PENDING = "vpn_resume_prompt_pending"
        const val EVENT_CHANNEL_ID = "jarvis_native_events"
        private const val OBSERVATION_INTERVAL_MS = 60_000L
        @Volatile var isRunning: Boolean = false
            private set
    }
}
