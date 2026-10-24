package com.thedrack.jarvismobile

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.os.Build
import android.speech.tts.TextToSpeech
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.ContextCompat
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.google.firebase.messaging.FirebaseMessaging
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.Locale
import java.util.concurrent.Executors

class MainActivity : ComponentActivity() {
    private lateinit var vault: TokenVault
    private var speech: TextToSpeech? = null
    private val executor = Executors.newSingleThreadExecutor()
    private val speechReady = mutableStateOf(false)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        vault = TokenVault(this)
        if (FirebaseBootstrap.initialize(this) && vault.readRefreshToken() != null) {
            registerFcmToken()
        }
        speech = TextToSpeech(this) { status ->
            speechReady.value = status == TextToSpeech.SUCCESS
            if (status == TextToSpeech.SUCCESS) speech?.language = Locale("pt", "BR")
        }
        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    JarvisMobileScreen(
                        initialBaseUrl = getSharedPreferences("jarvis_session", MODE_PRIVATE)
                            .getString("api_base_url", BuildConfig.DEFAULT_API_BASE_URL) ?: BuildConfig.DEFAULT_API_BASE_URL,
                        isLoggedInInitially = vault.read() != null && vault.readRefreshToken() != null,
                        speechReady = speechReady.value,
                        presenceInitiallyActive = BridgeService.isRunning,
                        onLogin = ::login,
                        onLogout = ::logout,
                        onStartPresence = ::startPresence,
                        onStopPresence = ::stopPresence,
                        onSpeak = { speak("Jarvis Mobile ativo. Canal de voz local funcionando.") }
                    )
                }
            }
        }
        handlePushIntent(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handlePushIntent(intent)
    }

    private fun handlePushIntent(source: Intent?) {
        val eventId = source?.getStringExtra(PushSpeechService.EXTRA_EVENT_ID) ?: return
        val prefs = getSharedPreferences("jarvis_session", MODE_PRIVATE)
        if (!prefs.getBoolean("presence_enabled", false) || vault.readRefreshToken().isNullOrBlank()) return
        val speechIntent = Intent(this, PushSpeechService::class.java)
            .putExtra(PushSpeechService.EXTRA_EVENT_ID, eventId)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) startForegroundService(speechIntent) else startService(speechIntent)
    }

    private fun login(baseUrl: String, username: String, password: String, result: (String?) -> Unit) {
        executor.execute {
            var connection: HttpURLConnection? = null
            val outcome = try {
                val normalized = baseUrl.trim().trimEnd('/')
                require(normalized.startsWith("https://")) { "Use uma URL HTTPS." }
                connection = (URL(normalized + "/v1/mobile/session/login").openConnection() as HttpURLConnection).apply {
                    requestMethod = "POST"
                    connectTimeout = 10000
                    readTimeout = 10000
                    doOutput = true
                    setRequestProperty("Content-Type", "application/json")
                }
                val body = JSONObject()
                    .put("username", username)
                    .put("password", password)
                    .put("device_id", getOrCreateDeviceId())
                    .toString()
                connection.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
                val code = connection.responseCode
                val stream = if (code in 200..299) connection.inputStream else connection.errorStream
                val response = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
                if (code !in 200..299) {
                    when (code) {
                        401 -> "Credenciais inválidas. Confira o e-mail/usuário e a senha."
                        404 -> "A API publicada ainda não contém o login móvel (HTTP 404). O servidor precisa ser atualizado."
                        503 -> "O servidor está sem o armazenamento seguro de sessões configurado (HTTP 503)."
                        else -> "Login recusado pelo servidor (HTTP " + code + ")."
                    }
                } else {
                    val payload = JSONObject(response)
                    val token = payload.optString("access_token")
                    val refreshToken = payload.optString("refresh_token")
                    if (token.isBlank() || refreshToken.isBlank()) "Resposta de sessão móvel incompleta."
                    else {
                        vault.save(token, refreshToken)
                        getSharedPreferences("jarvis_session", MODE_PRIVATE).edit()
                            .putString("api_base_url", normalized).apply()
                        null
                    }
                }
            } catch (error: Exception) {
                "Falha de conexão/login: " + (error.message ?: error.javaClass.simpleName)
            } finally {
                connection?.disconnect()
            }
            runOnUiThread {
                result(outcome)
                if (outcome == null) registerFcmToken()
            }
        }
    }

    private fun registerFcmToken() {
        if (!FirebaseBootstrap.initialize(applicationContext)) return
        try {
            FirebaseMessaging.getInstance().token.addOnCompleteListener { task ->
                if (task.isSuccessful) {
                    task.result?.takeIf { it.isNotBlank() }?.let { token ->
                        MobilePushClient.registerCurrentDevice(applicationContext, token)
                    }
                }
            }
        } catch (_: Exception) {
            // FCM remains optional until the Firebase project configuration is injected at build time.
        }
    }

    private fun getOrCreateDeviceId(): String {
        val prefs = getSharedPreferences("jarvis_session", MODE_PRIVATE)
        return prefs.getString("bridge_device_id", null) ?: java.util.UUID.randomUUID().toString().also {
            prefs.edit().putString("bridge_device_id", it).apply()
        }
    }

    private fun logout() {
        val refreshToken = vault.readRefreshToken()
        val prefs = getSharedPreferences("jarvis_session", MODE_PRIVATE)
        val deviceId = prefs.getString("bridge_device_id", null)
        val baseUrl = prefs.getString("api_base_url", BuildConfig.DEFAULT_API_BASE_URL)
            ?: BuildConfig.DEFAULT_API_BASE_URL
        stopPresence()
        executor.execute {
            try {
                if (!refreshToken.isNullOrBlank()) MobilePushClient.revokePushNow(applicationContext)
                // Push revocation may refresh/rotate the session; revoke with the latest token.
                val currentRefreshToken = vault.readRefreshToken() ?: refreshToken
                if (!currentRefreshToken.isNullOrBlank() && !deviceId.isNullOrBlank() && baseUrl.startsWith("https://")) {
                    val connection = (URL(baseUrl.trimEnd('/') + "/v1/mobile/session/revoke")
                        .openConnection() as HttpURLConnection)
                    try {
                        connection.requestMethod = "POST"
                        connection.connectTimeout = 5000
                        connection.readTimeout = 5000
                        connection.doOutput = true
                        connection.setRequestProperty("Content-Type", "application/json")
                        val body = JSONObject()
                            .put("refresh_token", currentRefreshToken)
                            .put("device_id", deviceId)
                            .toString()
                        connection.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
                        connection.responseCode
                    } finally {
                        connection.disconnect()
                    }
                }
            } catch (_: Exception) {
                // Local logout must still complete when the phone is offline.
            } finally {
                vault.clear()
            }
        }
    }

    private fun startPresence() {
        val accessToken = vault.read() ?: return
        val prefs = getSharedPreferences("jarvis_session", MODE_PRIVATE)
        prefs.edit().putBoolean("presence_enabled", true).apply()
        registerFcmToken()
        val baseUrl = prefs.getString("api_base_url", BuildConfig.DEFAULT_API_BASE_URL)
            ?: BuildConfig.DEFAULT_API_BASE_URL
        val intent = Intent(this, BridgeService::class.java)
            .putExtra(BridgeService.EXTRA_BASE_URL, baseUrl)
            .putExtra(BridgeService.EXTRA_TOKEN, accessToken)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) startForegroundService(intent) else startService(intent)
    }

    private fun stopPresence() {
        getSharedPreferences("jarvis_session", MODE_PRIVATE).edit()
            .putBoolean("presence_enabled", false).apply()
        stopService(Intent(this, BridgeService::class.java))
        stopService(Intent(this, PushSpeechService::class.java))
    }

    private fun speak(text: String) {
        speech?.speak(text, TextToSpeech.QUEUE_FLUSH, null, "jarvis-mobile-local-tts")
    }

    override fun onDestroy() {
        speech?.stop()
        speech?.shutdown()
        executor.shutdownNow()
        super.onDestroy()
    }
}

