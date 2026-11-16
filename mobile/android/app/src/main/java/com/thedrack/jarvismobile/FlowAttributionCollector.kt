package com.thedrack.jarvismobile

import java.time.Instant
import java.util.UUID

enum class FlowPacketDirection {
    OUTBOUND,
    INBOUND
}

fun interface ConnectionOwnerResolver {
    fun resolve(
        protocolNumber: Int,
        localAddress: java.net.InetAddress,
        localPort: Int,
        remoteAddress: java.net.InetAddress,
        remotePort: Int
    ): Int
}

fun interface PackageIdentityResolver {
    fun resolve(uid: Int): List<AppPackageIdentity>
}

data class NetworkFlowSnapshot(
    val flowId: String,
    val protocol: String,
    val localIp: String,
    val localPort: Int,
    val remoteIp: String,
    val remotePort: Int,
    val uid: Int?,
    val packageNames: List<String>,
    val appLabel: String?,
    val attributionStatus: String,
    val firstSeenAt: String,
    val lastSeenAt: String,
    val txPackets: Long,
    val txBytes: Long,
    val rxPackets: Long,
    val rxBytes: Long,
    val closed: Boolean
)

/**
 * Aggregates only IP/transport headers and packet lengths. It never stores packet payloads.
 * The tuple is normalized to app-local -> remote, regardless of packet direction.
 */
