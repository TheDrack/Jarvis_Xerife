package com.thedrack.jarvismobile

import android.content.Context
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.os.Build
import androidx.annotation.RequiresApi
import java.net.InetSocketAddress

/** Android adapter for the VPN-owner-only 5-tuple -> UID API (API 29+). */
@RequiresApi(Build.VERSION_CODES.Q)
internal fun createAndroidFlowAttributionCollector(
    context: Context,
    payloadMetadataEnabled: Boolean = false
): FlowAttributionCollector {
    val connectivity = context.getSystemService(ConnectivityManager::class.java)
        ?: error("ConnectivityManager is unavailable")
    val packageManager = context.packageManager

    val ownerResolver = ConnectionOwnerResolver { protocol, local, localPort, remote, remotePort ->
        connectivity.getConnectionOwnerUid(
            protocol,
            InetSocketAddress(local, localPort),
            InetSocketAddress(remote, remotePort)
        )
    }

    val packageResolver = PackageIdentityResolver { uid ->
        val packageNames = try {
            packageManager.getPackagesForUid(uid)
                ?.filter { it.isNotBlank() }
                ?.distinct()
                ?.sorted()
                ?.take(5)
                .orEmpty()
        } catch (_: RuntimeException) {
            emptyList()
        }
        packageNames.mapNotNull { packageName ->
            try {
                @Suppress("DEPRECATION")
                val info = packageManager.getApplicationInfo(packageName, 0)
                val label = packageManager.getApplicationLabel(info).toString()
                    .ifBlank { packageName }
                    .take(128)
                AppPackageIdentity(
                    packageName = packageName,
                    appLabel = label,
                    isSystemApp = info.flags and (
                        ApplicationInfo.FLAG_SYSTEM or ApplicationInfo.FLAG_UPDATED_SYSTEM_APP
                    ) != 0
                )
            } catch (_: PackageManager.NameNotFoundException) {
                null
            } catch (_: RuntimeException) {
                null
            }
        }
    }

    return FlowAttributionCollector(
        ownerResolver,
        packageResolver,
        payloadMetadataEnabled = payloadMetadataEnabled
    )
}