@Composable
private fun JarvisMobileScreen(
    initialBaseUrl: String,
    isLoggedInInitially: Boolean,
    speechReady: Boolean,
    presenceInitiallyActive: Boolean,
    onLogin: (String, String, String, (String?) -> Unit) -> Unit,
    onLogout: () -> Unit,
    onStartPresence: () -> Unit,
    onStopPresence: () -> Unit,
    onSpeak: () -> Unit
) {
    var baseUrl by remember { mutableStateOf(initialBaseUrl) }
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var loggedIn by remember { mutableStateOf(isLoggedInInitially) }
    var presenceActive by remember { mutableStateOf(presenceInitiallyActive) }
    var busy by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("Entre e ative a presença para receber eventos do Jarvis.") }
    val context = LocalContext.current
    val notificationPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) {
            onStartPresence()
            presenceActive = true
            message = "Presença ativada; o Jarvis pode enviar avisos e voz em segundo plano."
        } else {
            presenceActive = false
            message = "A permissão de notificações é necessária para a presença em segundo plano."
        }
    }

    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text("J.A.R.V.I.S.", style = MaterialTheme.typography.headlineLarge)
        Text("Companheiro Android", modifier = Modifier.padding(top = 8.dp))
        Text(
            if (speechReady) "Voz local disponível" else "Inicializando mecanismo de voz…",
            modifier = Modifier.padding(top = 12.dp)
        )
        Button(onClick = onSpeak, enabled = speechReady, modifier = Modifier.padding(top = 12.dp)) {
            Text("Testar voz")
        }
        if (!loggedIn) {
            OutlinedTextField(
                baseUrl, { baseUrl = it }, label = { Text("API HTTPS") },
                modifier = Modifier.fillMaxWidth().padding(top = 12.dp), singleLine = true
            )
            OutlinedTextField(
                username, { username = it }, label = { Text("Usuário") },
                modifier = Modifier.fillMaxWidth().padding(top = 8.dp), singleLine = true
            )
            OutlinedTextField(
                password, { password = it }, label = { Text("Senha (não será salva)") },
                modifier = Modifier.fillMaxWidth().padding(top = 8.dp), singleLine = true,
                visualTransformation = PasswordVisualTransformation()
            )
            Button(
                onClick = {
                    busy = true
                    message = "Autenticando…"
                    onLogin(baseUrl, username, password) { error ->
                        busy = false
                        password = ""
                        loggedIn = error == null
                        message = error ?: "Autenticado. Token protegido pelo Android Keystore."
                    }
                },
                enabled = !busy && username.isNotBlank() && password.isNotBlank(),
                modifier = Modifier.padding(top = 12.dp)
            ) { Text(if (busy) "Conectando…" else "Entrar no Jarvis") }
        } else {
            Text("Sessão autenticada neste dispositivo.", modifier = Modifier.padding(top = 12.dp))
            Button(
                onClick = {
                    if (Build.VERSION.SDK_INT >= 33 &&
                        ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) !=
                        PackageManager.PERMISSION_GRANTED
                    ) {
                        notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
                    } else {
                        onStartPresence()
                        presenceActive = true
                        message = "Presença ativada; verifique a notificação persistente."
                    }
                },
                enabled = !presenceActive,
                modifier = Modifier.padding(top = 12.dp)
            ) { Text("Ativar presença em segundo plano") }
            Button(
                onClick = { onStopPresence(); presenceActive = false; message = "Presença interrompida." },
                enabled = presenceActive,
                modifier = Modifier.padding(top = 8.dp)
            ) { Text("Parar presença") }
            Button(
                onClick = { onStopPresence(); onLogout(); presenceActive = false; loggedIn = false; message = "Sessão encerrada." },
                modifier = Modifier.padding(top = 8.dp)
            ) { Text("Sair") }
        }
        Text(message, modifier = Modifier.padding(top = 16.dp), style = MaterialTheme.typography.bodySmall)
    }
}
