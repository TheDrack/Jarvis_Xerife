package com.thedrack.jarvismobile

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.graphics.Path
import android.graphics.Rect
import android.graphics.Bitmap
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Display
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import android.util.Base64
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedInputStream
import java.io.BufferedOutputStream
import java.net.InetAddress
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.CountDownLatch
import java.util.concurrent.RejectedExecutionException
import java.util.concurrent.ThreadPoolExecutor
import java.util.concurrent.TimeUnit

/**
 * Explicitly user-enabled Android UI automation endpoint.
 *
 * The HTTP listener is bound to IPv4 loopback only. Termux reaches it from the
 * same device; every request requires the per-installation pairing bearer token.
 */
class JarvisAccessibilityService : AccessibilityService() {
    @Volatile private var server: ServerSocket? = null
    @Volatile private var listenerThread: Thread? = null
    private val mainHandler = Handler(Looper.getMainLooper())
    private val clientExecutor = ThreadPoolExecutor(
        2, 4, 30, TimeUnit.SECONDS, ArrayBlockingQueue(8)
    ) { runnable -> Thread(runnable, "jarvis-accessibility-client").apply { isDaemon = true } }

    override fun onServiceConnected() {
        super.onServiceConnected()
        isEnabled = true
        startLoopbackServer()
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) = Unit
    override fun onInterrupt() = Unit

    private fun startLoopbackServer() {
        if (server?.isClosed == false) return
        listenerThread = Thread({
            try {
                val socketServer = ServerSocket(PORT, 8, InetAddress.getByName("127.0.0.1"))
                server = socketServer
                while (!socketServer.isClosed) {
                    val client = try { socketServer.accept() } catch (_: Exception) { break }
                    try {
                        clientExecutor.execute { handleClient(client) }
                    } catch (_: RejectedExecutionException) {
                        client.close()
                    }
                }
            } catch (error: Exception) {
                android.util.Log.e(TAG, "Local accessibility listener failed: " + error.javaClass.simpleName)
            }
        }, "jarvis-accessibility-http").apply { isDaemon = true; start() }
    }

    private fun handleClient(socket: Socket) {
        socket.use { client ->
            client.soTimeout = 5000
            val input = BufferedInputStream(client.getInputStream())
            val output = BufferedOutputStream(client.getOutputStream())
            try {
                val requestLine = readLine(input, 4096) ?: return
                val parts = requestLine.split(" ")
                if (parts.size != 3 || parts[2] != "HTTP/1.1") {
                    writeResponse(output, 400, JSONObject().put("error", "bad_request"))
                    return
                }
                val headers = mutableMapOf<String, String>()
                while (true) {
                    val line = readLine(input, 8192) ?: return
                    if (line.isEmpty()) break
                    val separator = line.indexOf(':')
                    if (separator > 0) headers[line.substring(0, separator).trim().lowercase()] =
                        line.substring(separator + 1).trim()
                }
                if (!AccessibilityBridgeCredentials.isAuthorized(this, headers["authorization"])) {
                    writeResponse(output, 401, JSONObject().put("error", "unauthorized"))
                    return
                }
                val length = headers["content-length"]?.toIntOrNull() ?: 0
                if (length !in 0..MAX_BODY_BYTES) {
                    writeResponse(output, 413, JSONObject().put("error", "body_too_large"))
                    return
                }
                val body = ByteArray(length)
                var offset = 0
                while (offset < length) {
                    val count = input.read(body, offset, length - offset)
                    if (count < 0) throw IllegalArgumentException("incomplete_body")
                    offset += count
                }
                val result = route(parts[0], parts[1], if (length > 0) JSONObject(String(body, Charsets.UTF_8)) else JSONObject())
                writeResponse(output, 200, result)
            } catch (error: IllegalArgumentException) {
                writeResponse(output, 400, JSONObject().put("error", "invalid_request"))
            } catch (error: Exception) {
                writeResponse(output, 500, JSONObject().put("error", "internal_error"))
            }
        }
    }

    private fun route(method: String, path: String, body: JSONObject): JSONObject {
        if (method == "GET" && path == "/healthz") {
            return JSONObject().put("status", "ready").put("service", "jarvis-accessibility")
                .put("android_api", Build.VERSION.SDK_INT).put("screenshot_supported", Build.VERSION.SDK_INT >= 30)
        }
        if (method == "GET" && path == "/v1/snapshot") return onMain { snapshot() }
        if (method == "GET" && path == "/v1/screenshot") return screenshot()
        if (method == "POST" && path == "/v1/action") return onMain { performAction(body) }
        return JSONObject().put("error", "not_found")
    }

    private fun <T> onMain(block: () -> T): T {
        if (Looper.myLooper() == Looper.getMainLooper()) return block()
        var value: T? = null
        var failure: Throwable? = null
        val latch = CountDownLatch(1)
        mainHandler.post {
            try { value = block() } catch (error: Throwable) { failure = error } finally { latch.countDown() }
        }
        if (!latch.await(5, TimeUnit.SECONDS)) throw IllegalStateException("main_thread_timeout")
        failure?.let { throw it }
        @Suppress("UNCHECKED_CAST")
        return value as T
    }

