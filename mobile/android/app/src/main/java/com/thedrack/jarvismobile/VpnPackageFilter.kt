package com.thedrack.jarvismobile

object VpnPackageFilter {
    fun parse(raw: String): List<String> =
        raw.split(Regex("[,;\\s]+"))
            .map(String::trim)
            .filter(String::isNotEmpty)
            .distinct()
}
