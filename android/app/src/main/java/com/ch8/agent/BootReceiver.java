package com.ch8.agent;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;

public class BootReceiver extends BroadcastReceiver {

    @Override
    public void onReceive(Context context, Intent intent) {
        if (Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())) {
            SharedPreferences prefs = context.getSharedPreferences("ch8_prefs",
                    Context.MODE_PRIVATE);

            boolean configured = prefs.getBoolean("configured", false);
            if (!configured) return;

            String token = prefs.getString("token", "");

            Intent serviceIntent = new Intent(context, DaemonService.class);
            serviceIntent.setAction("START");
            serviceIntent.putExtra("token", token);

            if (Build.VERSION.SDK_INT >= 26) {
                context.startForegroundService(serviceIntent);
            } else {
                context.startService(serviceIntent);
            }
        }
    }
}
