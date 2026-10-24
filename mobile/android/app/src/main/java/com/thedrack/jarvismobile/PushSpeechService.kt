package com.thedrack.jarvismobile

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import androidx.core.app.NotificationCompat
import java.util.ArrayDeque
import java.util.Locale
import java.util.UUID

class PushSpeechService : Service() {
    private val mainHandler = Handler(Looper.getMainLooper())
    private val eventQueue = ArrayDeque<String>()
    private val seenEventIds = HashSet<String>()
    private var tts: TextToSpeech? = null
    private var ttsReady = false
    private var processing = false
    private var startReceived = false
    private var ttsInitFailed = false

    override fun onCreate() {
        super.onCreate()
        ensureChannel()
        tts = TextToSpeech(applicationContext) { status ->
            if (status == TextToSpeech.SUCCESS) {
                val languageStatus = tts?.setLanguage(Locale("pt", "BR")) ?: TextToSpeech.ERROR
                ttsReady = languageStatus != TextToSpeech.LANG_MISSING_DATA &&
                    languageStatus != TextToSpeech.LANG_NOT_SUPPORTED
                tts?.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                    override fun onStart(utteranceId: String?) = Unit

                    override fun onDone(utteranceId: String?) {
                        val eventId = utteranceId ?: return
                        Thread {
                            MobilePushClient.acknowledge(applicationContext, eventId)
                            mainHandler.post {
                                processing = false
                                processNext()
                            }
                        }.start()
                    }

                    override fun onError(utteranceId: String?) {
                        mainHandler.post {
                            processing = false
                            processNext()
                        }
                    }
                })
                if (ttsReady) {
                    mainHandler.post { processNext() }
                } else {
                    ttsInitFailed = true
                    if (startReceived) stopSelf()
                }
            } else {
                ttsInitFailed = true
                if (startReceived) stopSelf()
            }
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startReceived = true
        startForegroundNotification()
        if (ttsInitFailed) {
            stopIfIdle()
            return START_NOT_STICKY
        }
        val eventId = intent?.getStringExtra(EXTRA_EVENT_ID)
        if (eventId.isNullOrBlank() || runCatching { UUID.fromString(eventId) }.isFailure) {
            stopIfIdle()
            return START_NOT_STICKY
        }
        if (seenEventIds.add(eventId)) eventQueue.addLast(eventId)
        processNext()
        return START_NOT_STICKY
    }

    private fun processNext() {
        if (!ttsReady || processing) return
        val eventId = eventQueue.pollFirst()
        if (eventId == null) {
            stopIfIdle()
            return
        }
        val prefs = getSharedPreferences("jarvis_session", MODE_PRIVATE)
        if (!prefs.getBoolean("presence_enabled", false)) {
            processNext()
            return
        }
        processing = true
        Thread {
            val event = MobilePushClient.fetchEvent(applicationContext, eventId)
            mainHandler.post {
                if (event == null) {
                    processing = false
                    processNext()
                    return@post
                }
                val result = tts?.speak(
                    event.text,
                    TextToSpeech.QUEUE_FLUSH,
                    null,
                    event.eventId
                ) ?: TextToSpeech.ERROR
                if (result == TextToSpeech.ERROR) {
                    processing = false
                    processNext()
                }
            }
        }.start()
    }

    private fun ensureChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = getSystemService(NotificationManager::class.java)
        if (manager.getNotificationChannel(SPEECH_CHANNEL_ID) == null) {
            manager.createNotificationChannel(
                NotificationChannel(
                    SPEECH_CHANNEL_ID,
                    "Jarvis — reprodução de voz",
                    NotificationManager.IMPORTANCE_LOW
                ).apply { description = "Indicador visível enquanto o Jarvis fala" }
            )
        }
    }

    private fun startForegroundNotification() {
        val pending = PendingIntent.getActivity(
            this,
            7401,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val notification = NotificationCompat.Builder(this, SPEECH_CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("Jarvis")
            .setContentText("Reproduzindo mensagem de voz")
            .setContentIntent(pending)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .setOngoing(true)
            .build()
        if (Build.VERSION.SDK_INT >= 29) {
            startForeground(
                NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK
            )
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    private fun stopIfIdle() {
        if (!startReceived || processing || eventQueue.isNotEmpty()) return
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    override fun onDestroy() {
        tts?.stop()
        tts?.shutdown()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    companion object {
        const val EXTRA_EVENT_ID = "event_id"
        private const val SPEECH_CHANNEL_ID = "jarvis_push_speech"
        private const val NOTIFICATION_ID = 7401
    }
}
