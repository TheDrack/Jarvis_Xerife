package com.thedrack.jarvismobile

import android.content.Context
import hev.htproxy.TProxyService
import java.io.File

internal class HevTunnelEngine(context: Context) {
    private val configFile = File(context.filesDir, "jarvis-hev-tunnel.yml")
    private var nativeStartReturned = false

    @Synchronized
    fun start(tunFd: Int, username: String, password: String): Boolean {
        check(tunFd >= 0) { "Invalid TUN file descriptor" }
        require(username.matches(Regex("[0-9a-f]{48}")) && password.matches(Regex("[0-9a-f]{48}"))) {
            "SOCKS credentials must be random 192-bit lowercase hex values"
        }
        configFile.writeText(config(username, password), Charsets.UTF_8)
        val started = TProxyService.TProxyStartService(configFile.absolutePath, tunFd)
        nativeStartReturned = true
        if (!started) return false
        // JNI returns after creating the worker thread; allow its first poll cycle to fail fast on bad config.
        Thread.sleep(400)
        return TProxyService.TProxyIsRunning()
    }

    @Synchronized
    fun stop(): Boolean {
        if (!nativeStartReturned) {
            configFile.delete()
            return true
        }
        return try {
            TProxyService.TProxyStopService()
        } finally {
            nativeStartReturned = false
            configFile.delete()
        }
    }

    fun isRunning(): Boolean = TProxyService.TProxyIsRunning()

    @Synchronized
    fun stats(): HevTunnelStats {
        val values = TProxyService.TProxyGetStats()
        return HevTunnelStats(
            txPackets = values.getOrElse(0) { 0L },
            txBytes = values.getOrElse(1) { 0L },
            rxPackets = values.getOrElse(2) { 0L },
            rxBytes = values.getOrElse(3) { 0L }
        )
    }

    companion object {
        private fun config(username: String, password: String) = """
tunnel:
  name: jarvis0
  mtu: 1500
  ipv4: 198.18.0.1
  ipv6: 'fc00::1'
  icmp: 'off'
socks5:
  address: 127.0.0.1
  port: 10808
  udp: 'udp'
  username: '$username'
  password: '$password'
misc:
  log-level: warn
  max-session-count: 2048
"""
    }
}

internal data class HevTunnelStats(
    val txPackets: Long,
    val txBytes: Long,
    val rxPackets: Long,
    val rxBytes: Long
) {
    companion object {
        val ZERO = HevTunnelStats(0, 0, 0, 0)
    }
}
