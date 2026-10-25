package com.thedrack.jarvismobile

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer

/**
 * Reconhecimento de voz sob demanda: um turno por toque, em pt-BR.
 * Não escuta em segundo plano e não mantém o microfone ligado por padrão.
 * Exige permissão RECORD_AUDIO concedida antes de chamar listen().
 */
class VoiceInput(context: Context) {
    private val appContext = context.applicationContext
    private val recognizer: SpeechRecognizer? =
        if (SpeechRecognizer.isRecognitionAvailable(appContext)) {
            SpeechRecognizer.createSpeechRecognizer(appContext)
        } else {
            null
        }
    private val main = Handler(Looper.getMainLooper())

    val available: Boolean get() = recognizer != null

    fun listen(
        onPartialText: (String) -> Unit,
        onFinalText: (String) -> Unit,
        onFailure: (String) -> Unit
    ) {
        val rec = recognizer
        if (rec == null) {
            onFailure("Reconhecimento de voz indisponível neste aparelho.")
            return
        }
        rec.cancel()
        rec.setRecognitionListener(object : RecognitionListener {
            override fun onReadyForSpeech(params: Bundle?) {}
            override fun onBeginningOfSpeech() {}
            override fun onRmsChanged(rmsdB: Float) {}
            override fun onBufferReceived(buffer: ByteArray?) {}
            override fun onEndOfSpeech() {}
            override fun onEvent(eventType: Int, params: Bundle?) {}

            override fun onPartialResults(partialResults: Bundle?) {
                val text = partialResults?.firstText() ?: return
                main.post { onPartialText(text) }
            }

            override fun onResults(results: Bundle?) {
                val text = results?.firstText().orEmpty()
                main.post {
                    if (text.isBlank()) onFailure("Não entendi. Tente de novo.") else onFinalText(text)
                }
            }

            override fun onError(error: Int) {
                main.post { onFailure(describe(error)) }
            }
        })
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
            .putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            .putExtra(RecognizerIntent.EXTRA_LANGUAGE, "pt-BR")
            .putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            .putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
        rec.startListening(intent)
    }

    fun stop() {
        recognizer?.stopListening()
    }

    fun release() {
        recognizer?.destroy()
    }

    private fun Bundle.firstText(): String? =
        getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()?.takeIf { it.isNotBlank() }

    private fun describe(error: Int): String = when (error) {
        SpeechRecognizer.ERROR_NO_MATCH, SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> "Não entendi. Tente de novo."
        SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> "Permissão de microfone necessária."
        SpeechRecognizer.ERROR_NETWORK, SpeechRecognizer.ERROR_NETWORK_TIMEOUT ->
            "Reconhecimento de voz sem rede."
        SpeechRecognizer.ERROR_RECOGNIZER_BUSY -> "Reconhecedor ocupado. Tente novamente."
        else -> "Falha no reconhecimento de voz (código $error)."
    }
}