    private fun snapshot(): JSONObject {
        val root = rootInActiveWindow
            ?: return JSONObject().put("available", false).put("reason", "no_active_window")
        try {
            val nodes = JSONArray()
            val count = intArrayOf(0)
            appendNode(root, nodes, 0, count)
            return JSONObject().put("available", true).put("window_package", root.packageName?.toString().orEmpty())
                .put("node_count", count[0]).put("truncated", count[0] >= MAX_NODES).put("nodes", nodes)
        } finally {
            root.recycle()
        }
    }

    private fun appendNode(node: AccessibilityNodeInfo, output: JSONArray, depth: Int, count: IntArray) {
        if (depth > MAX_DEPTH || count[0] >= MAX_NODES) return
        val bounds = Rect()
        node.getBoundsInScreen(bounds)
        output.put(JSONObject()
            .put("index", count[0]++)
            .put("text", if (node.isPassword) "" else node.text?.toString()?.take(500).orEmpty())
            .put("content_description", if (node.isPassword) "" else node.contentDescription?.toString()?.take(500).orEmpty())
            .put("password", node.isPassword)
            .put("view_id", node.viewIdResourceName?.take(300).orEmpty())
            .put("class_name", node.className?.toString()?.take(200).orEmpty())
            .put("bounds", JSONObject().put("left", bounds.left).put("top", bounds.top)
                .put("right", bounds.right).put("bottom", bounds.bottom))
            .put("clickable", node.isClickable).put("editable", node.isEditable)
            .put("focusable", node.isFocusable).put("enabled", node.isEnabled)
            .put("selected", node.isSelected).put("depth", depth))
        for (index in 0 until node.childCount) {
            if (count[0] >= MAX_NODES) break
            node.getChild(index)?.let { child ->
                appendNode(child, output, depth + 1, count)
                child.recycle()
            }
        }
    }

    private fun screenshot(): JSONObject {
        if (Build.VERSION.SDK_INT < 30) return JSONObject().put("available", false).put("reason", "requires_android_11")
        val latch = CountDownLatch(1)
        var encoded: String? = null
        var failure = "capture_failed"
        takeScreenshot(Display.DEFAULT_DISPLAY, mainExecutor, object : TakeScreenshotCallback {
            override fun onSuccess(result: ScreenshotResult) {
                try {
                    val bitmap = Bitmap.wrapHardwareBuffer(result.hardwareBuffer, result.colorSpace)
                    if (bitmap == null) failure = "bitmap_unavailable" else {
                        val scale = minOf(1f, 1280f / maxOf(bitmap.width, bitmap.height))
                        val outputBitmap = if (scale < 1f) Bitmap.createScaledBitmap(
                            bitmap, (bitmap.width * scale).toInt().coerceAtLeast(1),
                            (bitmap.height * scale).toInt().coerceAtLeast(1), true
                        ) else bitmap
                        val bytes = java.io.ByteArrayOutputStream()
                        outputBitmap.compress(Bitmap.CompressFormat.JPEG, 72, bytes)
                        encoded = Base64.encodeToString(bytes.toByteArray(), Base64.NO_WRAP)
                        if (outputBitmap !== bitmap) outputBitmap.recycle()
                        bitmap.recycle()
                    }
                    result.hardwareBuffer.close()
                } catch (_: Exception) { failure = "encode_failed" } finally { latch.countDown() }
            }
            override fun onFailure(errorCode: Int) {
                failure = "android_screenshot_error_$errorCode"
                latch.countDown()
            }
        })
        if (!latch.await(8, TimeUnit.SECONDS)) return JSONObject().put("available", false).put("reason", "capture_timeout")
        return if (encoded != null) JSONObject().put("available", true).put("mime_type", "image/jpeg")
            .put("width_limit", 1280).put("image_base64", encoded)
        else JSONObject().put("available", false).put("reason", failure)
    }

