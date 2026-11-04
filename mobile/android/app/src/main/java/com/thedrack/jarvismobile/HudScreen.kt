package com.thedrack.jarvismobile

import android.Manifest
import android.annotation.SuppressLint
import android.content.pm.PackageManager
import android.graphics.Color
import android.webkit.GeolocationPermissions
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat

/**
 * Endereço do HUD servido pelo núcleo local.
 *
 * O núcleo Jarvis Desktop serve a mesma página do HUD (`/`) em HTTP simples na
 * porta 8777, na rede local ou no Tailscale. [normalize] aceita o endereço com
 * ou sem esquema, descarta caminho/consulta e devolve apenas origem + porta.
 */
object HudTarget {
    fun normalize(raw: String): String? {
        val trimmed = raw.trim()
        if (trimmed.isEmpty()) return null
        val withScheme = when {
            trimmed.startsWith("https://", ignoreCase = true) -> trimmed
            trimmed.startsWith("http://", ignoreCase = true) -> trimmed
            else -> "http://$trimmed"
        }
        val url = try {
            java.net.URI(withScheme).toURL()
        } catch (error: Exception) {
            return null
        }
        val host = url.host ?: return null
        if (host.isBlank()) return null
        val protocol = url.protocol.lowercase()
        if (protocol != "http" && protocol != "https") return null
        val port = if (url.port > 0) ":${url.port}" else ""
        return "$protocol://$host$port"
    }
}

/**
 * Página HUD do Jarvis dentro do aplicativo.
 *
 * A página é a mesma servida ao app desktop (`app/static/jarvis-desktop.html`),
 * portanto briefing, globo, câmeras e Universal Intelligence aparecem sem uma
 * segunda implementação. Nada é injetado: o pareamento acontece no próprio HUD
 * com o código de seis dígitos exibido no Jarvis Desktop, e o token fica no
 * `sessionStorage` do WebView.
 */
@SuppressLint("SetJavaScriptEnabled")
@Composable
fun JarvisHudScreen(
    initialUrl: String,
    onUrlChange: (String) -> Unit,
    onClose: () -> Unit
) {
    var draft by remember { mutableStateOf(initialUrl) }
    var target by remember { mutableStateOf(HudTarget.normalize(initialUrl)) }
    var error by remember { mutableStateOf<String?>(null) }
    var webView by remember { mutableStateOf<WebView?>(null) }
    val context = LocalContext.current
    val locationPermission = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { }

    // O HUD pede a localização do aparelho para ancorar clima e manchetes regionais.
    LaunchedEffect(Unit) {
        val fine = ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED
        val coarse = ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_COARSE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED
        if (!fine && !coarse) {
            locationPermission.launch(
                arrayOf(
                    Manifest.permission.ACCESS_COARSE_LOCATION,
                    Manifest.permission.ACCESS_FINE_LOCATION
                )
            )
        }
    }

    BackHandler {
        val view = webView
        if (view != null && view.canGoBack()) view.goBack() else onClose()
    }

    Column(modifier = Modifier.fillMaxSize()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            OutlinedTextField(
                draft,
                { draft = it },
                label = { Text("HUD do núcleo") },
                singleLine = true,
                modifier = Modifier.weight(1f)
            )
            Button(
                onClick = {
                    val normalized = HudTarget.normalize(draft)
                    if (normalized == null) {
                        error = "Endereço inválido. Use http://IP:8777."
                    } else {
                        error = null
                        target = normalized
                        onUrlChange(normalized)
                    }
                },
                modifier = Modifier.padding(start = 8.dp)
            ) { Text("Abrir") }
            Button(onClick = onClose, modifier = Modifier.padding(start = 8.dp)) { Text("Voltar") }
        }
        error?.let {
            Text(it, modifier = Modifier.padding(horizontal = 12.dp), style = MaterialTheme.typography.bodySmall)
        }
        val url = target
        if (url == null) {
            Text(
                "Informe o endereço do Jarvis Desktop nesta rede (LAN ou Tailscale), por exemplo http://192.168.0.15:8777, " +
                    "e pareie este telefone com o código de seis dígitos exibido no rodapé do HUD.",
                modifier = Modifier.padding(12.dp),
                style = MaterialTheme.typography.bodySmall
            )
        } else {
            AndroidView(
                modifier = Modifier.fillMaxSize(),
                factory = { context ->
                    WebView(context).apply {
                        setBackgroundColor(Color.parseColor("#01060c"))
                        settings.javaScriptEnabled = true
                        settings.domStorageEnabled = true
                        settings.geolocationEnabled = true
                        settings.mediaPlaybackRequiresUserGesture = true
                        webViewClient = WebViewClient()
                        // Só o próprio HUD recebe permissão de geolocalização.
                        webChromeClient = object : WebChromeClient() {
                            override fun onGeolocationPermissionsShowPrompt(
                                origin: String?,
                                callback: GeolocationPermissions.Callback?
                            ) {
                                val trusted = !origin.isNullOrBlank() && origin.startsWith(url)
                                callback?.invoke(origin, trusted, false)
                            }
                        }
                        loadUrl(url)
                        webView = this
                    }
                }
            )
        }
    }
}
