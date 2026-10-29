package com.thedrack.jarvismobile

import android.content.Context
import org.json.JSONObject

/** Resposta de /v1/message já interpretada para a interface. */
data class ChatReply(val success: Boolean, val text: String, val error: String?)

/** Resposta de /v1/status usada pelo cabeçalho do chat. */
data class JarvisStatus(
    val appName: String,
    val version: String,
    val isActive: Boolean,
    val wakeWord: String,
    val language: String
)

/** Cliente de conversa e status. Usa a mesma sessão renovável do restante do app. */
object JarvisApi {
    /** Limite de envio no cliente; o servidor também valida o texto. */
    const val MAX_MESSAGE_CHARS = 2000

    /**
     * Envia texto ao núcleo Jarvis (POST /v1/message).
     * Lança IllegalArgumentException para texto vazio ou longo demais.
     */
    fun sendMessage(context: Context, text: String): ChatReply {
        val trimmed = text.trim()
        require(trimmed.isNotEmpty()) { "Digite uma mensagem." }
        require(trimmed.length <= MAX_MESSAGE_CHARS) { "Mensagem longa demais (máximo $MAX_MESSAGE_CHARS caracteres)." }
        val body = JSONObject().put("text", trimmed).toString()
        val result = MobileApiClient.authenticatedRequest(context, "/v1/message", "POST", body)
            ?: return ChatReply(false, "", "Sem conexão com o Jarvis.")
        return JarvisParsing.parseChatReply(result.code, result.body)
    }

    /** Lê o status público (GET /v1/status). Retorna null se o servidor não responder. */
    fun fetchStatus(context: Context): JarvisStatus? {
        val result = MobileApiClient.publicGet(context, "/v1/status") ?: return null
        return JarvisParsing.parseStatus(result.code, result.body)
    }
}

/** Interpretação pura das respostas, sem tipos Android, para testes unitários na JVM. */
object JarvisParsing {
    fun parseChatReply(code: Int, body: String): ChatReply {
        if (code == 401) return ChatReply(false, "", "Sessão expirada. Entre novamente.")
        if (code == 429) return ChatReply(false, "", "Muitas mensagens em pouco tempo. Aguarde um instante.")
        if (code !in 200..299) return ChatReply(false, "", "Erro do servidor (HTTP $code).")
        return try {
            val json = JSONObject(body)
            val success = json.optBoolean("success", false)
            val response = json.text("response")
            val error = json.text("error").takeIf { it.isNotBlank() }
            when {
                response.isNotBlank() -> ChatReply(success, response, if (success) null else error)
                else -> ChatReply(false, "", error ?: "Resposta vazia do Jarvis.")
            }
        } catch (_: Exception) {
            ChatReply(false, "", "Resposta inválida do servidor.")
        }
    }

    fun parseStatus(code: Int, body: String): JarvisStatus? {
        if (code !in 200..299) return null
        return try {
            val json = JSONObject(body)
            JarvisStatus(
                appName = json.text("app_name"),
                version = json.text("version"),
                isActive = json.optBoolean("is_active", false),
                wakeWord = json.text("wake_word"),
                language = json.text("language")
            )
        } catch (_: Exception) {
            null
        }
    }

    /** Campo textual; JSON null vira string vazia (optString devolveria "null"). */
    private fun JSONObject.text(name: String): String = if (isNull(name)) "" else optString(name, "")
}
