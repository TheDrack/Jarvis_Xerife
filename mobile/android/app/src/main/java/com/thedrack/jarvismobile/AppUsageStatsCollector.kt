package com.thedrack.jarvismobile

import android.app.AppOpsManager
import android.app.usage.NetworkStats
import android.app.usage.NetworkStatsManager
import android.content.Context
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.os.Process
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant

/** Package identity resolved locally by Android's PackageManager. */
data class AppPackageIdentity(
    val packageName: String,
    val appLabel: String,
    val isSystemApp: Boolean
)

/** One app UID's aggregate byte counters over the requested interval. */
data class AppUsageEntry(
    val uid: Int,
    val packageNames: List<String>,
    val wifiRxBytes: Long,
    val wifiTxBytes: Long,
    val mobileRxBytes: Long,
    val mobileTxBytes: Long,
    val packageIdentities: List<AppPackageIdentity> = emptyList()
) {
    val totalBytes: Long
        get() = listOf(wifiRxBytes, wifiTxBytes, mobileRxBytes, mobileTxBytes)
            .fold(0L) { total, value -> saturatingAdd(total, value) }

    companion object {
        private fun saturatingAdd(left: Long, right: Long): Long =
            if (Long.MAX_VALUE - left < right) Long.MAX_VALUE else left + right
    }
}

data class AppUsageSnapshot(
    val windowStart: String,
    val windowEnd: String,
    val apps: List<AppUsageEntry>,
    val status: String = "ok"
) {
    fun toPayload(): JSONObject {
        val entries = JSONArray()
        apps.forEach { app ->
            entries.put(
                JSONObject()
                    .put("uid", app.uid)
                    .put("package_names", JSONArray(app.packageNames.take(5)))
                    .put("packages", JSONArray().apply {
                        app.packageIdentities.take(5).forEach { identity ->
                            put(JSONObject()
                                .put("package_name", identity.packageName)
                                .put("app_label", identity.appLabel.take(128))
                                .put("is_system_app", identity.isSystemApp))
                        }
                    })
                    .put("wifi", JSONObject().put("rx_bytes", app.wifiRxBytes).put("tx_bytes", app.wifiTxBytes))
                    .put("mobile", JSONObject().put("rx_bytes", app.mobileRxBytes).put("tx_bytes", app.mobileTxBytes))
            )
        }
        return JSONObject()
            .put("platform", "android")
            .put("usage_access_opt_in", true)
            .put("collection_status", status)
            .put("window_start", windowStart)
            .put("window_end", windowEnd)
            .put("apps", entries)
    }
}

/**
 * Reads only Android's aggregate per-UID network counters. It never captures packets, destinations,
 * URLs, socket metadata, or application content. Calls must run on a worker thread.
 */
object AppUsageStatsCollector {
    private const val DEFAULT_WINDOW_MS = 24L * 60L * 60L * 1000L
    private const val MAX_APPS = 50

    fun isAuthorized(userOptIn: Boolean, usageAccessGranted: Boolean): Boolean =
        userOptIn && usageAccessGranted

    fun hasUsageAccess(context: Context): Boolean {
        val appOps = context.getSystemService(Context.APP_OPS_SERVICE) as? AppOpsManager ?: return false
        return try {
            appOps.checkOpNoThrow(
                AppOpsManager.OPSTR_GET_USAGE_STATS,
                Process.myUid(),
                context.packageName
            ) == AppOpsManager.MODE_ALLOWED
        } catch (_: RuntimeException) {
            false
        }
    }