    private fun performAction(body: JSONObject): JSONObject {
        val action = body.optString("action")
        val success = when (action) {
            "back" -> performGlobalAction(GLOBAL_ACTION_BACK)
            "home" -> performGlobalAction(GLOBAL_ACTION_HOME)
            "recents" -> performGlobalAction(GLOBAL_ACTION_RECENTS)
            "tap" -> {
                val x = body.optDouble("x", Double.NaN).toFloat()
                val y = body.optDouble("y", Double.NaN).toFloat()
                if (!x.isFinite() || !y.isFinite() || x !in 0f..10000f || y !in 0f..10000f) false else dispatchTap(x, y)
            }
            "swipe" -> {
                val x1 = body.optDouble("x1", Double.NaN).toFloat()
                val y1 = body.optDouble("y1", Double.NaN).toFloat()
                val x2 = body.optDouble("x2", Double.NaN).toFloat()
                val y2 = body.optDouble("y2", Double.NaN).toFloat()
                val duration = body.optLong("duration_ms", 350L).coerceIn(80L, 1500L)
                if (listOf(x1, y1, x2, y2).any { !it.isFinite() || it !in 0f..10000f }) false
                else dispatchSwipe(x1, y1, x2, y2, duration)
            }
            "click_text" -> {
                val text = body.optString("text")
                if (text.isBlank() || text.length > 500) false
                else findNode { !it.isPassword && it.text?.toString() == text }?.let { clickNode(it) } ?: false
            }
            "click_view_id" -> {
                val viewId = body.optString("view_id")
                if (viewId.isBlank() || viewId.length > 300) false
                else findNode { it.viewIdResourceName == viewId }?.let { clickNode(it) } ?: false
            }
            "set_text" -> {
                val viewId = body.optString("view_id")
                val text = body.optString("text")
                if (viewId.isBlank() || viewId.length > 300 || text.length > 2000) false
                else {
                    val target = findNode { it.viewIdResourceName == viewId && it.isEditable && !it.isPassword }
                    target?.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, Bundle().apply {
                        putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text)
                    }) ?: false
                }
            }
            else -> return JSONObject().put("success", false).put("error", "unsupported_action")
        }
        return JSONObject().put("success", success).put("action", action)
    }

    private fun findNode(predicate: (AccessibilityNodeInfo) -> Boolean): AccessibilityNodeInfo? {
        val root = rootInActiveWindow ?: return null
        fun search(node: AccessibilityNodeInfo, depth: Int): AccessibilityNodeInfo? {
            if (depth > MAX_DEPTH) return null
            if (predicate(node)) return AccessibilityNodeInfo.obtain(node)
            for (index in 0 until node.childCount) {
                val child = node.getChild(index) ?: continue
                val found = search(child, depth + 1)
                child.recycle()
                if (found != null) return found
            }
            return null
        }
        return try {
            search(root, 0)
        } finally {
            root.recycle()
        }
    }

    private fun clickNode(node: AccessibilityNodeInfo): Boolean {
        var current: AccessibilityNodeInfo? = node
        try {
            repeat(MAX_DEPTH + 1) {
                val candidate = current ?: return false
                if (candidate.isClickable) return candidate.performAction(AccessibilityNodeInfo.ACTION_CLICK)
                val parent = candidate.parent
                if (candidate !== node) candidate.recycle()
                current = parent
            }
            return false
        } finally {
            current?.let { if (it !== node) it.recycle() }
            node.recycle()
        }
    }

    private fun dispatchTap(x: Float, y: Float): Boolean {
        val path = Path().apply { moveTo(x, y) }
        val gesture = GestureDescription.Builder().addStroke(
            GestureDescription.StrokeDescription(path, 0, 80)
        ).build()
        return dispatchGesture(gesture, null, null)
    }

    private fun dispatchSwipe(x1: Float, y1: Float, x2: Float, y2: Float, duration: Long): Boolean {
        val path = Path().apply { moveTo(x1, y1); lineTo(x2, y2) }
        val gesture = GestureDescription.Builder().addStroke(
            GestureDescription.StrokeDescription(path, 0, duration)
        ).build()
        return dispatchGesture(gesture, null, null)
    }

    private fun readLine(input: BufferedInputStream, limit: Int): String? {
        val bytes = java.io.ByteArrayOutputStream()
        while (bytes.size() <= limit) {
            val value = input.read()
            if (value < 0) return if (bytes.size() == 0) null else bytes.toString("UTF-8")
            if (value == 10) break
            if (value != 13) bytes.write(value)
        }
        if (bytes.size() > limit) throw IllegalArgumentException("header_too_large")
        return bytes.toString("UTF-8")
    }

    private fun writeResponse(output: BufferedOutputStream, status: Int, payload: JSONObject) {
        val body = payload.toString().toByteArray(Charsets.UTF_8)
        val reason = when (status) { 200 -> "OK"; 400 -> "Bad Request"; 401 -> "Unauthorized"; 413 -> "Payload Too Large"; else -> "Internal Server Error" }
        val header = "HTTP/1.1 $status $reason\r\nContent-Type: application/json; charset=utf-8\r\n" +
            "Content-Length: ${body.size}\r\nConnection: close\r\nCache-Control: no-store\r\n\r\n"
        output.write(header.toByteArray(Charsets.US_ASCII))
        output.write(body)
        output.flush()
    }

    override fun onDestroy() {
        isEnabled = false
        try { server?.close() } catch (_: Exception) { }
        server = null
        listenerThread?.interrupt()
        listenerThread = null
        clientExecutor.shutdownNow()
        super.onDestroy()
    }

    companion object {
        const val PORT = 18766
        private const val TAG = "JarvisAccessibility"
        private const val MAX_BODY_BYTES = 32 * 1024
        private const val MAX_NODES = 300
        private const val MAX_DEPTH = 12
        @Volatile var isEnabled: Boolean = false
            private set
    }
}
