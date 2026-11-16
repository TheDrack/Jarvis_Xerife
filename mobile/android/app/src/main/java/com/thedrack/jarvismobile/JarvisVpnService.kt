package com.thedrack.jarvismobile

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.VpnService
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.ParcelFileDescriptor
import android.util.Log
import java.security.SecureRandom
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Explicitly user-started local VPN. It is intentionally not auto-started by
 * AUTO mode until device-level transition and connectivity tests are complete.
 */
class JarvisVpnService : VpnService() {
    private var tun: ParcelFileDescriptor? = null
    private var socksProxy: LocalSocks5Proxy? = null
    private var engine: HevTunnelEngine? = null
    private val stopping = AtomicBoolean(false)
    private val mainHandler = Handler(Looper.getMainLooper())
    private val engineWatchdog = object : Runnable {
        override fun run() {
            if (stopping.get() || tun == null) return
            if (engine?.isRunning() != true || socksProxy?.isRunning() != true) {
                Log.e(TAG, "Hev worker exited; closing TUN to restore normal network routing")
                stopTunnel()
                return
            }
            mainHandler.postDelayed(this, ENGINE_WATCHDOG_INTERVAL_MS)
        }
    }

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopTunnel()
            return START_NOT_STICKY
        }
        if (tun != null) return START_STICKY
        try {
            startTunnel()
            return START_STICKY
        } catch (error: Exception) {
            Log.e(TAG, "Jarvis VPN failed to start", error)
            stopTunnel()
            return START_NOT_STICKY
        }
    }

    private fun startTunnel() {
        check(HevRuntimeCompatibility.isSupported(Build.VERSION.SDK_INT)) {
            "Jarvis VPN requires Android API ${HevRuntimeCompatibility.MIN_ANDROID_API} or newer"
        }
        check(VpnService.prepare(this) == null) {
            "VPN permission has not been granted by the user"
        }
        val runtime = VpnStateDetector.detect(this)
        check(!runtime.externalVpnActive) {
            "Another VPN is active. Jarvis will not replace it automatically."
        }

        stopping.set(false)
        val socksUsername = newSocksCredential()
        val socksPassword = newSocksCredential()
        val proxy = LocalSocks5Proxy(this, socksUsername, socksPassword)
        proxy.start()
        socksProxy = proxy

        val builder = Builder()
            .setSession("Jarvis Network Monitor")
            .setMtu(TUN_MTU)
            .setBlocking(true)
            .addAddress(TUN_IPV4, 30)
            .addAddress(TUN_IPV6, 126)
            .addRoute("0.0.0.0", 0)
            .addRoute("::", 0)
            .addDnsServer(DNS_IPV4)

        val selectedPackages = VpnPackageFilter.parse(
            getSharedPreferences("jarvis_session", MODE_PRIVATE)
                .getString("app_usage_package_filter", "")
                .orEmpty()
        )
        if (selectedPackages.isEmpty()) {
            builder.addDisallowedApplication(packageName)
        } else {
            require(!selectedPackages.contains(packageName)) {
                "Jarvis itself cannot be included in its own VPN capture filter"
            }
            val missing = selectedPackages.filter {
                runCatching { packageManager.getApplicationInfo(it, 0) }.isFailure
            }
            require(missing.isEmpty()) {
                "Selected packages are not installed: ${missing.joinToString()}"
            }
            selectedPackages.forEach(builder::addAllowedApplication)
        }

        val descriptor = checkNotNull(builder.establish()) {
            "Android refused to establish the VPN interface"
        }
        tun = descriptor

        val nativeEngine = HevTunnelEngine(applicationContext)
        engine = nativeEngine
        check(nativeEngine.start(descriptor.fd, socksUsername, socksPassword)) {
            "Hev tun2socks failed to initialize"
        }
        check(nativeEngine.isRunning()) {
            "Hev tun2socks did not enter the running state"
        }
        activeEngine = nativeEngine
        isRunning = true

        startVpnForeground()
        getSystemService(NotificationManager::class.java)
            ?.notify(NOTIFICATION_ID, buildNotification("VPN Jarvis ativa — TCP/UDP encaminhados"))
        mainHandler.removeCallbacks(engineWatchdog)
        mainHandler.postDelayed(engineWatchdog, ENGINE_WATCHDOG_INTERVAL_MS)
    }

    private fun startVpnForeground() {
        val notification = buildNotification("Iniciando VPN Jarvis…")
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(
                NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_SYSTEM_EXEMPTED
            )
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    override fun onRevoke() {
        stopTunnel()
        super.onRevoke()
    }

    override fun onDestroy() {
        stopTunnel()
        super.onDestroy()
    }

    private fun stopTunnel() {
        if (!stopping.compareAndSet(false, true)) return
        mainHandler.removeCallbacks(engineWatchdog)
        runCatching { engine?.stop() }
            .onFailure { Log.w(TAG, "Hev shutdown reported an error", it) }
        engine = null
        activeEngine = null
        isRunning = false
        runCatching { tun?.close() }
        tun = null
        runCatching { socksProxy?.close() }
        socksProxy = null
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            stopForeground(STOP_FOREGROUND_REMOVE)
        } else {
            @Suppress("DEPRECATION")
            stopForeground(true)
        }
        stopSelf()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val channel = NotificationChannel(
            CHANNEL_ID,
            "Jarvis VPN",
            NotificationManager.IMPORTANCE_LOW
        ).apply {
            description = "Estado do encaminhamento de rede do Jarvis"
        }
        getSystemService(NotificationManager::class.java)?.createNotificationChannel(channel)
    }

    private fun buildNotification(status: String): Notification {
        val stopIntent = PendingIntent.getService(
            this,
            0,
            Intent(this, JarvisVpnService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, CHANNEL_ID)
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
        }
        return builder
            .setSmallIcon(android.R.drawable.stat_sys_warning)
            .setContentTitle("Jarvis Network Monitor")
            .setContentText(status)
            .setOngoing(true)
            .addAction(android.R.drawable.ic_menu_close_clear_cancel, "Desativar", stopIntent)
            .build()
    }

    companion object {
        @Volatile var isRunning: Boolean = false
            private set
        @Volatile private var activeEngine: HevTunnelEngine? = null

        internal fun currentStats(): HevTunnelStats {
            if (!isRunning) return HevTunnelStats.ZERO
            return runCatching { activeEngine?.stats() ?: HevTunnelStats.ZERO }
                .getOrDefault(HevTunnelStats.ZERO)
        }

        const val ACTION_START = "com.thedrack.jarvismobile.vpn.START"
        const val ACTION_STOP = "com.thedrack.jarvismobile.vpn.STOP"
        private const val TAG = "JarvisVpnService"
        private const val CHANNEL_ID = "jarvis_vpn"
        private const val NOTIFICATION_ID = 4208
        private const val TUN_MTU = 1500
        private const val TUN_IPV4 = "198.18.0.1"
        private const val TUN_IPV6 = "fc00::1"
        private const val DNS_IPV4 = "1.1.1.1"
        private const val ENGINE_WATCHDOG_INTERVAL_MS = 1_000L
        private fun newSocksCredential(): String {
            val bytes = ByteArray(24)
            SecureRandom().nextBytes(bytes)
            return bytes.joinToString("") { it.toUByte().toString(16).padStart(2, '0') }
        }

    }
}
