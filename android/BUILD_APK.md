# Como Gerar APK do CH8 Agent para Android

Guia completo para criar o APK que pode ser instalado em qualquer Android.

## 🎯 Métodos Disponíveis

### Método 1: Via Buildozer (Recomendado)
Converte Python para APK usando Kivy/Python-for-Android.

### Método 2: Via GitHub Actions (Automático)
Build automático quando fizer push no GitHub.

### Método 3: Manual com Gradle
Para desenvolvedores Android nativos.

## 📦 Método 1: Buildozer (Local)

### Pré-requisitos

```bash
# Linux (Ubuntu/Debian)
sudo apt-get install -y \
    python3-pip \
    build-essential \
    git \
    zip \
    unzip \
    openjdk-11-jdk \
    autoconf \
    libtool \
    pkg-config \
    zlib1g-dev \
    libncurses5-dev \
    libncursesw5-dev \
    libtinfo5 \
    cmake \
    libffi-dev \
    libssl-dev

# macOS
brew install python3 openjdk@11 autoconf automake libtool pkg-config

# Instalar Buildozer
pip3 install buildozer cython
```

### Build Debug APK

```bash
cd android/

# Primeira vez (baixa Android SDK/NDK)
buildozer android debug

# Builds subsequentes (mais rápido)
buildozer android debug

# APK gerado em:
# android/bin/ch8agent-0.1.0-debug.apk
```

### Build Release APK (Assinado)

```bash
# 1. Criar keystore (primeira vez)
keytool -genkey -v \
    -keystore ch8-release-key.keystore \
    -alias ch8agent \
    -keyalg RSA \
    -keysize 2048 \
    -validity 10000

# 2. Build release
buildozer android release

# 3. Assinar APK
jarsigner -verbose \
    -sigalg SHA256withRSA \
    -digestalg SHA-256 \
    -keystore ch8-release-key.keystore \
    bin/ch8agent-0.1.0-release-unsigned.apk \
    ch8agent

# 4. Zipalign (otimizar)
zipalign -v 4 \
    bin/ch8agent-0.1.0-release-unsigned.apk \
    bin/ch8agent-0.1.0-release.apk

# APK final:
# android/bin/ch8agent-0.1.0-release.apk
```

## 🤖 Método 2: GitHub Actions (Automático)

Crie `.github/workflows/build-android.yml`:

```yaml
name: Build Android APK

on:
  push:
    branches: [ main, master ]
    tags:
      - 'v*'

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'

    - name: Install dependencies
      run: |
        pip install buildozer cython
        sudo apt-get update
        sudo apt-get install -y openjdk-11-jdk

    - name: Build APK
      run: |
        cd android
        buildozer android debug

    - name: Upload APK
      uses: actions/upload-artifact@v3
      with:
        name: ch8agent-apk
        path: android/bin/*.apk

    - name: Create Release
      if: startsWith(github.ref, 'refs/tags/')
      uses: softprops/action-gh-release@v1
      with:
        files: android/bin/*.apk
```

Agora, todo push gerará APK automaticamente!

## 🔧 Método 3: Gradle (Android Nativo)

Para desenvolvedores que preferem Android Studio:

```bash
# 1. Criar projeto Android Studio
# 2. Copiar arquivos Python para assets/
# 3. Usar Chaquopy (Python for Android)

# build.gradle
plugins {
    id 'com.android.application'
    id 'com.chaquo.python'
}

android {
    defaultConfig {
        ndk {
            abiFilters "armeabi-v7a", "arm64-v8a"
        }

        python {
            pip {
                install "aiohttp"
                install "pyyaml"
                install "structlog"
            }
        }
    }
}

# Build
./gradlew assembleDebug
# APK: app/build/outputs/apk/debug/app-debug.apk
```

## 📱 Instalar APK no Dispositivo

### Via ADB (USB Debug)

```bash
# Habilitar USB Debug no Android
# Conectar via USB

adb devices
adb install android/bin/ch8agent-0.1.0-debug.apk
```

### Via Arquivo

```bash
# Copiar APK para dispositivo
adb push android/bin/ch8agent-0.1.0-debug.apk /sdcard/Download/

# No Android:
# Abrir Files → Downloads → ch8agent.apk
# Instalar (permitir apps de fontes desconhecidas)
```