internal class FlowAttributionCollector(
    private val ownerResolver: ConnectionOwnerResolver,
    private val packageResolver: PackageIdentityResolver,
    private val clock: () -> Long = System::currentTimeMillis,
    private val maxFlows: Int = DEFAULT_MAX_FLOWS,
    private val maxAgeMillis: Long = DEFAULT_MAX_AGE_MS,
    private val idleSessionMillis: Long = DEFAULT_IDLE_SESSION_MS
) {
    private data class FlowKey(
        val protocolNumber: Int,
        val localIp: String,
        val localPort: Int,
        val remoteIp: String,
        val remotePort: Int
    )

    private data class MutableFlow(
        val key: FlowKey,
        val flowId: String,
        val firstSeenMillis: Long,
        var lastSeenMillis: Long,
        var uid: Int? = null,
        var packageNames: List<String> = emptyList(),
        var appLabel: String? = null,
        var attributionStatus: String = "unresolved",
        var txPackets: Long = 0,
        var txBytes: Long = 0,
        var rxPackets: Long = 0,
        var rxBytes: Long = 0,
        var closed: Boolean = false
    )

    private val flows = LinkedHashMap<FlowKey, MutableFlow>(16, 0.75f, true)
    private val packageCache = HashMap<Int, List<AppPackageIdentity>>()

    @Synchronized
    fun record(packet: ParsedIpPacket, direction: FlowPacketDirection) {
        val outbound = direction == FlowPacketDirection.OUTBOUND
        val localAddress = if (outbound) packet.sourceAddress else packet.destinationAddress
        val localPort = if (outbound) packet.sourcePort else packet.destinationPort
        val remoteAddress = if (outbound) packet.destinationAddress else packet.sourceAddress
        val remotePort = if (outbound) packet.destinationPort else packet.sourcePort
        val key = FlowKey(
            protocolNumber = packet.protocolNumber,
            localIp = localAddress.hostAddress,
            localPort = localPort,
            remoteIp = remoteAddress.hostAddress,
            remotePort = remotePort
        )
        val now = clock()
        val existing = flows[key]
        val isInitialTcpSyn = outbound &&
            packet.protocolNumber == TCP_PROTOCOL &&
            packet.tcpFlags?.and(TCP_SYN) == TCP_SYN &&
            packet.tcpFlags?.and(TCP_ACK) != TCP_ACK
        val startsNewTcpSession = existing?.closed == true && isInitialTcpSyn
        val expired = existing != null && now - existing.lastSeenMillis > idleSessionMillis
        val flow = if (existing == null || startsNewTcpSession || expired) {
            val created = MutableFlow(
                key = key,
                flowId = UUID.randomUUID().toString(),
                firstSeenMillis = now,
                lastSeenMillis = now
            )
            resolveAttribution(created, packet, localAddress, localPort, remoteAddress, remotePort)
            flows[key] = created
            created
        } else {
            existing
        }

        flow.lastSeenMillis = now
        if (packet.protocolNumber == TCP_PROTOCOL &&
            packet.tcpFlags?.and(TCP_FIN or TCP_RST) != 0
        ) flow.closed = true
        if (outbound) {
            flow.txPackets = saturatingAdd(flow.txPackets, 1)
            flow.txBytes = saturatingAdd(flow.txBytes, packet.packetBytes.toLong())
        } else {
            flow.rxPackets = saturatingAdd(flow.rxPackets, 1)
            flow.rxBytes = saturatingAdd(flow.rxBytes, packet.packetBytes.toLong())
        }
        prune(now)
    }

    @Synchronized
    fun snapshot(limit: Int = DEFAULT_SNAPSHOT_LIMIT): List<NetworkFlowSnapshot> {
        require(limit in 1..DEFAULT_SNAPSHOT_LIMIT)
        prune(clock())
        return flows.values
            .sortedByDescending { it.lastSeenMillis }
            .take(limit)
            .map { flow ->
                NetworkFlowSnapshot(
                    flowId = flow.flowId,
                    protocol = if (flow.key.protocolNumber == TCP_PROTOCOL) "tcp" else "udp",
                    localIp = flow.key.localIp,
                    localPort = flow.key.localPort,
                    remoteIp = flow.key.remoteIp,
                    remotePort = flow.key.remotePort,
                    uid = flow.uid,
                    packageNames = flow.packageNames.take(5),
                    appLabel = flow.appLabel?.take(128),
                    attributionStatus = flow.attributionStatus,
                    firstSeenAt = Instant.ofEpochMilli(flow.firstSeenMillis).toString(),
                    lastSeenAt = Instant.ofEpochMilli(flow.lastSeenMillis).toString(),
                    txPackets = flow.txPackets,
                    txBytes = flow.txBytes,
                    rxPackets = flow.rxPackets,
                    rxBytes = flow.rxBytes,
                    closed = flow.closed
                )
            }
    }

    @Synchronized
    fun clear() {
        flows.clear()
        packageCache.clear()
    }

    private fun resolveAttribution(
        flow: MutableFlow,
        packet: ParsedIpPacket,
        localAddress: java.net.InetAddress,
        localPort: Int,
        remoteAddress: java.net.InetAddress,
        remotePort: Int
    ) {
        val uid = try {
            ownerResolver.resolve(
                packet.protocolNumber,
                localAddress,
                localPort,
                remoteAddress,
                remotePort
            )
        } catch (_: SecurityException) {
            flow.attributionStatus = "denied"
            return
        } catch (_: RuntimeException) {
            flow.attributionStatus = "unresolved"
            return
        }
        if (uid < 0) {
            flow.attributionStatus = "unresolved"
            return
        }
        flow.uid = uid
        val identities = packageCache.getOrPut(uid) {
            runCatching { packageResolver.resolve(uid).take(5) }.getOrDefault(emptyList())
        }
        flow.packageNames = identities.map { it.packageName }.distinct().take(5)
        flow.appLabel = identities.firstOrNull()?.appLabel?.take(128)
        flow.attributionStatus = if (flow.packageNames.isEmpty()) "uid_only" else "resolved"
    }

    private fun prune(now: Long) {
        val staleKeys = flows.values
            .filter { now - it.lastSeenMillis > maxAgeMillis }
            .map { it.key }
        staleKeys.forEach(flows::remove)
        while (flows.size > maxFlows) {
            val oldest = flows.values.minByOrNull { it.lastSeenMillis } ?: break
            flows.remove(oldest.key)
        }
    }

    private fun saturatingAdd(left: Long, right: Long): Long =
        if (Long.MAX_VALUE - left < right) Long.MAX_VALUE else left + right

    companion object {
        private const val TCP_PROTOCOL = 6
        private const val TCP_SYN = 0x02
        private const val TCP_ACK = 0x10
        private const val TCP_FIN = 0x01
        private const val TCP_RST = 0x04
        const val DEFAULT_SNAPSHOT_LIMIT = 50
        private const val DEFAULT_MAX_FLOWS = 1_000
        private const val DEFAULT_MAX_AGE_MS = 10 * 60 * 1_000L
        private const val DEFAULT_IDLE_SESSION_MS = 60 * 1_000L
    }
}