    fun collect(
        context: Context,
        nowMillis: Long = System.currentTimeMillis(),
        windowMillis: Long = DEFAULT_WINDOW_MS,
        selectedPackages: Set<String> = emptySet()
    ): AppUsageSnapshot? {
        if (windowMillis <= 0L || nowMillis <= 0L || !hasUsageAccess(context)) return null
        val manager = context.getSystemService(Context.NETWORK_STATS_SERVICE) as? NetworkStatsManager ?: return null
        val start = (nowMillis - windowMillis).coerceAtLeast(0L)
        val counters = LinkedHashMap<Int, MutableCounters>()
        var successfulNetworks = 0

        successfulNetworks += readNetwork(manager, ConnectivityManager.TYPE_WIFI, start, nowMillis, counters)
        successfulNetworks += readNetwork(manager, ConnectivityManager.TYPE_MOBILE, start, nowMillis, counters)
        if (successfulNetworks == 0) return null

        val entries = counters.map { (uid, value) ->
            val packageNames = try {
                context.packageManager.getPackagesForUid(uid)
                    ?.filter { it.isNotBlank() }?.distinct()?.sorted()?.take(5).orEmpty()
            } catch (_: PackageManager.NameNotFoundException) {
                emptyList()
            } catch (_: RuntimeException) {
                emptyList()
            }
            val identities = packageNames.mapNotNull { packageName ->
                try {
                    @Suppress("DEPRECATION")
                    val info = context.packageManager.getApplicationInfo(packageName, 0)
                    val label = context.packageManager.getApplicationLabel(info).toString()
                        .ifBlank { packageName }.take(128)
                    AppPackageIdentity(
                        packageName = packageName,
                        appLabel = label,
                        isSystemApp = info.flags and (
                            android.content.pm.ApplicationInfo.FLAG_SYSTEM or
                                android.content.pm.ApplicationInfo.FLAG_UPDATED_SYSTEM_APP
                            ) != 0
                    )
                } catch (_: PackageManager.NameNotFoundException) {
                    null
                } catch (_: RuntimeException) {
                    null
                }
            }
            AppUsageEntry(
                uid = uid,
                packageNames = packageNames,
                wifiRxBytes = value.wifiRx,
                wifiTxBytes = value.wifiTx,
                mobileRxBytes = value.mobileRx,
                mobileTxBytes = value.mobileTx,
                packageIdentities = identities
            )
        }.let { filterEntries(it, selectedPackages) }
            .sortedByDescending { it.totalBytes }.take(MAX_APPS)

        return AppUsageSnapshot(
            windowStart = Instant.ofEpochMilli(start).toString(),
            windowEnd = Instant.ofEpochMilli(nowMillis).toString(),
            apps = entries,
            status = if (successfulNetworks == 2) "ok" else "partial"
        )
    }

    /** Empty selection means all visible UIDs; shared UIDs remain one indivisible record. */
    fun filterEntries(entries: List<AppUsageEntry>, selectedPackages: Set<String>): List<AppUsageEntry> {
        if (selectedPackages.isEmpty()) return entries
        return entries.filter { entry -> entry.packageNames.any(selectedPackages::contains) }
    }

    private fun readNetwork(
        manager: NetworkStatsManager,
        networkType: Int,
        start: Long,
        end: Long,
        counters: MutableMap<Int, MutableCounters>
    ): Int {
        var stats: NetworkStats? = null
        return try {
            val result = manager.querySummary(networkType, null, start, end) ?: return 0
            stats = result
            val bucket = NetworkStats.Bucket()
            while (result.hasNextBucket()) {
                if (!result.getNextBucket(bucket)) continue
                val uid = bucket.uid
                if (uid < 0) continue
                val current = counters.getOrPut(uid) { MutableCounters() }
                when (networkType) {
                    ConnectivityManager.TYPE_WIFI -> {
                        current.wifiRx = safeAdd(current.wifiRx, bucket.rxBytes)
                        current.wifiTx = safeAdd(current.wifiTx, bucket.txBytes)
                    }
                    ConnectivityManager.TYPE_MOBILE -> {
                        current.mobileRx = safeAdd(current.mobileRx, bucket.rxBytes)
                        current.mobileTx = safeAdd(current.mobileTx, bucket.txBytes)
                    }
                }
            }
            1
        } catch (_: Exception) {
            0
        } finally {
            try { stats?.close() } catch (_: Exception) { }
        }
    }

    private fun safeAdd(left: Long, right: Long): Long =
        if (right > 0L && Long.MAX_VALUE - left < right) Long.MAX_VALUE else left + right

    private data class MutableCounters(
        var wifiRx: Long = 0L,
        var wifiTx: Long = 0L,
        var mobileRx: Long = 0L,
        var mobileTx: Long = 0L
    )
}
