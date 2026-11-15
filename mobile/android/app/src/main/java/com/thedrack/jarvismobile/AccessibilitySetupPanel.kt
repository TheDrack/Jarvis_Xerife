package com.thedrack.jarvismobile

import android.content.ComponentName
import android.content.Context
import android.provider.Settings
import android.text.TextUtils
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

@Composable
fun AccessibilitySetupPanel(context: Context) {
    val component = ComponentName(context, JarvisAccessibilityService::class.java)
    val enabledServices = Settings.Secure.getString(
        context.contentResolver, Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES
    ).orEmpty()
    val enabled = TextUtils.SimpleStringSplitter(':').run {
        setString(enabledServices)
        any { it.equals(component.flattenToString(), ignoreCase = true) }
    }
    Column(
        modifier = Modifier.fillMaxWidth().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        Text("Automação Android nativa", style = MaterialTheme.typography.titleLarge)
        Text(if (enabled) "Serviço de acessibilidade ativo." else "Serviço de acessibilidade desativado.")
        Text("A ativação concede ao Jarvis acesso à árvore da interface e capacidade de executar gestos. Ative somente se desejar habilitar automação remota.")
        Button(onClick = {
            context.startActivity(android.content.Intent(context, AccessibilityPairingActivity::class.java))
        }) { Text("Parear Termux e configurar acesso") }
        Button(onClick = {
            context.startActivity(android.content.Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
        }) { Text("Configurações de Acessibilidade") }
        Text("Endpoint local: 127.0.0.1:${JarvisAccessibilityService.PORT}. O segredo de pareamento é gerado no aparelho e precisa ser configurado no Termux.", style = MaterialTheme.typography.bodySmall)
    }
}
