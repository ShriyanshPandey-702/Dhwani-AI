package com.voiceshieldapp.audio

import android.Manifest
import android.content.pm.PackageManager
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.MediaPlayer
import android.media.MediaRecorder
import android.os.Process
import android.util.Base64
import androidx.core.content.ContextCompat
import com.facebook.react.bridge.Arguments
import com.facebook.react.bridge.Promise
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReactContextBaseJavaModule
import com.facebook.react.bridge.ReactMethod
import com.facebook.react.bridge.ReadableArray
import com.facebook.react.bridge.ReadableMap
import com.facebook.react.modules.core.DeviceEventManagerModule
import java.io.InputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger

/**
 * Native Android Audio Capture Module for VoiceShield.
 *
 * Captures raw microphone audio via Android AudioRecord and delivers verified
 * 16 kHz mono signed 16-bit linear PCM little-endian in 250 ms chunks
 * (4,000 samples / 8,000 bytes) over the React Native bridge.
 *
 * Sequence Numbering Invariant:
 * This module is the sole owner of the authoritative audio sequence number
 * (`seq = 0, 1, 2, 3...`), which resets to 0 on every capture session.
 */
class VoiceShieldAudioModule(private val reactContext: ReactApplicationContext) :
    ReactContextBaseJavaModule(reactContext) {

    companion object {
        const val MODULE_NAME = "VoiceShieldAudioCapture"
        const val EVENT_AUDIO_CHUNK = "onAudioChunk"
        const val EVENT_AUDIO_ERROR = "onAudioCaptureError"
        const val EVENT_SEGMENT_CHANGE = "onFileSegmentChange"
        const val EVENT_PLAYBACK_COMPLETE = "onFilePlaybackComplete"

        const val TARGET_SAMPLE_RATE = 16000
        const val TARGET_CHANNELS = AudioFormat.CHANNEL_IN_MONO
        const val TARGET_ENCODING = AudioFormat.ENCODING_PCM_16BIT
        const val TARGET_SAMPLES_PER_CHUNK = 4000 // 250 ms @ 16 kHz
        const val TARGET_BYTES_PER_CHUNK = 8000   // 4000 samples * 2 bytes

        // Standard fallback input rates to probe if 16 kHz is rejected by HAL
        private val FALLBACK_SAMPLE_RATES = intArrayOf(48000, 44100, 22050, 8000)

        // WAV PCM header is 44 bytes for standard format
        private const val WAV_HEADER_BYTES = 44
    }

    private val isCapturing = AtomicBoolean(false)
    private val nativeSeq = AtomicInteger(0)
    private var captureThread: Thread? = null
    private var audioRecord: AudioRecord? = null

    // File-based streaming state
    private val isFileStreaming = AtomicBoolean(false)
    private var fileStreamThread: Thread? = null
    private var audioTrack: AudioTrack? = null

    // In-app media player for forensic / sample audio preview
    private var inAppPlayer: MediaPlayer? = null

    // Track listener count for React Native NativeEventEmitter
    private var listenerCount = 0

    override fun getName(): String = MODULE_NAME

    @ReactMethod
    fun checkPermission(promise: Promise) {
        val granted = ContextCompat.checkSelfPermission(
            reactContext,
            Manifest.permission.RECORD_AUDIO
        ) == PackageManager.PERMISSION_GRANTED
        promise.resolve(if (granted) "granted" else "denied")
    }

    @ReactMethod
    fun isCapturing(promise: Promise) {
        promise.resolve(isCapturing.get())
    }

    @ReactMethod
    fun startCapture(options: ReadableMap?, promise: Promise) {
        if (isCapturing.get()) {
            val res = Arguments.createMap().apply {
                putBoolean("alreadyCapturing", true)
                putInt("sampleRate", TARGET_SAMPLE_RATE)
            }
            promise.resolve(res)
            return
        }

        // Verify runtime permission
        val hasPermission = ContextCompat.checkSelfPermission(
            reactContext,
            Manifest.permission.RECORD_AUDIO
        ) == PackageManager.PERMISSION_GRANTED

        if (!hasPermission) {
            promise.reject("E_PERMISSION_DENIED", "RECORD_AUDIO permission is not granted")
            return
        }

        try {
            // Probe and initialize AudioRecord
            val initResult = probeAndInitializeAudioRecord()
            if (initResult == null) {
                promise.reject(
                    "E_INITIALIZATION_FAILED",
                    "Failed to initialize AudioRecord: no supported input sample rate found"
                )
                return
            }

            val (record, actualRate) = initResult
            audioRecord = record

            // Reset authoritative native sequence for new session
            nativeSeq.set(0)
            isCapturing.set(true)

            // Spawn dedicated background capture thread
            captureThread = Thread({
                runAudioCaptureLoop(record, actualRate)
            }, "VoiceShieldAudioThread").apply {
                start()
            }

            val res = Arguments.createMap().apply {
                putBoolean("started", true)
                putInt("sampleRate", TARGET_SAMPLE_RATE)
                putInt("channels", 1)
                putInt("chunkSizeBytes", TARGET_BYTES_PER_CHUNK)
                putInt("hardwareSampleRate", actualRate)
            }
            promise.resolve(res)
        } catch (e: Exception) {
            cleanupNativeResources()
            promise.reject("E_START_FAILED", "Exception starting audio capture: ${e.message}", e)
        }
    }

    @ReactMethod
    fun stopCapture(promise: Promise) {
        if (!isCapturing.get()) {
            val res = Arguments.createMap().apply {
                putBoolean("alreadyStopped", true)
                putInt("totalChunksEmitted", nativeSeq.get())
            }
            promise.resolve(res)
            return
        }

        isCapturing.set(false)

        try {
            // Wait briefly for background thread to exit loop
            captureThread?.let { thread ->
                if (thread.isAlive) {
                    thread.interrupt()
                    thread.join(600)
                }
            }
        } catch (_: InterruptedException) {
            // Clean exit
        } finally {
            cleanupNativeResources()
        }

        val res = Arguments.createMap().apply {
            putBoolean("stopped", true)
            putInt("totalChunksEmitted", nativeSeq.get())
        }
        promise.resolve(res)
    }

    @ReactMethod
    fun addListener(eventName: String) {
        listenerCount++
    }

    @ReactMethod
    fun removeListeners(count: Int) {
        listenerCount = maxOf(0, listenerCount - count)
    }

    /**
     * Probes input capabilities directly using AudioRecord.
     * Checks 16 kHz first; if HAL rejects, probes standard fallback input rates.
     */
    private fun probeAndInitializeAudioRecord(): Pair<AudioRecord, Int>? {
        // 1. First probe 16,000 Hz directly
        val minBuf16k = AudioRecord.getMinBufferSize(
            TARGET_SAMPLE_RATE,
            TARGET_CHANNELS,
            TARGET_ENCODING
        )

        if (minBuf16k > 0) {
            val bufSize = maxOf(minBuf16k, TARGET_BYTES_PER_CHUNK * 2)
            try {
                val record = AudioRecord(
                    MediaRecorder.AudioSource.MIC,
                    TARGET_SAMPLE_RATE,
                    TARGET_CHANNELS,
                    TARGET_ENCODING,
                    bufSize
                )
                if (record.state == AudioRecord.STATE_INITIALIZED) {
                    return Pair(record, TARGET_SAMPLE_RATE)
                }
                record.release()
            } catch (_: Exception) {
                // Fall through to probe fallback input rates
            }
        }

        // 2. Probe fallback sample rates supported by input hardware
        for (rate in FALLBACK_SAMPLE_RATES) {
            val minBuf = AudioRecord.getMinBufferSize(rate, TARGET_CHANNELS, TARGET_ENCODING)
            if (minBuf > 0) {
                val bufSize = maxOf(minBuf, (rate * 0.25 * 2).toInt() * 2)
                try {
                    val record = AudioRecord(
                        MediaRecorder.AudioSource.MIC,
                        rate,
                        TARGET_CHANNELS,
                        TARGET_ENCODING,
                        bufSize
                    )
                    if (record.state == AudioRecord.STATE_INITIALIZED) {
                        return Pair(record, rate)
                    }
                    record.release()
                } catch (_: Exception) {
                    continue
                }
            }
        }

        return null
    }

    /**
     * Continuous audio read loop executed on VoiceShieldAudioThread.
     */
    private fun runAudioCaptureLoop(record: AudioRecord, hardwareRate: Int) {
        Process.setThreadPriority(Process.THREAD_PRIORITY_URGENT_AUDIO)

        try {
            record.startRecording()
        } catch (e: Exception) {
            emitError("RECORDING_START_FAILED", "Could not start recording: ${e.message}")
            isCapturing.set(false)
            return
        }

        val needsResampling = (hardwareRate != TARGET_SAMPLE_RATE)
        val hwChunkSamples = (hardwareRate * 0.25).toInt()
        val readBuffer = ShortArray(hwChunkSamples)
        val resampledBuffer = ShortArray(TARGET_SAMPLES_PER_CHUNK)
        val byteBuffer = ByteBuffer.allocate(TARGET_BYTES_PER_CHUNK).apply {
            order(ByteOrder.LITTLE_ENDIAN)
        }

        while (isCapturing.get() && !Thread.currentThread().isInterrupted) {
            var samplesReadTotal = 0
            while (samplesReadTotal < hwChunkSamples && isCapturing.get()) {
                val toRead = hwChunkSamples - samplesReadTotal
                val read = record.read(readBuffer, samplesReadTotal, toRead)
                if (read < 0) {
                    if (isCapturing.get()) {
                        emitError("AUDIO_RECORD_ERROR", "AudioRecord.read error code: $read")
                    }
                    break
                }
                samplesReadTotal += read
            }

            if (!isCapturing.get() || samplesReadTotal < hwChunkSamples) {
                break
            }

            // Resample to exactly 16 kHz if necessary
            val finalSamples: ShortArray = if (needsResampling) {
                resampleLinear(readBuffer, hardwareRate, resampledBuffer, TARGET_SAMPLE_RATE)
                resampledBuffer
            } else {
                readBuffer
            }

            // Convert ShortArray to little-endian byte array
            byteBuffer.clear()
            for (sample in finalSamples) {
                byteBuffer.putShort(sample)
            }
            val pcmBytes = byteBuffer.array()

            // Encode to Base64 without newlines
            val base64Data = Base64.encodeToString(pcmBytes, Base64.NO_WRAP)

            // Authoritative sequence number increment
            val seq = nativeSeq.getAndIncrement()

            emitAudioChunk(base64Data, seq)
        }

        try {
            if (record.recordingState == AudioRecord.RECORDSTATE_RECORDING) {
                record.stop()
            }
        } catch (_: Exception) {}
    }

    /**
     * Deterministic linear resampling from inputRate to outputRate.
     * Guarantees exact outputLength (4,000 samples) with zero drift.
     */
    private fun resampleLinear(
        input: ShortArray,
        inputRate: Int,
        output: ShortArray,
        outputRate: Int
    ) {
        val outLen = output.size
        val inLen = input.size
        val ratio = inputRate.toDouble() / outputRate.toDouble()

        for (i in 0 until outLen) {
            val srcPos = i * ratio
            val srcIdx = srcPos.toInt()
            val frac = srcPos - srcIdx

            val sample = if (srcIdx + 1 < inLen) {
                val s1 = input[srcIdx].toDouble()
                val s2 = input[srcIdx + 1].toDouble()
                (s1 + frac * (s2 - s1)).toInt()
            } else if (srcIdx < inLen) {
                input[srcIdx].toInt()
            } else {
                0
            }

            output[i] = sample.coerceIn(Short.MIN_VALUE.toInt(), Short.MAX_VALUE.toInt()).toShort()
        }
    }

    private fun emitAudioChunk(base64Data: String, seq: Int) {
        try {
            val params = Arguments.createMap().apply {
                putString("data", base64Data)
                putInt("seq", seq)
                putDouble("timestamp", System.currentTimeMillis().toDouble())
                putInt("byteLength", TARGET_BYTES_PER_CHUNK)
                putInt("samples", TARGET_SAMPLES_PER_CHUNK)
            }
            reactContext
                .getJSModule(DeviceEventManagerModule.RCTDeviceEventEmitter::class.java)
                .emit(EVENT_AUDIO_CHUNK, params)
        } catch (_: Exception) {
            // Bridge may be tearing down
        }
    }

    private fun emitError(code: String, message: String) {
        try {
            val params = Arguments.createMap().apply {
                putString("code", code)
                putString("message", message)
            }
            reactContext
                .getJSModule(DeviceEventManagerModule.RCTDeviceEventEmitter::class.java)
                .emit(EVENT_AUDIO_ERROR, params)
        } catch (_: Exception) {
            // Bridge may be tearing down
        }
    }

    private fun cleanupNativeResources() {
        try {
            audioRecord?.let {
                if (it.recordingState == AudioRecord.RECORDSTATE_RECORDING) {
                    it.stop()
                }
                it.release()
            }
        } catch (_: Exception) {}
        audioRecord = null
        captureThread = null
    }

    // ── File-based WAV asset streaming ─────────────────────────────────────

    /**
     * Streams a single WAV file from assets:
     * - Plays audio through the device speaker via AudioTrack (audible)
     * - Emits onAudioChunk events with the same format as mic capture
     *
     * The WAV must be 16kHz, mono, PCM16 (same as mic pipeline target).
     * @param assetPath path within assets directory, e.g. "recording_samples/voice_a.wav"
     */
    @ReactMethod
    fun startFileCapture(assetPath: String, promise: Promise) {
        if (isFileStreaming.get() || isCapturing.get()) {
            promise.reject("E_ALREADY_ACTIVE", "Audio capture or file streaming is already active")
            return
        }

        nativeSeq.set(0)
        isFileStreaming.set(true)

        fileStreamThread = Thread({
            runFilePlaybackLoop(listOf(assetPath), promise)
        }, "VoiceShieldFileStreamThread").apply { start() }
    }

    /**
     * Streams multiple WAV files sequentially (gapless A→B→C).
     * Emits onSegmentChange at each file boundary.
     * @param assetPaths ReadableArray of asset paths
     */
    @ReactMethod
    fun startFileSequence(assetPaths: ReadableArray, promise: Promise) {
        if (isFileStreaming.get() || isCapturing.get()) {
            promise.reject("E_ALREADY_ACTIVE", "Audio capture or file streaming is already active")
            return
        }

        val paths = (0 until assetPaths.size()).map { assetPaths.getString(it) ?: "" }
            .filter { it.isNotBlank() }

        if (paths.isEmpty()) {
            promise.reject("E_NO_PATHS", "No valid asset paths provided")
            return
        }

        nativeSeq.set(0)
        isFileStreaming.set(true)

        fileStreamThread = Thread({
            runFilePlaybackLoop(paths, promise)
        }, "VoiceShieldFileStreamThread").apply { start() }
    }

    @ReactMethod
    fun stopFileCapture(promise: Promise) {
        isFileStreaming.set(false)
        try {
            fileStreamThread?.let { t ->
                if (t.isAlive) {
                    t.interrupt()
                    t.join(800)
                }
            }
        } catch (_: InterruptedException) {}
        cleanupFileResources()
        val res = Arguments.createMap().apply {
            putBoolean("stopped", true)
            putInt("totalChunksEmitted", nativeSeq.get())
        }
        promise.resolve(res)
    }

    @ReactMethod
    fun isFileStreaming(promise: Promise) {
        promise.resolve(isFileStreaming.get())
    }

    private fun runFilePlaybackLoop(paths: List<String>, promise: Promise) {
        Process.setThreadPriority(Process.THREAD_PRIORITY_URGENT_AUDIO)

        // Initialize AudioTrack for playback (speaker output)
        val minBuf = AudioTrack.getMinBufferSize(
            TARGET_SAMPLE_RATE,
            AudioFormat.CHANNEL_OUT_MONO,
            AudioFormat.ENCODING_PCM_16BIT
        )
        val trackBufSize = maxOf(minBuf, TARGET_BYTES_PER_CHUNK * 2)

        val track = try {
            AudioTrack(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_MEDIA)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build(),
                AudioFormat.Builder()
                    .setSampleRate(TARGET_SAMPLE_RATE)
                    .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .build(),
                trackBufSize,
                AudioTrack.MODE_STREAM,
                AudioManager.AUDIO_SESSION_ID_GENERATE
            )
        } catch (e: Exception) {
            isFileStreaming.set(false)
            promise.reject("E_AUDIO_TRACK_INIT", "AudioTrack initialization failed: ${e.message}", e)
            return
        }

        audioTrack = track

        try {
            track.play()
        } catch (e: Exception) {
            isFileStreaming.set(false)
            track.release()
            audioTrack = null
            promise.reject("E_AUDIO_TRACK_PLAY", "AudioTrack.play() failed: ${e.message}", e)
            return
        }

        val assetManager = reactContext.assets
        val chunkBuffer = ByteArray(TARGET_BYTES_PER_CHUNK)
        val b64Buffer = ByteBuffer.allocate(TARGET_BYTES_PER_CHUNK).apply { order(ByteOrder.LITTLE_ENDIAN) }

        var resolvedOk = false

        for ((segmentIndex, assetPath) in paths.withIndex()) {
            if (!isFileStreaming.get() || Thread.currentThread().isInterrupted) break

            // Emit segment change event so JS can update transcript / labels
            emitSegmentChange(segmentIndex, assetPath)

            var inputStream: InputStream? = null
            try {
                inputStream = assetManager.open(assetPath)

                // Skip WAV header (44 bytes standard PCM)
                val headerBuf = ByteArray(WAV_HEADER_BYTES)
                var headerRead = 0
                while (headerRead < WAV_HEADER_BYTES) {
                    val r = inputStream.read(headerBuf, headerRead, WAV_HEADER_BYTES - headerRead)
                    if (r < 0) break
                    headerRead += r
                }

                // Stream PCM data in TARGET_BYTES_PER_CHUNK blocks
                var bytesRead: Int
                while (isFileStreaming.get() && !Thread.currentThread().isInterrupted) {
                    var totalRead = 0
                    while (totalRead < TARGET_BYTES_PER_CHUNK) {
                        bytesRead = inputStream.read(chunkBuffer, totalRead, TARGET_BYTES_PER_CHUNK - totalRead)
                        if (bytesRead < 0) break
                        totalRead += bytesRead
                    }

                    if (totalRead == 0) break // EOF

                    // Zero-pad last chunk if needed
                    if (totalRead < TARGET_BYTES_PER_CHUNK) {
                        chunkBuffer.fill(0, totalRead, TARGET_BYTES_PER_CHUNK)
                    }

                    // Play through speaker
                    track.write(chunkBuffer, 0, TARGET_BYTES_PER_CHUNK)

                    // Encode to Base64 and emit as onAudioChunk
                    val base64Data = Base64.encodeToString(chunkBuffer, Base64.NO_WRAP)
                    val seq = nativeSeq.getAndIncrement()
                    emitAudioChunk(base64Data, seq)

                    // Real-time pacing: sleep 250ms per 250ms chunk
                    try {
                        Thread.sleep(250)
                    } catch (_: InterruptedException) {
                        Thread.currentThread().interrupt()
                        break
                    }
                }
            } catch (e: Exception) {
                if (isFileStreaming.get()) {
                    emitError("FILE_READ_ERROR", "Error reading asset '$assetPath': ${e.message}")
                }
            } finally {
                try { inputStream?.close() } catch (_: Exception) {}
            }
        }

        // Playback complete
        if (isFileStreaming.get()) {
            emitPlaybackComplete(nativeSeq.get())
        }

        isFileStreaming.set(false)
        cleanupFileResources()

        if (!resolvedOk) {
            val res = Arguments.createMap().apply {
                putBoolean("completed", true)
                putInt("totalChunksEmitted", nativeSeq.get())
            }
            promise.resolve(res)
        }
    }

    private fun cleanupFileResources() {
        try {
            audioTrack?.let { t ->
                if (t.playState == AudioTrack.PLAYSTATE_PLAYING) t.stop()
                t.release()
            }
        } catch (_: Exception) {}
        audioTrack = null
        fileStreamThread = null
    }

    private fun emitSegmentChange(index: Int, assetPath: String) {
        try {
            val params = Arguments.createMap().apply {
                putInt("segmentIndex", index)
                putString("assetPath", assetPath)
                putDouble("timestamp", System.currentTimeMillis().toDouble())
            }
            reactContext
                .getJSModule(DeviceEventManagerModule.RCTDeviceEventEmitter::class.java)
                .emit(EVENT_SEGMENT_CHANGE, params)
        } catch (_: Exception) {}
    }

    private fun emitPlaybackComplete(totalChunks: Int) {
        try {
            val params = Arguments.createMap().apply {
                putInt("totalChunks", totalChunks)
                putDouble("timestamp", System.currentTimeMillis().toDouble())
            }
            reactContext
                .getJSModule(DeviceEventManagerModule.RCTDeviceEventEmitter::class.java)
                .emit(EVENT_PLAYBACK_COMPLETE, params)
        } catch (_: Exception) {}
    }

    // ── In-app audio playback for forensic inspection & live demo ─────────────
    @ReactMethod
    fun playMediaUri(uriString: String, promise: Promise) {
        try {
            stopMediaPlaybackInternal()
            val player = MediaPlayer()
            inAppPlayer = player

            if (uriString.startsWith("asset://") || (!uriString.startsWith("http://") && !uriString.startsWith("https://") && !uriString.startsWith("file://") && !uriString.startsWith("content://"))) {
                val assetPath = if (uriString.startsWith("asset://")) uriString.substring(8) else uriString
                val afd = reactContext.assets.openFd(assetPath)
                player.setDataSource(afd.fileDescriptor, afd.startOffset, afd.length)
                afd.close()
            } else {
                val uri = android.net.Uri.parse(uriString)
                player.setDataSource(reactContext, uri)
            }

            player.setOnPreparedListener { mp ->
                mp.start()
                val res = Arguments.createMap().apply {
                    putBoolean("success", true)
                    putInt("durationMs", mp.duration)
                }
                promise.resolve(res)
            }
            player.setOnCompletionListener {
                stopMediaPlaybackInternal()
            }
            player.setOnErrorListener { _, what, extra ->
                try {
                    promise.reject("E_PLAY_MEDIA", "MediaPlayer error $what / $extra")
                } catch (_: Exception) {}
                stopMediaPlaybackInternal()
                true
            }
            player.prepareAsync()
        } catch (e: Exception) {
            stopMediaPlaybackInternal()
            promise.reject("E_PLAY_MEDIA", "Failed to play audio: ${e.message}", e)
        }
    }

    @ReactMethod
    fun seekMediaUri(positionMs: Int, promise: Promise) {
        try {
            inAppPlayer?.seekTo(positionMs)
            promise.resolve(true)
        } catch (e: Exception) {
            promise.reject("E_SEEK_MEDIA", e.message, e)
        }
    }

    @ReactMethod
    fun pauseMediaUri(promise: Promise) {
        try {
            inAppPlayer?.let {
                if (it.isPlaying) it.pause()
            }
            promise.resolve(true)
        } catch (e: Exception) {
            promise.reject("E_PAUSE_MEDIA", e.message, e)
        }
    }

    @ReactMethod
    fun resumeMediaUri(promise: Promise) {
        try {
            inAppPlayer?.let {
                if (!it.isPlaying) it.start()
            }
            promise.resolve(true)
        } catch (e: Exception) {
            promise.reject("E_RESUME_MEDIA", e.message, e)
        }
    }

    @ReactMethod
    fun stopMediaPlayback(promise: Promise) {
        stopMediaPlaybackInternal()
        promise.resolve(true)
    }

    @ReactMethod
    fun getMediaStatus(promise: Promise) {
        val playing = inAppPlayer?.isPlaying == true
        val pos = inAppPlayer?.currentPosition ?: 0
        val dur = inAppPlayer?.duration ?: 0
        val res = Arguments.createMap().apply {
            putBoolean("isPlaying", playing)
            putInt("positionMs", pos)
            putInt("durationMs", dur)
        }
        promise.resolve(res)
    }

    private fun stopMediaPlaybackInternal() {
        try {
            inAppPlayer?.let {
                if (it.isPlaying) it.stop()
                it.release()
            }
        } catch (_: Exception) {}
        inAppPlayer = null
    }

    override fun invalidate() {
        super.invalidate()
        isCapturing.set(false)
        isFileStreaming.set(false)
        cleanupNativeResources()
        cleanupFileResources()
        stopMediaPlaybackInternal()
    }
}
