package com.thedrack.jarvismobile

/** Pure transition policy for handing the Android VPN slot between Jarvis and another provider. */
enum class VpnHandoffAction {
    KEEP_JARVIS,
    USE_EXTERNAL_VPN,
    PROMPT_JARVIS_RESUME,
    WAIT_FOR_EXTERNAL_OR_USER
}

object VpnHandoffPolicy {
    fun decide(
        externalVpnActive: Boolean,
        jarvisVpnActive: Boolean,
        externalVpnWasActive: Boolean,
        jarvisResumeAllowed: Boolean
    ): VpnHandoffAction = when {
        externalVpnActive -> VpnHandoffAction.USE_EXTERNAL_VPN
        jarvisVpnActive -> VpnHandoffAction.KEEP_JARVIS
        externalVpnWasActive && jarvisResumeAllowed -> VpnHandoffAction.PROMPT_JARVIS_RESUME
        else -> VpnHandoffAction.WAIT_FOR_EXTERNAL_OR_USER
    }
}
