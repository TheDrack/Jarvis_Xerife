package com.thedrack.jarvismobile

import android.os.Bundle
import android.speech.tts.TextToSpeech
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
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
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
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
        speech = TextToSpeech(this) { status ->
            speechReady.value = status == TextToSpeech.SUCCESS
            if (status == TextToSpeech.SUCCESS) speech?.language = Locale("pt", "BR")
        }
        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    JarvisMobileScreen(
                        initialBaseUrl = BuildConfig.DEFAULT_API_BASE_URL,
                        isLoggedInInitially = vault.read() != null,
                        speechReady = speechReady.value,
                        onLogin = ::login,
                        onLogout = { vault.clear() },
                        onSpeak = { speak("Jarvis Mobile ativo. Canal de voz local funcionando.") }
                    )
                }
            }
        }
    }

    private fun login(baseUrl: String, username: String, password: String, result: (String?) -> Unit) {
        executor.execute {
            var connection: HttpURLConnection? = null
            val outcome = try {
                val normalized = baseUrl.trim().trimEnd('/')
                require(normalized.startsWith("https://")) { "Use uma URL HTTPS." }
                connection = (URL(normalized + "/token").openConnection() as HttpURLConnection).apply {
                    requestMethod = "POST"
                    connectTimeout = 10000
                    readTimeout = 10000
                    doOutput = true
                    setRequestProperty("Content-Type", "application/x-www-form-urlencoded")
                }
                val body = "username=" + URLEncoder.encode(username, "UTF-8") +
                    "&password=" + URLEncoder.encode(password, "UTF-8")
                connection.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
                val code = connection.responseCode
                val stream = if (code in 200..299) connection.inputStream else connection.errorStream
                val response = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
                if (code !in 200..299) {
                    "Login recusado pelo servidor (HTTP " + code + ")."
                } else {
                    val token = JSONObject(response).optString("access_token")
                    if (token.isBlank()) "Resposta de login sem token válido."
                    else {
                        vault.save(token)
                        null
                    }
                }
            } catch (error: Exception) {
                "Falha de conexão/login: " + (error.message ?: error.javaClass.simpleName)
            } finally {
                connection?.disconnect()
            }
            runOnUiThread { result(outcome) }
        }
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
    onLogin: (String, String, String, (String?) -> Unit) -> Unit,
    onLogout: () -> Unit,
    onSpeak: () -> Unit
) {
    var baseUrl by remember { mutableStateOf(initialBaseUrl) }
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var loggedIn by remember { mutableStateOf(isLoggedInInitially) }
    var busy by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("Sessão local; integração de eventos ainda não ativada.") }

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
                onClick = { onLogout(); loggedIn = false; message = "Sessão encerrada." },
                modifier = Modifier.padding(top = 8.dp)
            ) { Text("Sair") }
        }
        Text(message, modifier = Modifier.padding(top = 16.dp), style = MaterialTheme.typography.bodySmall)
    }
}
