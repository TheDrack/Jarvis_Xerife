package com.thedrack.jarvismobile

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import java.util.UUID

class JarvisFirebaseMessagingService : FirebaseMessagingService() {
    override fun onCreate() {
        super.onCreate()
        FirebaseBootstrap.initialize(applicationContext)
    }

    override fun onNewToken(token: String) {
        try {
            TokenVault(applicationContext).savePushToken(token)
            MobilePushClient.registerCurrentDevice(applicationContext, token)
        } catch (_: Exception) {
            // Token refresh can be retried on the next app launch/login.
        }
    }

    override fun onMessageReceived(message: RemoteMessage) {
        val eventId = message.data["event_id"] ?: return
        val eventType = message.data["event_type"] ?: return
        if (eventType !in setOf("speak", "notification") || runCatching { UUID.fromString(eventId) }.isFailure) return

        val prefs = getSharedPreferences("jarvis_session", Context.MODE_PRIVATE)
        if (!prefs.getBoolean("presence_enabled", false)) return

        ensureNotificationChannel()
        if (eventType == "notification") {
            if (!canPostNotifications()) return
            val event = MobilePushClient.fetchEvent(applicationContext, eventId) ?: return
            if (event.eventType != "notification") return
            if (showEventNotification(eventId, event.title, event.text, launchSpeechOnTap = false)) {
                MobilePushClient.acknowledge(applicationContext, eventId)
            }
            return
        }

        showEventNotification(eventId)
        if (message.priority != RemoteMessage.PRIORITY_HIGH || !canPostNotifications()) return
        try {
            val intent = Intent(this, PushSpeechService::class.java)
                .putExtra(PushSpeechService.EXTRA_EVENT_ID, eventId)
            ContextCompat.startForegroundService(this, intent)
        } catch (_: Exception) {
            // The notification remains available if Android denies background speech startup.
        }
    }

    private fun canPostNotifications(): Boolean {
        if (!NotificationManagerCompat.from(this).areNotificationsEnabled()) return false
        return Build.VERSION.SDK_INT < 33 ||
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) ==
            PackageManager.PERMISSION_GRANTED
    }

    private fun ensureNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = getSystemService(NotificationManager::class.java)
        if (manager.getNotificationChannel(EVENT_CHANNEL_ID) == null) {
            manager.createNotificationChannel(
                NotificationChannel(
                    EVENT_CHANNEL_ID,
                    "Jarvis — avisos e presença",
                    NotificationManager.IMPORTANCE_HIGH
                ).apply { description = "Eventos de presença e mensagens de voz do Jarvis" }
            )
        }
    }

    private fun showEventNotification(
        eventId: String,
        title: String = "Jarvis",
        text: String = "O Jarvis tem uma mensagem de voz pronta.",
        launchSpeechOnTap: Boolean = true
    ): Boolean {
        val intent = Intent(this, MainActivity::class.java)
        if (launchSpeechOnTap) intent.putExtra(PushSpeechService.EXTRA_EVENT_ID, eventId)
        val pending = PendingIntent.getActivity(
            this,
            eventId.hashCode(),
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val notification = NotificationCompat.Builder(this, EVENT_CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(title)
            .setContentText(text)
            .setContentIntent(pending)
            .setCategory(NotificationCompat.CATEGORY_MESSAGE)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .build()
        return try {
            NotificationManagerCompat.from(this).notify(eventId.hashCode(), notification)
            true
        } catch (_: SecurityException) {
            false
        }
    }

    companion object {
        const val EVENT_CHANNEL_ID = "jarvis_push_events"
    }
}
