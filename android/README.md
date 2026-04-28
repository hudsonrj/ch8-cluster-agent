# CH8 Agent - Android App

Native Android application for the CH8 distributed AI cluster.

## Features

- **Foreground Service**: Keeps the daemon running in background with wake lock
- **Auto-start on Boot**: Automatically reconnects to your CH8 network
- **Local Dashboard**: WebView showing the orchestrator UI at localhost:7879
- **Token Setup**: Simple first-time setup with network token

## Building

### Prerequisites
- Android Studio Arctic Fox or later
- JDK 11+
- Android SDK 34

### Steps

1. Open the `android/` folder in Android Studio
2. Sync Gradle
3. Build APK: `Build > Build Bundle(s) / APK(s) > Build APK`
4. Install on device: `adb install app/build/outputs/apk/release/app-release.apk`

## Architecture

The app uses a foreground service to run Python (via Termux shared libraries or Chaquopy):
- `DaemonService` — Foreground service that runs `connect.daemon`
- `MainActivity` — WebView showing the local orchestrator dashboard
- `BootReceiver` — Starts the daemon service on device boot

## Alternative: Termux

For users who prefer a terminal experience:

```bash
curl -fsSL https://raw.githubusercontent.com/hudsonrj/ch8-cluster-agent/master/scripts/install-android.sh | bash
```

Requires [Termux from F-Droid](https://f-droid.org/en/packages/com.termux/).
