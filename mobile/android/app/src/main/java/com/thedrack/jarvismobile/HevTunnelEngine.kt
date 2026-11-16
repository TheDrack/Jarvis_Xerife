package com.thedrack.jarvismobile

import android.content.Context
import hev.htproxy.TProxyService
import java.io.File

internal class HevTunnelEngine(context: Context) {
    private val configFile = File(context.filesDir, "jarvis-hev-tunnel.yml")

    fun start(tunFd: Int): Boolean {
        check(tunFd >= 0) { "Invalid TUN file descriptor" }
        configFile.writeText(CONFIG, Charsets.UTF_8)
        val started = TProxyService.TProxyStartService(configFile.absolutePath, tunFd)
        if (!started) return false
        // JNI returns after creating the worker thread; allow its first poll cycle to fail fast on bad config.
        Thread.sleep(400)
        return TProxyService.TProxyIsRunning()
    }

    fun stop(): Boolean = TProxyService.TProxyStopService()

    fun isRunning(): Boolean = TProxyService.TProxyIsRunning()

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
        private const val CONFIG = """
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
)
