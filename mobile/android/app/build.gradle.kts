import java.io.File
import java.net.URL
import java.security.MessageDigest

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
        versionCode = System.getenv("ANDROID_VERSION_CODE")?.toIntOrNull() ?: 2
        versionName = "0.2.0"
        buildConfigField("String", "DEFAULT_API_BASE_URL", "\"https://jarvis-api-c47i.onrender.com\"")
        buildConfigField("String", "GOOGLE_WEB_CLIENT_ID", "\"${buildConfigString("GOOGLE_WEB_CLIENT_ID")}\"")
    }
    buildFeatures { compose = true; buildConfig = true }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    signingConfigs {
        create("release") {
            System.getenv("ANDROID_KEYSTORE_PATH")?.let { path ->
                storeFile = file(path)
                storePassword = System.getenv("ANDROID_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("ANDROID_KEY_ALIAS")
                keyPassword = System.getenv("ANDROID_KEY_PASSWORD")
            }
        }
    }
    buildTypes {
        release {
            signingConfig = signingConfigs.getByName("release")
        }
    }
}

val hevAarFile = layout.buildDirectory.file("third_party/hev-socks5-tunnel-2.20.0.aar")
val hevAarSha256 = "ae8a2e96b80b4eccccd037805a4bb4a278090c89dbcae8bc6fcb7634e9a255b9"
val downloadHevAar = tasks.register("downloadHevAar") {
    val aar = hevAarFile.get().asFile
    outputs.file(aar)
    inputs.property("hevAarSha256", hevAarSha256)
    doLast {
        fun sha256(file: java.io.File): String =
            MessageDigest.getInstance("SHA-256")
                .digest(file.readBytes()).joinToString("") { it.toUByte().toString(16).padStart(2, '0') }

        aar.parentFile.mkdirs()
        if (!aar.isFile || sha256(aar) != hevAarSha256) {
            val temporary = File(aar.parentFile, aar.name + ".part")
            val url = URL(
                "https://github.com/heiher/hev-socks5-tunnel/releases/download/2.20.0/hev-socks5-tunnel.aar"
            )
            val connection = url.openConnection().apply {
                connectTimeout = 15_000
                readTimeout = 45_000
            }
            connection.getInputStream().use { input ->
                temporary.outputStream().use { output -> input.copyTo(output) }
            }
            check(sha256(temporary) == hevAarSha256) {
                "Hev AAR SHA-256 mismatch; refusing to use an unverified native dependency"
            }
            if (aar.exists()) check(aar.delete()) { "Cannot replace previous Hev AAR" }
            check(temporary.renameTo(aar)) { "Cannot install verified Hev AAR" }
        }
        check(sha256(aar) == hevAarSha256) { "Hev AAR verification failed" }
    }
}

tasks.named("preBuild").configure { dependsOn(downloadHevAar) }

dependencies {
    implementation(files(hevAarFile))
    val composeBom = platform("androidx.compose:compose-bom:2025.04.01")
    implementation(composeBom)
    implementation("androidx.activity:activity-compose:1.10.1")
    implementation("androidx.core:core-ktx:1.16.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.google.android.gms:play-services-auth:21.3.0")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.9.0")
    debugImplementation("androidx.compose.ui:ui-tooling")
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
}
