package com.thedrack.jarvismobile

object VpnPackageFilter {
    const val MAX_PACKAGES = 50

    fun parse(raw: String): List<String> {
        val packages = raw.split(Regex("[,;\\s]+"))
            .map(String::trim)
            .filter(String::isNotEmpty)
            .distinct()
        require(packages.size <= MAX_PACKAGES) {
            "At most $MAX_PACKAGES packages can be selected for VPN capture"
        }
        return packages
    }
}
