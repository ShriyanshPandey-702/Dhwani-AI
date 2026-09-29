package com.voiceshieldapp.telecom

import android.app.Activity
import android.app.role.RoleManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.provider.OpenableColumns
import android.provider.Settings
import android.util.Log
import com.facebook.react.bridge.ActivityEventListener
import com.facebook.react.bridge.Arguments
import com.facebook.react.bridge.BaseActivityEventListener
import com.facebook.react.bridge.Promise
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReactContextBaseJavaModule
import com.facebook.react.bridge.ReactMethod
import com.facebook.react.bridge.WritableArray
import com.facebook.react.bridge.WritableMap
import com.facebook.react.modules.core.DeviceEventManagerModule
import java.io.File
import java.lang.ref.WeakReference

/**
 * React Native native module bridging Android Telecom CallScreeningService,
 * RoleManager, local audio file selection, and demo audio assets to JavaScript.
 */
class VoiceShieldCallScreeningModule(private val reactContext: ReactApplicationContext) :
    ReactContextBaseJavaModule(reactContext) {

    companion object {
        const val MODULE_NAME = "VoiceShieldCallScreening"
        const val EVENT_CALL_SCREENED = "onIncomingCallScreened"
        const val EVENT_ROLE_STATUS_CHANGED = "onRoleStatusChanged"
        private const val TAG = "VoiceShieldTelecom"

        private const val REQUEST_CODE_ROLE = 4040
        private const val REQUEST_CODE_SETTINGS = 4041
        private const val REQUEST_CODE_PICK_AUDIO = 4042

        private var currentInstance: WeakReference<VoiceShieldCallScreeningModule>? = null

        /**
         * Called by VoiceShieldCallScreeningService when a call is screened.
         * Dispatches event to active JS environment.
         */
        fun notifyCallScreened(record: ScreenedCallRecord) {
            Log.i(TAG, "Dispatching onIncomingCallScreened to React Native for event ${record.eventId}")
            currentInstance?.get()?.sendCallScreenedEvent(record)
        }
    }

    private var pendingRolePromise: Promise? = null
    private var pendingSettingsPromise: Promise? = null
    private var pendingPickPromise: Promise? = null
    private val storage = CallScreeningStorage(reactContext)

    private val activityEventListener: ActivityEventListener = object : BaseActivityEventListener() {
        override fun onActivityResult(
            activity: Activity,
            requestCode: Int,
            resultCode: Int,
            data: Intent?
        ) {
            when (requestCode) {
                REQUEST_CODE_ROLE -> {
                    val promise = pendingRolePromise
                    pendingRolePromise = null

                    val isHeld = checkIsRoleHeld()
                    Log.i(TAG, "Role request finished, isRoleHeld=$isHeld")
                    val result = Arguments.createMap().apply {
                        putBoolean("granted", isHeld)
                        putBoolean("alreadyHeld", false)
                    }
                    promise?.resolve(result)
                    sendRoleStatusChanged(isHeld)
                }
                REQUEST_CODE_SETTINGS -> {
                    val promise = pendingSettingsPromise
                    pendingSettingsPromise = null

                    val isHeld = checkIsRoleHeld()
                    Log.i(TAG, "Returned from settings, isRoleHeld=$isHeld")
                    promise?.resolve(isHeld)
                    sendRoleStatusChanged(isHeld)
                }
                REQUEST_CODE_PICK_AUDIO -> {
                    val promise = pendingPickPromise
                    pendingPickPromise = null

                    if (resultCode == Activity.RESULT_OK && data?.data != null) {
                        try {
                            val map = handlePickedAudio(data.data!!)
                            promise?.resolve(map)
                        } catch (e: Exception) {
                            Log.e(TAG, "Error processing picked audio: ${e.message}", e)
                            promise?.reject("PICK_AUDIO_ERROR", e.message, e)
                        }
                    } else {
                        promise?.resolve(null)
                    }
                }
            }
        }
    }

    init {
        currentInstance = WeakReference(this)
        reactContext.addActivityEventListener(activityEventListener)
    }

    override fun getName(): String = MODULE_NAME

    private fun checkIsRoleHeld(): Boolean {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val roleManager = reactContext.getSystemService(RoleManager::class.java)
            roleManager?.isRoleHeld(RoleManager.ROLE_CALL_SCREENING) == true
        } else {
            false
        }
    }

    @ReactMethod
    fun isRoleHeld(promise: Promise) {
        try {
            val held = checkIsRoleHeld()
            promise.resolve(held)
        } catch (e: Exception) {
            promise.reject("ROLE_CHECK_FAILED", e.message, e)
        }
    }

    @ReactMethod
    fun getRoleAvailability(promise: Promise) {
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                val roleManager = reactContext.getSystemService(RoleManager::class.java)
                promise.resolve(roleManager?.isRoleAvailable(RoleManager.ROLE_CALL_SCREENING) == true)
            } else {
                promise.resolve(false)
            }
        } catch (e: Exception) {
            promise.reject("ROLE_AVAILABILITY_FAILED", e.message, e)
        }
    }

    @ReactMethod
    fun requestRole(promise: Promise) {
        try {
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) {
                val result = Arguments.createMap().apply {
                    putBoolean("granted", false)
                    putBoolean("alreadyHeld", false)
                    putString("error", "ROLE_MANAGER_UNAVAILABLE_API_LEVEL")
                }
                promise.resolve(result)
                return
            }

            val roleManager = reactContext.getSystemService(RoleManager::class.java)
            if (roleManager == null) {
                promise.reject("NO_ROLE_MANAGER", "RoleManager not available on this device")
                return
            }

            if (roleManager.isRoleHeld(RoleManager.ROLE_CALL_SCREENING)) {
                val result = Arguments.createMap().apply {
                    putBoolean("granted", true)
                    putBoolean("alreadyHeld", true)
                }
                promise.resolve(result)
                return
            }

            val act = reactContext.currentActivity
            if (act == null) {
                promise.reject("NO_ACTIVITY", "Cannot request role without foreground activity")
                return
            }

            pendingRolePromise = promise
            val intent = roleManager.createRequestRoleIntent(RoleManager.ROLE_CALL_SCREENING)
            act.startActivityForResult(intent, REQUEST_CODE_ROLE)
        } catch (e: Exception) {
            pendingRolePromise = null
            promise.reject("ROLE_REQUEST_FAILED", e.message, e)
        }
    }

    /**
     * Opens Android System Default Apps / Role settings so the user can
     * change or disable VoiceShield as the Call Screening app.
     */
    @ReactMethod
    fun openCallScreeningSettings(promise: Promise) {
        try {
            val act = reactContext.currentActivity
            if (act == null) {
                promise.reject("NO_ACTIVITY", "Cannot open settings without foreground activity")
                return
            }

            pendingSettingsPromise = promise
            val defaultAppsIntent = Intent(Settings.ACTION_MANAGE_DEFAULT_APPS_SETTINGS)
            if (defaultAppsIntent.resolveActivity(reactContext.packageManager) != null) {
                act.startActivityForResult(defaultAppsIntent, REQUEST_CODE_SETTINGS)
            } else {
                val appDetailsIntent = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                    data = Uri.parse("package:" + reactContext.packageName)
                }
                act.startActivityForResult(appDetailsIntent, REQUEST_CODE_SETTINGS)
            }
        } catch (e: Exception) {
            pendingSettingsPromise = null
            promise.reject("SETTINGS_FAILED", e.message, e)
        }
    }

    /**
     * Retrieves a bundled demo audio sample and copies it to local cache,
     * returning a valid file:// URI with metadata.
     */
    @ReactMethod
    fun getDemoAudioSample(sampleType: String, promise: Promise) {
        try {
            val assetFileName = when (sampleType) {
                "synthetic" -> "synthetic_sample.wav"
                "benign" -> "benign_sample.wav"
                "short" -> "short_sample.wav"
                else -> {
                    promise.reject("INVALID_SAMPLE_TYPE", "Unknown sample type: $sampleType")
                    return
                }
            }

            val assetPath = "demo_samples/$assetFileName"
            val destFile = File(reactContext.cacheDir, "demo_$assetFileName")

            reactContext.assets.open(assetPath).use { input ->
                destFile.outputStream().use { output ->
                    input.copyTo(output)
                }
            }

            if (!destFile.exists() || destFile.length() == 0L) {
                promise.reject("SAMPLE_UNAVAILABLE", "Demo audio sample is unavailable.")
                return
            }

            val result = Arguments.createMap().apply {
                putString("uri", "file://" + destFile.absolutePath)
                putString("name", assetFileName)
                putString("type", "audio/wav")
                putDouble("size", destFile.length().toDouble())
            }
            promise.resolve(result)
        } catch (e: Exception) {
            promise.reject("SAMPLE_ERROR", "Demo audio sample is unavailable: ${e.message}", e)
        }
    }

    /**
     * Prompts the user to select an audio file (WAV, FLAC, OGG, MP3, M4A)
     * from their device via Android's document picker.
     */
    @ReactMethod
    fun pickAudioFile(promise: Promise) {
        try {
            val act = reactContext.currentActivity
            if (act == null) {
                promise.reject("NO_ACTIVITY", "Cannot open file picker without foreground activity")
                return
            }

            pendingPickPromise = promise
            val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                addCategory(Intent.CATEGORY_OPENABLE)
                type = "audio/*"
                putExtra(
                    Intent.EXTRA_MIME_TYPES,
                    arrayOf(
                        "audio/wav", "audio/x-wav",
                        "audio/flac", "audio/x-flac",
                        "audio/ogg", "application/ogg",
                        "audio/mpeg", "audio/mp3",
                        "audio/mp4", "audio/x-m4a"
                    )
                )
            }
            act.startActivityForResult(intent, REQUEST_CODE_PICK_AUDIO)
        } catch (e: Exception) {
            pendingPickPromise = null
            promise.reject("PICKER_LAUNCH_FAILED", e.message, e)
        }
    }

    private fun handlePickedAudio(uri: Uri): WritableMap {
        var displayName = "audio_file.wav"
        var size = 0L

        reactContext.contentResolver.query(uri, null, null, null, null)?.use { cursor ->
            if (cursor.moveToFirst()) {
                val nameIndex = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                if (nameIndex != -1) {
                    val name = cursor.getString(nameIndex)
                    if (!name.isNullOrBlank()) displayName = name
                }
                val sizeIndex = cursor.getColumnIndex(OpenableColumns.SIZE)
                if (sizeIndex != -1) {
                    size = cursor.getLong(sizeIndex)
                }
            }
        }

        var mimeType = reactContext.contentResolver.getType(uri)
        if (mimeType.isNullOrBlank()) {
            val lower = displayName.lowercase()
            mimeType = when {
                lower.endsWith(".wav") -> "audio/wav"
                lower.endsWith(".flac") -> "audio/flac"
                lower.endsWith(".ogg") -> "audio/ogg"
                lower.endsWith(".mp3") -> "audio/mpeg"
                lower.endsWith(".m4a") -> "audio/mp4"
                else -> "audio/*"
            }
        }

        val safeName = "picked_" + System.currentTimeMillis() + "_" + displayName.replace("[^a-zA-Z0-9._-]".toRegex(), "_")
        val destFile = File(reactContext.cacheDir, safeName)
        reactContext.contentResolver.openInputStream(uri)?.use { input ->
            destFile.outputStream().use { output ->
                input.copyTo(output)
            }
        }

        if (size <= 0L) {
            size = destFile.length()
        }

        return Arguments.createMap().apply {
            putString("uri", "file://" + destFile.absolutePath)
            putString("name", displayName)
            putString("type", mimeType)
            putDouble("size", size.toDouble())
        }
    }

    /**
     * Local-only test notification to verify channel, priority, and permissions on device.
     * Strictly creates NO call, session, incident, or risk records and affects NO dashboard stats.
     */
    @ReactMethod
    fun testSecurityNotification(promise: Promise) {
        try {
            CallNotificationHelper.showTestNotification(reactContext)
            promise.resolve(true)
        } catch (e: Exception) {
            promise.reject("NOTIFICATION_TEST_FAILED", e.message, e)
        }
    }

    @ReactMethod
    fun postSecurityNotification(title: String, message: String, isHighPriority: Boolean, promise: Promise) {
        try {
            CallNotificationHelper.showNotification(reactContext, title, message, isHighPriority)
            promise.resolve(true)
        } catch (e: Exception) {
            promise.reject("NOTIFICATION_POST_FAILED", e.message, e)
        }
    }

    @ReactMethod
    fun hasContactsPermission(promise: Promise) {
        try {
            val granted = reactContext.checkSelfPermission("android.permission.READ_CONTACTS") ==
                PackageManager.PERMISSION_GRANTED
            promise.resolve(granted)
        } catch (e: Exception) {
            promise.reject("CONTACTS_CHECK_FAILED", e.message, e)
        }
    }

    @ReactMethod
    fun requestContactsPermission(promise: Promise) {
        try {
            // READ_CONTACTS is a normal permission granted at install time on API 29+ for screening.
            // For runtime grant on API 23+, we check current state and inform the user.
            val granted = reactContext.checkSelfPermission("android.permission.READ_CONTACTS") ==
                PackageManager.PERMISSION_GRANTED
            promise.resolve(granted)
        } catch (e: Exception) {
            promise.reject("CONTACTS_REQUEST_FAILED", e.message, e)
        }
    }

    @ReactMethod
    fun getRecentScreenedCalls(promise: Promise) {
        try {
            val records = storage.getRecentEvents()
            val array: WritableArray = Arguments.createArray()
            records.forEach { record ->
                array.pushMap(recordToWritableMap(record))
            }
            promise.resolve(array)
        } catch (e: Exception) {
            promise.reject("STORAGE_LOAD_FAILED", e.message, e)
        }
    }

    @ReactMethod
    fun clearScreenedCalls(promise: Promise) {
        try {
            storage.clearEvents()
            promise.resolve(true)
        } catch (e: Exception) {
            promise.reject("STORAGE_CLEAR_FAILED", e.message, e)
        }
    }

    @ReactMethod
    fun addListener(eventName: String) {
        // Required for RN built-in Event Emitter Calls
    }

    @ReactMethod
    fun removeListeners(count: Int) {
        // Required for RN built-in Event Emitter Calls
    }

    private fun recordToWritableMap(record: ScreenedCallRecord): WritableMap {
        return Arguments.createMap().apply {
            putString("eventId", record.eventId)
            putString("incidentId", record.eventId)
            putString("phoneNumber", record.callerMasked)
            putString("carrierVerification", record.verificationStatus)
            putString("status", "finalized")
            putDouble("timestamp", record.timestamp.toDouble())
            putString("callerMasked", record.callerMasked)
            putString("callerName", record.callerName)
            putString("callerHash", record.callerHash)
            putString("contactStatus", record.contactStatus)
            putString("verificationStatus", record.verificationStatus)
            putInt("riskScore", record.riskScore)
            putString("riskState", record.riskState)
            putString("decision", record.decision)
            putString("riskLevel", record.riskLevel)
            putString("warningType", record.warningType)
            putString("category", record.category)
            putString("explanation", record.explanation)
            putDouble("screeningLatencyMs", record.screeningLatencyMs.toDouble())
            putString("source", record.source)
            putString("audioAnalysisStatus", record.audioAnalysisStatus)
            putString("callDirection", record.callDirection)
            val reasons: WritableArray = Arguments.createArray()
            record.reasonCodes.forEach { reasons.pushString(it) }
            putArray("reasonCodes", reasons)
        }
    }

    private fun sendCallScreenedEvent(record: ScreenedCallRecord) {
        if (!reactContext.hasActiveReactInstance()) return
        val map = recordToWritableMap(record)
        val emitter = reactContext.getJSModule(DeviceEventManagerModule.RCTDeviceEventEmitter::class.java)
        emitter.emit(EVENT_CALL_SCREENED, map)
        emitter.emit("CALL_SCREENING_EVENT", map)
    }

    private fun sendRoleStatusChanged(isHeld: Boolean) {
        if (!reactContext.hasActiveReactInstance()) return
        val map = Arguments.createMap().apply {
            putBoolean("isRoleHeld", isHeld)
        }
        reactContext
            .getJSModule(DeviceEventManagerModule.RCTDeviceEventEmitter::class.java)
            .emit(EVENT_ROLE_STATUS_CHANGED, map)
    }
}
