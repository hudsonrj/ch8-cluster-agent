[app]
title = CH8 Agent
package.name = ch8agent
package.domain = com.ch8

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,sh
source.include_patterns = connect/**/*.py,agents/**/*.py

version = 1.0.0

requirements = python3,kivy,httpx,psutil,pydantic,certifi,httpcore,idna,sniffio,anyio,h11

orientation = portrait
fullscreen = 0

# Android specific
android.permissions = INTERNET,ACCESS_NETWORK_STATE,FOREGROUND_SERVICE,WAKE_LOCK,RECEIVE_BOOT_COMPLETED,POST_NOTIFICATIONS
android.api = 34
android.minapi = 24
android.ndk = 25b
android.accept_sdk_license = True

# App icon and presplash
# icon.filename = %(source.dir)s/icon.png
# presplash.filename = %(source.dir)s/presplash.png

# Build
android.arch = arm64-v8a
# android.archs = arm64-v8a,armeabi-v7a

# Service for background daemon
services = CH8Daemon:service_daemon.py:foreground

# Dark theme
android.theme = @android:style/Theme.DeviceDefault

[buildozer]
log_level = 2
warn_on_root = 0
