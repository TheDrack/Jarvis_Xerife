package com.thedrack.jarvismobile

/** Pure authorization gate for location collection; consent and both permission scopes are required. */
internal object LocationSharingPolicy {
    fun isAuthorized(
        userOptIn: Boolean,
        foregroundPermissionGranted: Boolean,
        backgroundPermissionGranted: Boolean,
        authenticated: Boolean
    ): Boolean = userOptIn && foregroundPermissionGranted && backgroundPermissionGranted && authenticated
}
