package com.thedrack.jarvismobile

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.unit.dp

class AccessibilityPairingActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val token = AccessibilityBridgeCredentials.getOrCreate(this)
        setContent {
            val clipboard = LocalClipboardManager.current
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    Column(
                        modifier = Modifier.fillMaxWidth().padding(24.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        Text("Jarvis — pareamento de acessibilidade", style = MaterialTheme.typography.titleLarge)
                        Text("O segredo abaixo autentica apenas conexões locais do Termux para este aparelho. Não o envie para serviços externos.")
                        Text(token, style = MaterialTheme.typography.bodyMedium)
                        Button(onClick = { clipboard.setText(AnnotatedString(token)) }) {
                            Text("Copiar segredo local")
                        }
                        Button(onClick = { startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)) }) {
                            Text("Abrir configurações de Acessibilidade")
                        }
                        Text("Ative manualmente “Jarvis Accessibility”. O serviço só ficará disponível enquanto o Android mantiver essa permissão ativa.")
                    }
                }
            }
        }
    }
}
