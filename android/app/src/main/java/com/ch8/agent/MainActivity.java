package com.ch8.agent;

import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.view.View;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.ValueCallback;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;
import android.net.Uri;

import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;

public class MainActivity extends AppCompatActivity {

    private WebView webView;
    private LinearLayout setupLayout;
    private EditText serverInput;
    private EditText tokenInput;
    private TextView statusText;

    private static final String PREFS = "ch8_prefs";
    private static final String KEY_SERVER = "server_url";
    private static final String KEY_TOKEN = "token";
    private static final String KEY_CONFIGURED = "configured";

    // Default control server URLs (try Tailscale first, then public)
    private static final String[] DEFAULT_SERVERS = {
            "http://100.120.31.61:8081",          // Tailscale direct
            "https://control.ch8ai.com.br",       // Public HTTPS
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        setupLayout = findViewById(R.id.setup_layout);
        webView = findViewById(R.id.webview);
        serverInput = findViewById(R.id.server_input);
        tokenInput = findViewById(R.id.token_input);
        statusText = findViewById(R.id.status_text);

        // WebView setup
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        settings.setUserAgentString("CH8Agent-Android/1.0");
        webView.setWebViewClient(new CH8WebViewClient());
        webView.setWebChromeClient(new WebChromeClient());

        // Check if already configured
        SharedPreferences prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        boolean configured = prefs.getBoolean(KEY_CONFIGURED, false);

        if (configured) {
            showDashboard();
        } else {
            showSetup();
        }

        // Request notification permission (Android 13+)
        if (android.os.Build.VERSION.SDK_INT >= 33) {
            ActivityCompat.requestPermissions(this,
                    new String[]{"android.permission.POST_NOTIFICATIONS"}, 1);
        }
    }

    private void showSetup() {
        setupLayout.setVisibility(View.VISIBLE);
        webView.setVisibility(View.GONE);

        // Pre-fill with defaults
        serverInput.setText("https://control.ch8ai.com.br");
        tokenInput.setHint("tk_... (optional for view-only)");

        Button connectBtn = findViewById(R.id.btn_connect);
        connectBtn.setOnClickListener(v -> {
            String server = serverInput.getText().toString().trim();
            String token = tokenInput.getText().toString().trim();

            if (server.isEmpty()) {
                Toast.makeText(this, "Enter the control server URL", Toast.LENGTH_SHORT).show();
                return;
            }

            // Remove trailing slash
            if (server.endsWith("/")) server = server.substring(0, server.length() - 1);

            // Save config
            getSharedPreferences(PREFS, MODE_PRIVATE).edit()
                    .putString(KEY_SERVER, server)
                    .putString(KEY_TOKEN, token)
                    .putBoolean(KEY_CONFIGURED, true)
                    .apply();

            // Register device as cluster node
            if (!token.isEmpty()) {
                registerDevice(server, token);
            }

            showDashboard();
        });
    }

    private void showDashboard() {
        setupLayout.setVisibility(View.GONE);
        webView.setVisibility(View.VISIBLE);

        SharedPreferences prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        String server = prefs.getString(KEY_SERVER, DEFAULT_SERVERS[1]);

        statusText.setText("Connecting to " + server + "...");
        statusText.setVisibility(View.VISIBLE);

        webView.loadUrl(server);
    }

    private class CH8WebViewClient extends WebViewClient {
        @Override
        public void onPageFinished(WebView view, String url) {
            statusText.setVisibility(View.GONE);
            // Inject dark status bar color
            view.evaluateJavascript(
                    "document.querySelector('meta[name=theme-color]') || " +
                    "(function(){var m=document.createElement('meta');m.name='theme-color';m.content='#0a0b0f';document.head.appendChild(m)})()",
                    null);
        }

        @Override
        public void onReceivedError(WebView view, int errorCode, String description, String failingUrl) {
            // Try fallback servers
            SharedPreferences prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
            String currentServer = prefs.getString(KEY_SERVER, "");

            for (String fallback : DEFAULT_SERVERS) {
                if (!fallback.equals(currentServer)) {
                    statusText.setText("Trying " + fallback + "...");
                    statusText.setVisibility(View.VISIBLE);
                    prefs.edit().putString(KEY_SERVER, fallback).apply();
                    view.loadUrl(fallback);
                    return;
                }
            }

            // All failed — show error
            view.loadData(
                    "<html><body style='background:#0a0b0f;color:#f0f2f5;font-family:sans-serif;padding:40px;text-align:center'>" +
                    "<h2 style='color:#ff4d6a'>Connection Failed</h2>" +
                    "<p style='color:#8a93a8'>Cannot reach CH8 Control Server</p>" +
                    "<p style='color:#505868;font-size:12px'>Error: " + description + "</p>" +
                    "<p style='color:#505868;font-size:12px'>URL: " + failingUrl + "</p>" +
                    "<br><button onclick='window.location.reload()' style='background:#6366f1;color:#fff;border:none;padding:12px 24px;border-radius:8px;font-size:14px'>Retry</button>" +
                    "<br><br><button onclick='Android.resetConfig()' style='background:transparent;color:#8a93a8;border:1px solid #333;padding:8px 16px;border-radius:6px;font-size:12px'>Change Server</button>" +
                    "</body></html>",
                    "text/html", "utf-8");
        }

        @Override
        public boolean shouldOverrideUrlLoading(WebView view, String url) {
            // Keep navigation inside the app for control server
            SharedPreferences prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
            String server = prefs.getString(KEY_SERVER, "");
            if (url.startsWith(server) || url.startsWith("http://127.0.0.1") || url.startsWith("http://100.")) {
                return false; // Load in WebView
            }
            // External links open in browser
            Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
            startActivity(intent);
            return true;
        }
    }

    public void resetConfig() {
        getSharedPreferences(PREFS, MODE_PRIVATE).edit()
                .putBoolean(KEY_CONFIGURED, false)
                .apply();
        showSetup();
    }

    private void registerDevice(String server, String token) {
        new Thread(() -> {
            try {
                java.net.URL url = new java.net.URL(server + "/api/mobile/register");
                java.net.HttpURLConnection conn = (java.net.HttpURLConnection) url.openConnection();
                conn.setRequestMethod("POST");
                conn.setRequestProperty("Content-Type", "application/json");
                conn.setDoOutput(true);
                String deviceName = android.os.Build.MODEL;
                String body = "{\"token\":\"" + token + "\",\"device_name\":\"" + deviceName + "\",\"os\":\"android\"}";
                conn.getOutputStream().write(body.getBytes());
                int code = conn.getResponseCode();
                runOnUiThread(() -> {
                    if (code == 200) {
                        Toast.makeText(this, deviceName + " registered as cluster node!", Toast.LENGTH_LONG).show();
                    }
                });
            } catch (Exception e) {
                // Silent fail - device works as viewer even without registration
            }
        }).start();
    }

    @Override
    public void onBackPressed() {
        if (webView.getVisibility() == View.VISIBLE && webView.canGoBack()) {
            webView.goBack();
        } else if (webView.getVisibility() == View.VISIBLE) {
            // Double back to exit
            showSetup();
        } else {
            super.onBackPressed();
        }
    }
}
