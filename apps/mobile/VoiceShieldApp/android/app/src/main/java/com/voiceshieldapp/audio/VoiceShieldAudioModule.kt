package com.voiceshieldapp.audio

import android.Manifest
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Process
import android.util.Base64
import androidx.core.content.ContextCompat
import com.facebook.react.bridge.Arguments
import com.facebook.react.bridge.Promise
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReactContextBaseJavaModule
import com.facebook.react.bridge.ReactMethod
import com.facebook.react.bridge.ReadableMap
import com.facebook.react.modules.core.DeviceEventManagerModule
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

        const val TARGET_SAMPLE_RATE = 16000
        const val TARGET_CHANNELS = AudioFormat.CHANNEL_IN_MONO
        const val TARGET_ENCODING = AudioFormat.ENCODING_PCM_16BIT
        const val TARGET_SAMPLES_PER_CHUNK = 4000 // 250 ms @ 16 kHz
        const val TARGET_BYTES_PER_CHUNK = 8000   // 4000 samples * 2 bytes

        // Standard fallback input rates to probe if 16 kHz is rejected by HAL
        private val FALLBACK_SAMPLE_RATES = intArrayOf(48000, 44100, 22050, 8000)
    }

    private val isCapturing = AtomicBoolean(false)
    private val nativeSeq = AtomicInteger(0)
    private var captureThread: Thread? = null
    private var audioRecord: AudioRecord? = null

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

    override fun invalidate() {
        super.invalidate()
        isCapturing.set(false)
        cleanupNativeResources()
    }
}
