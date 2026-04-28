package com.ch8.agent;

import android.content.Intent;
import android.os.Bundle;
import android.view.View;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;

import java.io.File;

public class MainActivity extends AppCompatActivity {

    private WebView webView;
    private LinearLayout setupLayout;
    private EditText tokenInput;
    private TextView statusText;
    private Button startButton, stopButton;

    private static final String PREFS = "ch8_prefs";
    private static final String KEY_TOKEN = "token";
    private static final String KEY_CONFIGURED = "configured";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        setupLayout = findViewById(R.id.setup_layout);
        webView = findViewById(R.id.webview);
        tokenInput = findViewById(R.id.token_input);
        statusText = findViewById(R.id.status_text);
        startButton = findViewById(R.id.btn_start);
        stopButton = findViewById(R.id.btn_stop);

        // WebView setup for local dashboard
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        webView.setWebViewClient(new WebViewClient());

        // Check if already configured
        boolean configured = getSharedPreferences(PREFS, MODE_PRIVATE)
                .getBoolean(KEY_CONFIGURED, false);

        if (configured) {
            showDashboard();
        } else {
            showSetup();
        }

        startButton.setOnClickListener(v -> startDaemon());
        stopButton.setOnClickListener(v -> stopDaemon());

        // Request notification permission (Android 13+)
        if (android.os.Build.VERSION.SDK_INT >= 33) {
            ActivityCompat.requestPermissions(this,
                    new String[]{"android.permission.POST_NOTIFICATIONS"}, 1);
        }
    }

    private void showSetup() {
        setupLayout.setVisibility(View.VISIBLE);
        webView.setVisibility(View.GONE);

        Button connectBtn = findViewById(R.id.btn_connect);
        connectBtn.setOnClickListener(v -> {
            String token = tokenInput.getText().toString().trim();
            if (token.isEmpty()) {
                Toast.makeText(this, "Enter your network token", Toast.LENGTH_SHORT).show();
                return;
            }

            // Save token
            getSharedPreferences(PREFS, MODE_PRIVATE).edit()
                    .putString(KEY_TOKEN, token)
                    .putBoolean(KEY_CONFIGURED, true)
                    .apply();

            // Start daemon with token
            startDaemonWithToken(token);
            showDashboard();
        });
    }

    private void showDashboard() {
        setupLayout.setVisibility(View.GONE);
        webView.setVisibility(View.VISIBLE);

        // Load local orchestrator dashboard (port 7879)
        webView.loadUrl("http://127.0.0.1:7879/");

        updateStatus();
    }

    private void startDaemon() {
        String token = getSharedPreferences(PREFS, MODE_PRIVATE)
                .getString(KEY_TOKEN, "");
        startDaemonWithToken(token);
    }

    private void startDaemonWithToken(String token) {
        Intent serviceIntent = new Intent(this, DaemonService.class);
        serviceIntent.putExtra("token", token);
        serviceIntent.setAction("START");

        if (android.os.Build.VERSION.SDK_INT >= 26) {
            startForegroundService(serviceIntent);
        } else {
            startService(serviceIntent);
        }

        statusText.setText("Status: Running");
        statusText.setTextColor(0xFF4CAF50);
        Toast.makeText(this, "CH8 Agent started", Toast.LENGTH_SHORT).show();
    }

    private void stopDaemon() {
        Intent serviceIntent = new Intent(this, DaemonService.class);
        serviceIntent.setAction("STOP");
        startService(serviceIntent);

        statusText.setText("Status: Stopped");
        statusText.setTextColor(0xFFF44336);
        Toast.makeText(this, "CH8 Agent stopped", Toast.LENGTH_SHORT).show();
    }

    private void updateStatus() {
        boolean running = DaemonService.isRunning;
        statusText.setText(running ? "Status: Running" : "Status: Stopped");
        statusText.setTextColor(running ? 0xFF4CAF50 : 0xFFF44336);
    }

    @Override
    public void onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }
}
