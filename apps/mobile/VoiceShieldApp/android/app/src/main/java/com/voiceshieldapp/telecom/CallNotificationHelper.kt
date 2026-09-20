package com.voiceshieldapp.telecom

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import com.voiceshieldapp.MainActivity
import com.voiceshieldapp.R

/**
 * Native Android notification helper for CallScreeningService.
 * Uses NotificationManager and NotificationCompat with heads-up display.
 */
object CallNotificationHelper {

    const val CHANNEL_ID = "voiceshield_call_screening"
    private const val CHANNEL_NAME = "VoiceShield Call Screening"
    private const val CHANNEL_DESC = "Security alerts for incoming screened calls"

    fun ensureChannel(context: Context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val notificationManager =
                context.getSystemService(Context.NOTIFICATION_SERVICE) as? NotificationManager ?: return
            val existing = notificationManager.getNotificationChannel(CHANNEL_ID)
            if (existing == null) {
                val channel = NotificationChannel(
                    CHANNEL_ID,
                    CHANNEL_NAME,
                    NotificationManager.IMPORTANCE_HIGH
                ).apply {
                    description = CHANNEL_DESC
                    enableVibration(true)
                    setShowBadge(true)
                }
                notificationManager.createNotificationChannel(channel)
            }
        }
    }

    fun showScreeningNotification(context: Context, evaluation: EvaluationResult) {
        try {
            ensureChannel(context)

            // Android 13+ (API 33) runtime notification permission check
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                if (ContextCompat.checkSelfPermission(
                        context,
                        "android.permission.POST_NOTIFICATIONS"
                    ) != PackageManager.PERMISSION_GRANTED
                ) {
                    // Cannot post notification without permission; graceful degradation
                    return
                }
            }

            val (title, message) = when (evaluation.warningType) {
                WarningType.VERIFICATION_FAILED -> Pair(
                    "VoiceShield Warning",
                    "Caller verification failed for ${evaluation.maskedCaller} — exercise caution"
                )
                WarningType.UNVERIFIED_CALLER -> Pair(
                    "VoiceShield Security Check",
                    "Caller could not be verified by carrier for ${evaluation.maskedCaller}"
                )
                WarningType.RESTRICTED_NUMBER -> Pair(
                    "VoiceShield Security Check",
                    "Incoming call from Restricted/Private caller"
                )
                WarningType.BLOCKLIST_MATCH -> Pair(
                    "VoiceShield Blocked Call",
                    "Blocked incoming call from ${evaluation.maskedCaller}"
                )
                WarningType.NONE -> Pair(
                    "VoiceShield Call Security",
                    "Incoming call detected from ${evaluation.maskedCaller}"
                )
            }

            val launchIntent = Intent(context, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            }
            val pendingIntent = PendingIntent.getActivity(
                context,
                0,
                launchIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )

            // Use launcher icon as fallback small icon
            val smallIconRes = context.applicationInfo.icon.takeIf { it != 0 }
                ?: android.R.drawable.ic_dialog_info

            val notification = NotificationCompat.Builder(context, CHANNEL_ID)
                .setSmallIcon(smallIconRes)
                .setContentTitle(title)
                .setContentText(message)
                .setStyle(NotificationCompat.BigTextStyle().bigText(message))
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setCategory(NotificationCompat.CATEGORY_CALL)
                .setAutoCancel(true)
                .setContentIntent(pendingIntent)
                .build()

            val notificationManager =
                context.getSystemService(Context.NOTIFICATION_SERVICE) as? NotificationManager
            val notificationId = (evaluation.timestamp % 100000).toInt()
            notificationManager?.notify(notificationId, notification)
        } catch (e: Exception) {
            // Notification failure must never crash CallScreeningService
        }
    }
}
