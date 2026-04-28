package com.ch8.agent;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;

import androidx.core.app.NotificationCompat;

import java.io.BufferedReader;
import java.io.File;
import java.io.InputStreamReader;

public class DaemonService extends Service {

    private static final String CHANNEL_ID = "ch8_daemon";
    private static final int NOTIFICATION_ID = 1;

    public static boolean isRunning = false;

    private Process daemonProcess;
    private Process orchestratorProcess;
    private PowerManager.WakeLock wakeLock;

    @Override
    public void onCreate() {
        super.onCreate();
        createNotificationChannel();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent == null) return START_STICKY;

        String action = intent.getAction();
        if ("STOP".equals(action)) {
            stopDaemon();
            stopForeground(true);
            stopSelf();
            return START_NOT_STICKY;
        }

        // Start foreground notification
        startForeground(NOTIFICATION_ID, buildNotification("CH8 Agent running..."));

        // Acquire wake lock to keep CPU running
        PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "ch8:daemon");
        wakeLock.acquire();

        // Start Python daemon
        String token = intent.getStringExtra("token");
        startDaemon(token);

        isRunning = true;
        return START_STICKY;
    }

    private void startDaemon(String token) {
        try {
            String pythonPath = findPython();
            if (pythonPath == null) {
                updateNotification("Error: Python not found. Install via Termux.");
                return;
            }

            String agentDir = getFilesDir() + "/ch8-agent";

            // Clone agent if not exists
            if (!new File(agentDir + "/ch8").exists()) {
                cloneAgent(agentDir);
            }

            // Set up environment
            ProcessBuilder pb = new ProcessBuilder(
                    pythonPath, "-m", "connect.daemon"
            );
            pb.directory(new File(agentDir));
            pb.environment().put("PYTHONPATH", agentDir);
            pb.environment().put("HOME", getFilesDir().getAbsolutePath());
            if (token != null && !token.isEmpty()) {
                pb.environment().put("CH8_TOKEN", token);
            }
            pb.redirectErrorStream(true);

            daemonProcess = pb.start();

            // Start orchestrator
            ProcessBuilder orchPb = new ProcessBuilder(
                    pythonPath, agentDir + "/agents/orchestrator.py"
            );
            orchPb.directory(new File(agentDir));
            orchPb.environment().put("PYTHONPATH", agentDir);
            orchPb.environment().put("HOME", getFilesDir().getAbsolutePath());
            orchPb.redirectErrorStream(true);

            orchestratorProcess = orchPb.start();

            updateNotification("CH8 Agent connected");

        } catch (Exception e) {
            updateNotification("Error: " + e.getMessage());
        }
    }

    private void stopDaemon() {
        isRunning = false;
        if (daemonProcess != null) {
            daemonProcess.destroy();
            daemonProcess = null;
        }
        if (orchestratorProcess != null) {
            orchestratorProcess.destroy();
            orchestratorProcess = null;
        }
        if (wakeLock != null && wakeLock.isHeld()) {
            wakeLock.release();
        }
    }

    private String findPython() {
        // Termux Python paths
        String[] paths = {
                "/data/data/com.termux/files/usr/bin/python3",
                "/data/data/com.termux/files/usr/bin/python",
                getFilesDir() + "/python/bin/python3",
        };
        for (String p : paths) {
            if (new File(p).exists()) return p;
        }
        return null;
    }

    private void cloneAgent(String targetDir) {
        try {
            String git = "/data/data/com.termux/files/usr/bin/git";
            if (!new File(git).exists()) git = "git";

            ProcessBuilder pb = new ProcessBuilder(
                    git, "clone", "-b", "master",
                    "https://github.com/hudsonrj/ch8-cluster-agent.git",
                    targetDir
            );
            pb.redirectErrorStream(true);
            Process p = pb.start();
            p.waitFor();
        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL_ID, "CH8 Daemon",
                    NotificationManager.IMPORTANCE_LOW
            );
            channel.setDescription("CH8 Agent background service");
            NotificationManager nm = getSystemService(NotificationManager.class);
            nm.createNotificationChannel(channel);
        }
    }

    private Notification buildNotification(String text) {
        Intent intent = new Intent(this, MainActivity.class);
        PendingIntent pi = PendingIntent.getActivity(this, 0, intent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);

        return new NotificationCompat.Builder(this, CHANNEL_ID)
                .setContentTitle("CH8 Agent")
                .setContentText(text)
                .setSmallIcon(android.R.drawable.ic_dialog_info)
                .setContentIntent(pi)
                .setOngoing(true)
                .build();
    }

    private void updateNotification(String text) {
        NotificationManager nm = getSystemService(NotificationManager.class);
        nm.notify(NOTIFICATION_ID, buildNotification(text));
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public void onDestroy() {
        stopDaemon();
        super.onDestroy();
    }
}
