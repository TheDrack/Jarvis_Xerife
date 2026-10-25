package com.thedrack.jarvismobile

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

/** Mensagem da conversa. Fica só em memória: não é persistida no aparelho. */
data class ChatMessage(val id: Long, val fromUser: Boolean, val text: String, val isError: Boolean = false)

/** Tela de conversa: histórico, campo de texto, microfone sob demanda e envio. */
@Composable
fun ChatPanel(
    modifier: Modifier,
    messages: List<ChatMessage>,
    draft: String,
    busy: Boolean,
    listening: Boolean,
    voiceAvailable: Boolean,
    statusLine: String,
    notice: String?,
    onDraftChange: (String) -> Unit,
    onSend: () -> Unit,
    onMic: () -> Unit
) {
    val listState = rememberLazyListState()
    LaunchedEffect(messages.size) {
        if (messages.isNotEmpty()) listState.animateScrollToItem(messages.size - 1)
    }

    Column(modifier = modifier) {
        Text(statusLine, style = MaterialTheme.typography.bodySmall)
        Text(
            "Toque em Falar para ditar; o microfone não fica ligado em segundo plano.",
            style = MaterialTheme.typography.bodySmall,
            modifier = Modifier.padding(top = 2.dp)
        )
        notice?.let {
            Text(it, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(top = 4.dp))
        }
        LazyColumn(
            state = listState,
            modifier = Modifier.fillMaxWidth().weight(1f).padding(vertical = 8.dp)
        ) {
            items(messages, key = { it.id }) { message -> MessageBubble(message) }
        }
        OutlinedTextField(
            value = draft,
            onValueChange = onDraftChange,
            modifier = Modifier.fillMaxWidth(),
            placeholder = { Text("Escreva ou fale com o Jarvis") },
            maxLines = 4,
            enabled = !busy
        )
        Row(
            modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            TextButton(onClick = onMic, enabled = voiceAvailable && !busy) {
                Text(if (listening) "Parar" else "Falar")
            }
            Button(onClick = onSend, enabled = draft.isNotBlank() && !busy) {
                Text(if (busy) "Aguarde…" else "Enviar")
            }
        }
    }
}

@Composable
private fun MessageBubble(message: ChatMessage) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
        horizontalArrangement = if (message.fromUser) Arrangement.End else Arrangement.Start
    ) {
        Surface(
            color = when {
                message.isError -> MaterialTheme.colorScheme.errorContainer
                message.fromUser -> MaterialTheme.colorScheme.primaryContainer
                else -> MaterialTheme.colorScheme.surfaceVariant
            },
            shape = MaterialTheme.shapes.medium
        ) {
            Text(message.text, modifier = Modifier.padding(12.dp))
        }
    }
}
