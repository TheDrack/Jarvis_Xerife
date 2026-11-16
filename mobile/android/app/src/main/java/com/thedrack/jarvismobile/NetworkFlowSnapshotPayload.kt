package com.thedrack.jarvismobile

data class PackageVersionSnapshot(
    val versionName: String,
    val versionCode: Long
)

data class NetworkFlowSnapshotEntry(
    val flow: NetworkFlowSnapshot,
    val packageVersions: List<Pair<String, PackageVersionSnapshot>>,
    val protocolObservations: List<NetworkProtocolObservation>
)

data class NetworkFlowSnapshotReport(
    val vpnTransportActive: Boolean,
    val jarvisVpnActive: Boolean,
    val tailscaleInstalled: Boolean,
    val captureOwner: String,
    val captureReason: String,
    val flowMetadataOptIn: Boolean,
    val payloadMetadataOptIn: Boolean,
    val flows: List<NetworkFlowSnapshotEntry>
)

/** Pure policy boundary for the authenticated, read-only local network snapshot endpoint. */
object NetworkFlowSnapshotPayload {
    fun build(
        runtime: VpnRuntimeState,
        flowSharingEnabled: Boolean,
        payloadMetadataEnabled: Boolean,
        flows: List<NetworkFlowSnapshot>,
        packageVersion: (String) -> PackageVersionSnapshot?
    ): NetworkFlowSnapshotReport {
        val payloadEnabled = flowSharingEnabled && payloadMetadataEnabled
        val jarvisOwnsVpn = runtime.vpnTransportActive && runtime.jarvisVpnActive
        val captureOwner = when {
            jarvisOwnsVpn -> "jarvis"
            runtime.externalVpnActive -> "external"
            else -> "none"
        }
        val reason = when {
            !flowSharingEnabled -> "flow_metadata_consent_disabled"
            !runtime.vpnTransportActive -> "vpn_not_active"
            !jarvisOwnsVpn -> "external_vpn_not_owned"
            flows.isEmpty() -> "no_active_flows"
            else -> "capturing"
        }
        val packageVersionCache = mutableMapOf<String, PackageVersionSnapshot?>()
        fun cachedPackageVersion(packageName: String): PackageVersionSnapshot? {
            if (packageVersionCache.containsKey(packageName)) return packageVersionCache[packageName]
            return packageVersion(packageName).also { packageVersionCache[packageName] = it }
        }
        val visibleFlows = if (flowSharingEnabled && jarvisOwnsVpn) {
            flows.take(FlowAttributionCollector.DEFAULT_SNAPSHOT_LIMIT).map { flow ->
                val versions = if (flow.attributionStatus == "resolved" && flow.packageNames.size == 1) {
                    flow.packageNames.mapNotNull { packageName ->
                        cachedPackageVersion(packageName)?.let { packageName to it }
                    }
                } else emptyList()
                NetworkFlowSnapshotEntry(
                    flow = flow,
                    packageVersions = versions,
                    protocolObservations = if (payloadEnabled) flow.protocolObservations.take(3) else emptyList()
                )
            }
        } else emptyList()
        return NetworkFlowSnapshotReport(
            vpnTransportActive = runtime.vpnTransportActive,
            jarvisVpnActive = runtime.jarvisVpnActive,
            tailscaleInstalled = runtime.tailscaleInstalled,
            captureOwner = captureOwner,
            captureReason = reason,
            flowMetadataOptIn = flowSharingEnabled,
            payloadMetadataOptIn = payloadEnabled,
            flows = visibleFlows
        )
    }
}
