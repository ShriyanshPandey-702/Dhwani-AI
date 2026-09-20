package com.voiceshieldapp.telecom

import android.app.Activity
import android.app.role.RoleManager
import android.content.Context
import android.content.Intent
import android.os.Build
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
import java.lang.ref.WeakReference

/**
 * React Native native module bridging Android Telecom CallScreeningService
 * and RoleManager to the JavaScript layer.
 */
class VoiceShieldCallScreeningModule(private val reactContext: ReactApplicationContext) :
    ReactContextBaseJavaModule(reactContext) {

    companion object {
        const val MODULE_NAME = "VoiceShieldCallScreening"
        const val EVENT_CALL_SCREENED = "onIncomingCallScreened"
        const val EVENT_ROLE_STATUS_CHANGED = "onRoleStatusChanged"
        private const val REQUEST_CODE_ROLE = 4040

        private var currentInstance: WeakReference<VoiceShieldCallScreeningModule>? = null

        /**
         * Called by VoiceShieldCallScreeningService when a call is screened.
         * Dispatches event to active JS environment.
         */
        fun notifyCallScreened(record: ScreenedCallRecord) {
            currentInstance?.get()?.sendCallScreenedEvent(record)
        }
    }

    private var pendingRolePromise: Promise? = null
    private val storage = CallScreeningStorage(reactContext)

    private val activityEventListener: ActivityEventListener = object : BaseActivityEventListener() {
        override fun onActivityResult(
            activity: Activity,
            requestCode: Int,
            resultCode: Int,
            data: Intent?
        ) {
            if (requestCode == REQUEST_CODE_ROLE) {
                val promise = pendingRolePromise
                pendingRolePromise = null

                val isHeld = checkIsRoleHeld()
                val result = Arguments.createMap().apply {
                    putBoolean("granted", isHeld)
                    putBoolean("alreadyHeld", false)
                }
                promise?.resolve(result)
                sendRoleStatusChanged(isHeld)
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
            promise.resolve(checkIsRoleHeld())
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

    @ReactMethod
    fun getRecentScreenedCalls(promise: Promise) {
        try {
            val records = storage.getRecentEvents()
            val array: WritableArray = Arguments.createArray()
            records.forEach { record ->
                val map: WritableMap = Arguments.createMap().apply {
                    putString("eventId", record.eventId)
                    putDouble("timestamp", record.timestamp.toDouble())
                    putString("callerMasked", record.callerMasked)
                    putString("callerHash", record.callerHash)
                    putString("verificationStatus", record.verificationStatus)
                    putString("decision", record.decision)
                    putString("riskLevel", record.riskLevel)
                    putString("warningType", record.warningType)

                    val reasons: WritableArray = Arguments.createArray()
                    record.reasonCodes.forEach { reasons.pushString(it) }
                    putArray("reasonCodes", reasons)
                }
                array.pushMap(map)
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

    private fun sendCallScreenedEvent(record: ScreenedCallRecord) {
        if (!reactContext.hasActiveReactInstance()) return
        val map: WritableMap = Arguments.createMap().apply {
            putString("eventId", record.eventId)
            putDouble("timestamp", record.timestamp.toDouble())
            putString("callerMasked", record.callerMasked)
            putString("callerHash", record.callerHash)
            putString("verificationStatus", record.verificationStatus)
            putString("decision", record.decision)
            putString("riskLevel", record.riskLevel)
            putString("warningType", record.warningType)
            val reasons: WritableArray = Arguments.createArray()
            record.reasonCodes.forEach { reasons.pushString(it) }
            putArray("reasonCodes", reasons)
        }
        reactContext
            .getJSModule(DeviceEventManagerModule.RCTDeviceEventEmitter::class.java)
            .emit(EVENT_CALL_SCREENED, map)
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
