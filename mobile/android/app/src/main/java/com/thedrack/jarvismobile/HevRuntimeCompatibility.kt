package com.thedrack.jarvismobile

object HevRuntimeCompatibility {
    const val MIN_ANDROID_API = 29
    fun isSupported(apiLevel: Int): Boolean = apiLevel >= MIN_ANDROID_API
}
