package com.thedrack.jarvismobile

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat

/**
 * Explicitly opted-in location publisher. Android's persistent foreground-service
 * notification remains visible while this service collects in the background.
 */
class LocationTrackingService : Service() {
    private val handler = Handler(Looper.getMainLooper())
    @Volatile private var stopping = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopSharingPreference()
            stopSelf(startId)
            return START_NOT_STICKY
        }
        if (!sharingIsAuthorized()) {
            stopSharingPreference()
            stopSelf(startId)
            return START_NOT_STICKY
        }
        stopping = false
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            ServiceCompat.startForeground(
                this,
                NOTIFICATION_ID,
                buildNotification(),
                ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION
            )
        } else {
            startForeground(NOTIFICATION_ID, buildNotification())
        }
        handler.removeCallbacks(publishRunnable)
        handler.post(publishRunnable)
        return START_STICKY
    }

    private fun sharingIsAuthorized(): Boolean {
        val prefs = getSharedPreferences("jarvis_session", MODE_PRIVATE)
        val foregroundGranted =
            ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED ||
                ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED
        val backgroundGranted = Build.VERSION.SDK_INT < Build.VERSION_CODES.Q ||
            ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_BACKGROUND_LOCATION) == PackageManager.PERMISSION_GRANTED
        return prefs.getBoolean("location_sharing_enabled", false) &&
            foregroundGranted && backgroundGranted &&
            TokenVault(applicationContext).readRefreshToken() != null
    }

    private val publishRunnable = object : Runnable {
        override fun run() {
            if (stopping || !sharingIsAuthorized()) {
                stopSharingPreference()
                stopSelf()
                return
            }
            val deviceId = getSharedPreferences("jarvis_session", MODE_PRIVATE)
                .getString("bridge_device_id", null)
            if (!deviceId.isNullOrBlank()) {
                Thread {
                    try {
                        EnvironmentObservationPublisher.publish(
                            applicationContext,
                            deviceId,
                            BridgeService.isRunning,
                            includeLocation = true
                        )
                    } catch (error: Exception) {
                        android.util.Log.w("JarvisMobile", "Background location publish failed: " + error.javaClass.simpleName)
                    }
                }.start()
            }
            handler.postDelayed(this, LOCATION_INTERVAL_MS)
        }
    }

    private fun stopSharingPreference() {
        getSharedPreferences("jarvis_session", MODE_PRIVATE).edit()
            .putBoolean("location_sharing_enabled", false).apply()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Compartilhamento de localização",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Indica quando o Jarvis está compartilhando a localização deste dispositivo."
            }
            getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
    }

    private fun buildNotification(): Notification {
        val openApp = PendingIntent.getActivity(
            this,
            1,
            Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_menu_mylocation)
            .setContentTitle("Jarvis — localização ativa")
            .setContentText("Compartilhamento em segundo plano ligado. Toque para gerenciar.")
            .setContentIntent(openApp)
            .setOngoing(true)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .build()
    }

    override fun onDestroy() {
        stopping = true
        handler.removeCallbacksAndMessages(null)
        super.onDestroy()
    }

    companion object {
        const val ACTION_STOP = "com.thedrack.jarvismobile.STOP_LOCATION_SHARING"
        private const val CHANNEL_ID = "jarvis_location_sharing"
        private const val NOTIFICATION_ID = 5822
        private const val LOCATION_INTERVAL_MS = 60_000L
    }
}
