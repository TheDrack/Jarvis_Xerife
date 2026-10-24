plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

fun buildConfigString(name: String): String {
    val value = System.getenv(name) ?: project.findProperty(name)?.toString().orEmpty()
    return value.replace("\\", "\\\\").replace("\"", "\\\"")
}

android {
    namespace = "com.thedrack.jarvismobile"
    compileSdk = 35
    defaultConfig {
        applicationId = "com.thedrack.jarvismobile"
        minSdk = 26
        targetSdk = 35
        versionCode = 2
        versionName = "0.2.0"
        buildConfigField("String", "DEFAULT_API_BASE_URL", "\"https://jarvis-api-c47i.onrender.com\"")
        buildConfigField("String", "FCM_API_KEY", "\"${buildConfigString("JARVIS_FCM_API_KEY")}\"")
        buildConfigField("String", "FCM_APP_ID", "\"${buildConfigString("JARVIS_FCM_APP_ID")}\"")
        buildConfigField("String", "FCM_PROJECT_ID", "\"${buildConfigString("JARVIS_FCM_PROJECT_ID")}\"")
        buildConfigField("String", "FCM_SENDER_ID", "\"${buildConfigString("JARVIS_FCM_SENDER_ID")}\"")
    }
    buildFeatures { compose = true; buildConfig = true }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2025.04.01")
    implementation(composeBom)
    implementation("androidx.activity:activity-compose:1.10.1")
    implementation("androidx.core:core-ktx:1.16.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation(platform("com.google.firebase:firebase-bom:35.1.0"))
    implementation("com.google.firebase:firebase-messaging")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.9.0")
    debugImplementation("androidx.compose.ui:ui-tooling")
}
