package com.thedrack.jarvismobile

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.os.Build
import android.speech.tts.TextToSpeech
import androidx.activity.ComponentActivity
import androidx.activity.result.ActivityResultLauncher
import androidx.activity.compose.setContent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
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
import com.google.android.gms.auth.api.signin.GoogleSignIn
import com.google.android.gms.auth.api.signin.GoogleSignInOptions
import com.google.android.gms.common.api.ApiException
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
    private lateinit var voice: VoiceInput
    private lateinit var googleSignInLauncher: ActivityResultLauncher<Intent>
    private var pendingGoogleResult: ((String?) -> Unit)? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        vault = TokenVault(this)
        voice = VoiceInput(this)
        googleSignInLauncher = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            val callback = pendingGoogleResult
            pendingGoogleResult = null
            if (result.resultCode != RESULT_OK) {
                callback?.invoke("Login Google cancelado.")
            } else {
                try {
                    val task = GoogleSignIn.getSignedInAccountFromIntent(result.data)
                    val idToken = task.getResult(ApiException::class.java).idToken
                    if (idToken.isNullOrBlank()) callback?.invoke("O Google não retornou ID token. Confira o OAuth Web Client ID.")
                    else exchangeGoogleToken(idToken, callback)
                } catch (error: Exception) {
                    callback?.invoke("Falha no login Google: " + (error.message ?: error.javaClass.simpleName))
                }
            }
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
                        voice = voice,
                        onLogin = ::login,
                        onGoogleSignIn = ::startGoogleSignIn,
                        onLogout = ::logout,
                        onStartPresence = ::startPresence,
                        onStopPresence = ::stopPresence,
                        onLocationSharingChanged = ::setLocationSharing,
                        onSpeak = { speak("Jarvis Mobile ativo. Canal de voz local funcionando.") },
                        onSendChat = ::sendChat,
                        onFetchStatus = ::fetchStatus,
                        onSpeakReply = ::speak
                    )
                }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        if (!this::vault.isInitialized) return
        val prefs = getSharedPreferences("jarvis_session", MODE_PRIVATE)
        if (prefs.getBoolean("location_sharing_enabled", false)) {
            if (hasLocationPermission() && hasBackgroundLocationPermission()) {
                setLocationSharing(true)
            } else {
                prefs.edit().putBoolean("location_sharing_enabled", false).apply()
                stopService(Intent(this, LocationTrackingService::class.java))
            }
        }
    }

    private fun hasLocationPermission(): Boolean =
        ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED ||
            ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED

    private fun hasBackgroundLocationPermission(): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.Q ||
            ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_BACKGROUND_LOCATION) == PackageManager.PERMISSION_GRANTED

    private fun setLocationSharing(enabled: Boolean) {
        val prefs = getSharedPreferences("jarvis_session", MODE_PRIVATE)
        val allowed = LocationSharingPolicy.isAuthorized(
            userOptIn = enabled,
            foregroundPermissionGranted = hasLocationPermission(),
            backgroundPermissionGranted = hasBackgroundLocationPermission(),
            authenticated = !vault.readRefreshToken().isNullOrBlank()
        )
        prefs.edit().putBoolean("location_sharing_enabled", allowed).apply()
        val serviceIntent = Intent(this, LocationTrackingService::class.java)
        if (!allowed) {
            stopService(serviceIntent)
            return
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) startForegroundService(serviceIntent)
        else startService(serviceIntent)
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
                        EnvironmentObservationPublisher.publish(applicationContext, getOrCreateDeviceId(), BridgeService.isRunning)
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
            }
        }
    }

    private fun startGoogleSignIn(result: (String?) -> Unit) {
        val clientId = BuildConfig.GOOGLE_WEB_CLIENT_ID
        if (clientId.isBlank()) {
            result("Login Google ainda não configurado: defina GOOGLE_WEB_CLIENT_ID no build Android.")
            return
        }
        val options = GoogleSignInOptions.Builder(GoogleSignInOptions.DEFAULT_SIGN_IN)
            .requestEmail()
            .requestIdToken(clientId)
            .build()
        pendingGoogleResult = result
        googleSignInLauncher.launch(GoogleSignIn.getClient(this, options).signInIntent)
    }

    private fun exchangeGoogleToken(idToken: String, result: ((String?) -> Unit)?) {
        val prefs = getSharedPreferences("jarvis_session", MODE_PRIVATE)
        val baseUrl = prefs.getString("api_base_url", BuildConfig.DEFAULT_API_BASE_URL)
            ?: BuildConfig.DEFAULT_API_BASE_URL
        executor.execute {
            var connection: HttpURLConnection? = null
            val outcome = try {
                val normalized = baseUrl.trim().trimEnd('/')
                require(normalized.startsWith("https://")) { "Use uma URL HTTPS." }
                connection = (URL(normalized + "/v1/mobile/session/google").openConnection() as HttpURLConnection).apply {
                    requestMethod = "POST"
                    connectTimeout = 10000
                    readTimeout = 10000
                    doOutput = true
                    setRequestProperty("Content-Type", "application/json")
                }
                val body = JSONObject()
                    .put("id_token", idToken)
                    .put("device_id", getOrCreateDeviceId())
                    .toString()
                connection.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
                val code = connection.responseCode
                val stream = if (code in 200..299) connection.inputStream else connection.errorStream
                val response = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
                if (code !in 200..299) {
                    val detail = try { JSONObject(response).optString("detail") } catch (_: Exception) { "" }
                    when (code) {
                        401 -> "Token Google inválido ou expirado."
                        403 -> detail.ifBlank { "Esta conta Google ainda não está vinculada a uma conta Jarvis existente." }
                        404 -> "A API publicada ainda não contém o login Google (HTTP 404)."
                        503 -> detail.ifBlank { "Login Google não configurado no servidor (HTTP 503)." }
                        else -> detail.ifBlank { "Login Google recusado pelo servidor (HTTP $code)." }
                    }
                } else {
                    val payload = JSONObject(response)
                    val token = payload.optString("access_token")
                    val refreshToken = payload.optString("refresh_token")
                    if (token.isBlank() || refreshToken.isBlank()) "Resposta de sessão móvel incompleta."
                    else {
                        vault.save(token, refreshToken)
                        prefs.edit().putString("api_base_url", normalized).apply()
                        null
                    }
                }
            } catch (error: Exception) {
                "Falha de conexão/login Google: " + (error.message ?: error.javaClass.simpleName)
            } finally {
                connection?.disconnect()
            }
            runOnUiThread {
                result?.invoke(outcome)
            }
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
    }

    private fun speak(text: String) {
        speech?.speak(text, TextToSpeech.QUEUE_FLUSH, null, "jarvis-mobile-local-tts")
    }

    /** Envia texto ao núcleo em segundo plano e devolve a resposta na thread de UI. */
    private fun sendChat(text: String, onReply: (ChatReply) -> Unit) {
        executor.execute {
            val reply = try {
                JarvisApi.sendMessage(applicationContext, text)
            } catch (error: IllegalArgumentException) {
                ChatReply(false, "", error.message)
            }
            runOnUiThread { onReply(reply) }
        }
    }

    private fun fetchStatus(onStatus: (JarvisStatus?) -> Unit) {
        executor.execute {
            val status = JarvisApi.fetchStatus(applicationContext)
            runOnUiThread { onStatus(status) }
        }
    }

    override fun onDestroy() {
        speech?.stop()
        speech?.shutdown()
        voice.release()
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
    voice: VoiceInput,
    onLogin: (String, String, String, (String?) -> Unit) -> Unit,
    onGoogleSignIn: ((String?) -> Unit) -> Unit,
    onLogout: () -> Unit,
    onStartPresence: () -> Unit,
    onStopPresence: () -> Unit,
    onLocationSharingChanged: (Boolean) -> Unit,
    onSpeak: () -> Unit,
    onSendChat: (String, (ChatReply) -> Unit) -> Unit,
    onFetchStatus: ((JarvisStatus?) -> Unit) -> Unit,
    onSpeakReply: (String) -> Unit
) {
    var baseUrl by remember { mutableStateOf(initialBaseUrl) }
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var loggedIn by remember { mutableStateOf(isLoggedInInitially) }
    var presenceActive by remember { mutableStateOf(presenceInitiallyActive) }
    var busy by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("Entre e ative a presença para receber eventos do Jarvis.") }
    var tab by remember { mutableStateOf(0) } // 0 = Presença, 1 = Conversa
    var messages by remember { mutableStateOf(listOf<ChatMessage>()) }
    var nextId by remember { mutableStateOf(1L) }
    var draft by remember { mutableStateOf("") }
    var chatBusy by remember { mutableStateOf(false) }
    var listening by remember { mutableStateOf(false) }
    var chatNotice by remember { mutableStateOf<String?>(null) }
    var status by remember { mutableStateOf<JarvisStatus?>(null) }
    val context = LocalContext.current
    var locationSharingEnabled by remember {
        mutableStateOf(context.getSharedPreferences("jarvis_session", Context.MODE_PRIVATE).getBoolean("location_sharing_enabled", false))
    }

    fun newId(): Long {
        val id = nextId
        nextId = id + 1
        return id
    }

    LaunchedEffect(loggedIn) {
        if (loggedIn) onFetchStatus { status = it }
    }

    val startListening: () -> Unit = {
        listening = true
        chatNotice = null
        voice.listen(
            onPartialText = { draft = it },
            onFinalText = { draft = it; listening = false },
            onFailure = { listening = false; chatNotice = it }
        )
    }
    val micPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) startListening() else chatNotice = "Sem permissão de microfone; use o teclado."
    }
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

    val backgroundLocationPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        val prefs = context.getSharedPreferences("jarvis_session", Context.MODE_PRIVATE)
        if (granted && (
                ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED ||
                    ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED
            )
        ) {
            locationSharingEnabled = true
            prefs.edit().putBoolean("location_sharing_enabled", true).apply()
            onLocationSharingChanged(true)
            message = "Compartilhamento contínuo ativado. A notificação do Android indica quando a localização está ativa."
        } else {
            locationSharingEnabled = false
            prefs.edit().putBoolean("location_sharing_enabled", false).apply()
            onLocationSharingChanged(false)
            message = "Para continuar em segundo plano, permita localização 'o tempo todo' nas configurações do Android."
        }
    }

    val locationPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { grants ->
        val granted = grants[Manifest.permission.ACCESS_FINE_LOCATION] == true || grants[Manifest.permission.ACCESS_COARSE_LOCATION] == true
        if (!granted) {
            locationSharingEnabled = false
            context.getSharedPreferences("jarvis_session", Context.MODE_PRIVATE).edit().putBoolean("location_sharing_enabled", false).apply()
            onLocationSharingChanged(false)
            message = "Permissão de localização negada; nenhum dado será enviado."
        } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_BACKGROUND_LOCATION) != PackageManager.PERMISSION_GRANTED
        ) {
            message = "Para localização em segundo plano, conceda agora a permissão 'o tempo todo' do Android."
            backgroundLocationPermissionLauncher.launch(Manifest.permission.ACCESS_BACKGROUND_LOCATION)
        } else {
            locationSharingEnabled = true
            context.getSharedPreferences("jarvis_session", Context.MODE_PRIVATE).edit().putBoolean("location_sharing_enabled", true).apply()
            onLocationSharingChanged(true)
            message = "Compartilhamento contínuo ativado. A notificação do Android indica quando a localização está ativa."
        }
    }

    fun onMicPressed() {
        if (listening) {
            voice.stop()
            listening = false
        } else if (ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) ==
            PackageManager.PERMISSION_GRANTED
        ) {
            startListening()
        } else {
            micPermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
        }
    }

    fun sendDraft() {
        val text = draft.trim()
        if (text.isEmpty() || chatBusy) return
        messages = messages + ChatMessage(newId(), fromUser = true, text = text)
        draft = ""
        chatBusy = true
        chatNotice = null
        onSendChat(text) { reply ->
            chatBusy = false
            if (reply.success) {
                messages = messages + ChatMessage(newId(), fromUser = false, text = reply.text)
                onSpeakReply(reply.text)
            } else {
                messages = messages + ChatMessage(
                    newId(),
                    fromUser = false,
                    text = reply.error ?: "Falha ao falar com o Jarvis.",
                    isError = true
                )
            }
        }
    }

    val statusLine = when {
        status != null -> {
            val s = status!!
            "Jarvis ${s.appName} ${s.version} · " + if (s.isActive) "ativo" else "inativo"
        }
        loggedIn -> "Consultando o Jarvis…"
        else -> "Entre para conversar."
    }

    Column(modifier = Modifier.fillMaxSize().padding(24.dp)) {
        Text("J.A.R.V.I.S.", style = MaterialTheme.typography.headlineLarge)
        Text("Companheiro Android", modifier = Modifier.padding(top = 4.dp))
        if (loggedIn) {
            Row(modifier = Modifier.padding(top = 12.dp)) {
                Button(onClick = { tab = 0 }, enabled = tab != 0) { Text("Presença") }
                Button(onClick = { tab = 1 }, enabled = tab != 1, modifier = Modifier.padding(start = 8.dp)) {
                    Text("Conversa")
                }
            }
        }
        if (loggedIn && tab == 1) {
            ChatPanel(
                modifier = Modifier.fillMaxWidth().weight(1f).padding(top = 12.dp),
                messages = messages,
                draft = draft,
                busy = chatBusy,
                listening = listening,
                voiceAvailable = voice.available,
                statusLine = statusLine,
                notice = chatNotice,
                onDraftChange = { draft = it },
                onSend = ::sendDraft,
                onMic = ::onMicPressed
            )
        } else {
            Column(
                modifier = Modifier.fillMaxWidth().weight(1f).verticalScroll(rememberScrollState()),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
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
                            message = "Abrindo login Google…"
                            onGoogleSignIn { error ->
                                busy = false
                                loggedIn = error == null
                                message = error ?: "Autenticado com Google. Token protegido pelo Android Keystore."
                            }
                        },
                        enabled = !busy && BuildConfig.GOOGLE_WEB_CLIENT_ID.isNotBlank(),
                        modifier = Modifier.padding(top = 12.dp)
                    ) { Text("Continuar com Google") }
                    if (BuildConfig.GOOGLE_WEB_CLIENT_ID.isBlank()) {
                        Text(
                            "Login Google aguardando configuração do OAuth Web Client ID no build.",
                            modifier = Modifier.padding(top = 6.dp),
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
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
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text("Compartilhar localização")
                            Text("Opcional. Com permissão 'o tempo todo', continua em segundo plano; uma notificação persistente indica a coleta.", style = MaterialTheme.typography.bodySmall)
                        }
                        Switch(
                            checked = locationSharingEnabled,
                            onCheckedChange = { enabled ->
                                if (!enabled) {
                                    locationSharingEnabled = false
                                    context.getSharedPreferences("jarvis_session", Context.MODE_PRIVATE).edit().putBoolean("location_sharing_enabled", false).apply()
                                    onLocationSharingChanged(false)
                                    message = "Compartilhamento de localização interrompido."
                                } else if (
                                    ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED ||
                                    ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED
                                ) {
                                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q &&
                                        ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_BACKGROUND_LOCATION) != PackageManager.PERMISSION_GRANTED
                                    ) {
                                        message = "Conceda localização 'o tempo todo' para permitir a coleta em segundo plano."
                                        backgroundLocationPermissionLauncher.launch(Manifest.permission.ACCESS_BACKGROUND_LOCATION)
                                    } else {
                                        locationSharingEnabled = true
                                        context.getSharedPreferences("jarvis_session", Context.MODE_PRIVATE).edit().putBoolean("location_sharing_enabled", true).apply()
                                        onLocationSharingChanged(true)
                                        message = "Compartilhamento contínuo ativado."
                                    }
                                } else {
                                    locationPermissionLauncher.launch(arrayOf(Manifest.permission.ACCESS_COARSE_LOCATION, Manifest.permission.ACCESS_FINE_LOCATION))
                                }
                            }
                        )
                    }
                    Button(
                        onClick = {
                            onStopPresence()
                            onLogout()
                            presenceActive = false
                            loggedIn = false
                            messages = emptyList()
                            draft = ""
                            status = null
                            tab = 0
                            message = "Sessão encerrada."
                        },
                        modifier = Modifier.padding(top = 8.dp)
                    ) { Text("Sair") }
                }
                Text(message, modifier = Modifier.padding(top = 16.dp), style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}
