package com.thedrack.jarvismobile

import android.content.Context
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Build

data class VpnRuntimeState(
    val vpnTransportActive: Boolean,
    val tailscaleInstalled: Boolean,
    val jarvisVpnActive: Boolean
) {
    val externalVpnActive: Boolean
        get() = vpnTransportActive && !jarvisVpnActive
}

/** Reads public Android state only; it never tries to take over an existing VPN. */
object VpnStateDetector {
    const val TAILSCALE_PACKAGE = "com.tailscale.ipn"

    fun detect(context: Context, jarvisVpnActive: Boolean = false): VpnRuntimeState {
        val manager = context.getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager
        val vpnActive = if (manager == null) {
            false
        } else {
            manager.allNetworks.any { network ->
                manager.getNetworkCapabilities(network)
                    ?.hasTransport(NetworkCapabilities.TRANSPORT_VPN) == true
            }
        }

        val tailscaleInstalled = try {
            if (Build.VERSION.SDK_INT >= 33) {
                context.packageManager.getPackageInfo(
                    TAILSCALE_PACKAGE,
                    PackageManager.PackageInfoFlags.of(0)
                )
            } else {
                @Suppress("DEPRECATION")
                context.packageManager.getPackageInfo(TAILSCALE_PACKAGE, 0)
            }
            true
        } catch (_: PackageManager.NameNotFoundException) {
            false
        } catch (_: RuntimeException) {
            false
        }

        return VpnRuntimeState(
            vpnTransportActive = vpnActive,
            tailscaleInstalled = tailscaleInstalled,
            jarvisVpnActive = jarvisVpnActive
        )
    }
}