### Via QR Code

```bash
# Hospedar APK temporariamente
python3 -m http.server 8000

# No Android:
# Escanear QR code gerado
# Baixar e instalar
```

## 🎨 Adicionar Ícone e Splash Screen

### Ícone

Criar `android/icon.png` (512x512 px):

```python
# buildozer.spec
[app]
icon.filename = icon.png
```

### Splash Screen

Criar `android/presplash.png` (preferência 1280x1920 px):

```python
# buildozer.spec
[app]
presplash.filename = presplash.png
```

## 🔑 Assinar APK para Play Store

```bash
# 1. Criar keystore de produção
keytool -genkey -v \
    -keystore ch8-prod.keystore \
    -alias ch8agent \
    -keyalg RSA \
    -keysize 2048 \
    -validity 10000

# 2. Build release
buildozer android release

# 3. Assinar
jarsigner -verbose \
    -sigalg SHA256withRSA \
    -digestalg SHA-256 \
    -keystore ch8-prod.keystore \
    bin/ch8agent-*-release-unsigned.apk \
    ch8agent

# 4. Zipalign
zipalign -v 4 \
    bin/ch8agent-*-release-unsigned.apk \
    ch8agent-release.apk

# 5. Verificar assinatura
apksigner verify --print-certs ch8agent-release.apk
```

## 📦 Tamanhos de APK

| Versão | Tamanho | Inclui |
|--------|---------|--------|
| Mínima | ~15MB | Python + código CH8 |
| Com Kivy UI | ~25MB | + interface gráfica |
| Com llama.cpp | ~40MB | + inferência local |
| Completa | ~60MB | Tudo |

## ⚡ Otimizações

### Reduzir Tamanho do APK

```python
# buildozer.spec
[app]
# Remover arquivos desnecessários
android.whitelist = *.py,*.yaml,*.json

# Habilitar ProGuard
android.enable_proguard = True

# Usar ABIs específicas
android.archs = arm64-v8a  # Apenas 64-bit
```

### Melhorar Performance

```python
# buildozer.spec
[app]
# Usar NDK mais recente
android.ndk = 25b

# Otimizações de compilação
android.add_compile_options = -O3

# Habilitar multidex
android.enable_androidx = True
```

## 🐛 Troubleshooting

### Erro: "SDK not found"
```bash
buildozer android clean
buildozer android debug
```

### Erro: "NDK build failed"
```bash
# Usar NDK específica
export ANDROID_NDK_HOME=/path/to/ndk/25b
buildozer android debug
```

### APK não instala
```bash
# Ver logs
adb logcat | grep ch8agent

# Desinstalar versão antiga
adb uninstall com.ch8agent.ch8agent
```

### App crasha ao abrir
```bash
# Ver logs de crash
adb logcat | grep -i 'AndroidRuntime\|FATAL\|crash'

# Comum: permissões faltando
# Adicionar em buildozer.spec:
# android.permissions = INTERNET,WAKE_LOCK
```

## 📋 Checklist Release

- [ ] Atualizar versão em buildozer.spec
- [ ] Testar em Android 10, 11, 12, 13
- [ ] Verificar permissões necessárias
- [ ] Otimizar tamanho do APK
- [ ] Assinar com keystore de produção
- [ ] Gerar notas de release
- [ ] Upload para GitHub Releases
- [ ] (Opcional) Submeter para Play Store

## 🎉 Publicar no Play Store

1. Criar conta Google Play Developer ($25 uma vez)
2. Criar app no Console
3. Upload APK ou AAB
4. Preencher metadados (descrição, capturas)
5. Definir classificação de conteúdo
6. Review e publicação

## 🔗 Links Úteis

- [Buildozer Docs](https://buildozer.readthedocs.io/)
- [Python for Android](https://python-for-android.readthedocs.io/)
- [Kivy Docs](https://kivy.org/doc/stable/)
- [Android Signing](https://developer.android.com/studio/publish/app-signing)
- [Play Store Guidelines](https://play.google.com/console/about/guides/)

---

**Agora você pode distribuir CH8 Agent como APK para qualquer Android!** 🚀
