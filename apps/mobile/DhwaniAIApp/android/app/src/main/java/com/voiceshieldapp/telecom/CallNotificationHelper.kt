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
    private const val CHANNEL_NAME = "Dhwani AI Call Screening"
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

    fun showNotification(
        context: Context,
        title: String,
        message: String,
        isHighPriority: Boolean = false,
        notificationId: Int = 1001
    ) {
        try {
            ensureChannel(context)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                if (ContextCompat.checkSelfPermission(
                        context,
                        "android.permission.POST_NOTIFICATIONS"
                    ) != PackageManager.PERMISSION_GRANTED
                ) {
                    return
                }
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

            val smallIconRes = R.drawable.ic_notification

            val priority = if (isHighPriority) NotificationCompat.PRIORITY_HIGH else NotificationCompat.PRIORITY_DEFAULT

            val notification = NotificationCompat.Builder(context, CHANNEL_ID)
                .setSmallIcon(smallIconRes)
                .setColor(0xFF00E5FF.toInt())
                .setContentTitle(title)
                .setContentText(message)
                .setStyle(NotificationCompat.BigTextStyle().bigText(message))
                .setPriority(priority)
                .setAutoCancel(true)
                .setContentIntent(pendingIntent)
                .build()

            val notificationManager =
                context.getSystemService(Context.NOTIFICATION_SERVICE) as? NotificationManager
            notificationManager?.notify(notificationId, notification)
        } catch (e: Exception) {
            // Safe fallback
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

            val callerDisplay = evaluation.callerName ?: evaluation.maskedCaller
            val isElevated = evaluation.riskState == "suspicious" ||
                             evaluation.riskState == "high" ||
                             evaluation.riskState == "critical"

            val title: String
            val message: String
            val priority: Int

            priority = NotificationCompat.PRIORITY_HIGH
            if (isElevated) {
                title = "Dhwani AI Security Alert"
                val riskUpper = evaluation.riskState.uppercase()
                message = "Incoming call from $callerDisplay · Risk: $riskUpper. Review call security."
            } else {
                title = "Dhwani AI"
                message = "Incoming call detected: $callerDisplay · Risk: LOW. Tap to view security details."
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

            // Use dedicated Dhwani AI monochrome vector small icon
            val smallIconRes = R.drawable.ic_notification

            val notification = NotificationCompat.Builder(context, CHANNEL_ID)
                .setSmallIcon(smallIconRes)
                .setColor(0xFF00E5FF.toInt())
                .setContentTitle(title)
                .setContentText(message)
                .setStyle(NotificationCompat.BigTextStyle().bigText(message))
                .setPriority(priority)
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

    /**
     * Local-only test notification to verify channel, priority, and permissions on device.
     * Strictly creates NO call, session, incident, or risk records and affects NO dashboard stats.
     */
    fun showTestNotification(context: Context) {
        try {
            ensureChannel(context)

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                if (ContextCompat.checkSelfPermission(
                        context,
                        "android.permission.POST_NOTIFICATIONS"
                    ) != PackageManager.PERMISSION_GRANTED
                ) {
                    return
                }
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

            val smallIconRes = R.drawable.ic_notification

            val title = "Dhwani AI Security Test"
            val message = "Notification channel and alert delivery verified successfully. (Test only — no calls or stats affected)"

            val notification = NotificationCompat.Builder(context, CHANNEL_ID)
                .setSmallIcon(smallIconRes)
                .setColor(0xFF00E5FF.toInt())
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
            notificationManager?.notify(99999, notification)
        } catch (e: Exception) {
            // Notification failure must not crash
        }
    }
}
