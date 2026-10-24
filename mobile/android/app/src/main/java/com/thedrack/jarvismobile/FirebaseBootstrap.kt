package com.thedrack.jarvismobile

import android.content.Context
import com.google.firebase.FirebaseApp
import com.google.firebase.FirebaseOptions

/** Firebase config is injected at build time; no google-services.json or secret is committed. */
object FirebaseBootstrap {
    fun initialize(context: Context): Boolean {
        if (FirebaseApp.getApps(context).any { it.name == FirebaseApp.DEFAULT_APP_NAME }) return true
        val apiKey = BuildConfig.FCM_API_KEY
        val appId = BuildConfig.FCM_APP_ID
        val projectId = BuildConfig.FCM_PROJECT_ID
        val senderId = BuildConfig.FCM_SENDER_ID
        if (apiKey.isBlank() || appId.isBlank() || projectId.isBlank() || senderId.isBlank()) {
            return false
        }
        return try {
            FirebaseApp.initializeApp(
                context,
                FirebaseOptions.Builder()
                    .setApiKey(apiKey)
                    .setApplicationId(appId)
                    .setProjectId(projectId)
                    .setGcmSenderId(senderId)
                    .build()
            ) != null
        } catch (_: Exception) {
            false
        }
    }
}
