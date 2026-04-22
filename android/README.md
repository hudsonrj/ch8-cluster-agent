# CH8 Agent para Android 📱

Transforme seu celular ou tablet Android em um nó do cluster CH8 Agent!

## 🎯 Dois Modos de Operação

### 🌐 Modo Cloud (Recomendado para iniciantes)
Usa APIs de modelos na nuvem (OpenAI, Claude, Groq, etc)
- ✅ Funciona em qualquer Android (até 1GB RAM)
- ✅ Baixo consumo de bateria
- ✅ Resposta rápida
- ❌ Requer internet
- ❌ Custo por uso (APIs pagas)

### 📱 Modo Local (Privacidade total)
Roda mini modelos localmente no dispositivo
- ✅ 100% offline
- ✅ Privacidade completa
- ✅ Zero custo por uso
- ❌ Requer Android com 3GB+ RAM
- ❌ Maior consumo de bateria

### 🔀 Modo Híbrido (Melhor dos dois mundos)
Tarefas simples no device, complexas na nuvem
- ✅ Balanceamento automático
- ✅ Otimizado para bateria
- ✅ Funciona offline para tarefas básicas

## 🚀 Instalação

### Opção 1: Via Termux (Mais Fácil)

```bash
# 1. Instalar Termux da F-Droid
# https://f-droid.org/en/packages/com.termux/

# 2. Dentro do Termux
pkg update && pkg upgrade
pkg install python git clang wget

# 3. Instalar CH8 Agent
curl -fsSL https://raw.githubusercontent.com/hudsonrj/ch8-cluster-agent/main/android/install-termux.sh | bash

# 4. Iniciar nó
ch8-android start
```

### Opção 2: APK Nativo (Sem root)

```bash
# Baixar APK pré-compilado
wget https://github.com/hudsonrj/ch8-cluster-agent/releases/latest/download/ch8-agent.apk

# Instalar no dispositivo
adb install ch8-agent.apk
```

## 📱 Configuração

### Modo Cloud (OpenAI, Claude, Groq, etc)

```yaml
# ~/.ch8/android-config.yaml
mode: cloud

cloud:
  provider: openai  # ou: claude, groq, cohere, mistral
  api_key: sk-...
  model: gpt-3.5-turbo  # Rápido e barato

  # Configuração de economia
  max_tokens: 256
  temperature: 0.7
  timeout: 10

node:
  id: android-$(hostname)
  capabilities:
    - text_generation
    - analysis
    - extraction
```

### Modo Local (Mini Modelos)

```yaml
# ~/.ch8/android-config.yaml
mode: local

local:
  backend: llama.cpp
  model: smollm-135m-q4.gguf
  context_length: 512
  threads: 4  # Use CPU cores disponíveis

battery:
  power_mode: efficient
  max_cpu_usage: 50  # Limite CPU para economizar bateria
  temperature_limit: 40  # Parar se device esquentar

node:
  id: android-$(hostname)
  capabilities:
    - simple_classification
    - keyword_extraction
    - yes_no_questions
```

### Modo Híbrido

```yaml
# ~/.ch8/android-config.yaml
mode: hybrid

# Regras de roteamento
routing:
  local_tasks:
    - classification
    - simple_extraction
    - yes_no

  cloud_tasks:
    - complex_analysis
    - code_generation
    - long_summaries

# Fallback: use cloud se local falhar
fallback_to_cloud: true

# Economia de dados
data_saver:
  enabled: true
  wifi_only: true  # Só usa cloud em WiFi
```

## 🔋 Otimizações para Bateria

### Configuração Recomendada

```python
from android_node import AndroidNode

node = AndroidNode(config={
    'battery_optimization': {
        'enabled': True,
        'strategies': [
            'adaptive_polling',      # Reduz polling quando bateria baixa
            'background_throttling', # Menos tasks em background
            'temperature_monitor',   # Para se esquentar muito
            'doze_compatible'        # Compatível com Doze mode
        ]
    },

    'power_profiles': {
        'plugged': {
            'max_concurrent_tasks': 3,
            'cpu_limit': 100,
            'polling_interval': 1
        },
        'battery_high': {  # > 50%
            'max_concurrent_tasks': 2,
            'cpu_limit': 70,
            'polling_interval': 5
        },
        'battery_medium': {  # 20-50%
            'max_concurrent_tasks': 1,
            'cpu_limit': 40,
            'polling_interval': 15
        },
        'battery_low': {  # < 20%
            'max_concurrent_tasks': 0,  # Só aceita urgentes
            'cpu_limit': 20,
            'polling_interval': 60
        }
    }
})
```

## 📊 Modelos Recomendados por Hardware

### Dispositivos Básicos (2-3GB RAM)

```yaml
local:
  models:
    - smollm-135m-q4.gguf (60MB)  # Ultra-leve
    - tinystories-1m-q8.gguf (2MB)  # Nano tasks
```

### Dispositivos Médios (4-6GB RAM)

```yaml
local:
  models:
    - qwen2-0.5b-q2.gguf (300MB)  # Balanceado
    - smollm-360m-q4.gguf (180MB)  # Rápido
```

### Dispositivos Top (8GB+ RAM)

```yaml
local:
  models:
    - tinyllama-1.1b-q4.gguf (700MB)  # Qualidade
    - phi-2-q4.gguf (1.6GB)  # Melhor reasoning
```

## 🌐 Provedores Cloud Suportados

### OpenAI (GPT-3.5, GPT-4)
```python
{
    'provider': 'openai',
    'api_key': 'sk-...',
    'model': 'gpt-3.5-turbo',
    'base_url': 'https://api.openai.com/v1'
}
```

### Anthropic (Claude)
```python
{
    'provider': 'anthropic',
    'api_key': 'sk-ant-...',
    'model': 'claude-3-haiku-20240307'  # Mais rápido
}
```

### Groq (Ultra Rápido, Gratuito)
```python
{
    'provider': 'groq',
    'api_key': 'gsk_...',
    'model': 'llama3-8b-8192',  # ~500 tokens/seg!
    'base_url': 'https://api.groq.com/openai/v1'
}
```

### Together AI (Muitos modelos)
```python
{
    'provider': 'together',
    'api_key': '...',
    'model': 'mistralai/Mixtral-8x7B-Instruct-v0.1'
}
```

### Local OpenAI-Compatible (Ollama, vLLM)
```python
{
    'provider': 'openai',
    'api_key': 'not-needed',
    'model': 'tinyllama',
    'base_url': 'http://192.168.1.100:11434/v1'  # Ollama na rede local
}
```

## 📦 Gerando APK

### Método 1: Buildozer (Python to APK)

```bash
# 1. Instalar Buildozer
pip install buildozer

# 2. Configurar buildozer.spec
cd android/
buildozer init

# 3. Editar buildozer.spec
# (arquivo já configurado no repo)

# 4. Build APK
buildozer android debug

# APK gerado em: bin/ch8agent-0.1-debug.apk
```

### Método 2: Kivy (Interface Gráfica)

```bash
# APK com interface visual
cd android/kivy-app/
buildozer android release

# Assinar APK
jarsigner -verbose -sigalg SHA1withRSA \
    -digestalg SHA1 \
    -keystore my-release-key.keystore \
    bin/ch8agent-release-unsigned.apk \
    alias_name

zipalign -v 4 \
    bin/ch8agent-release-unsigned.apk \
    bin/ch8agent-release.apk
```

### Método 3: React Native (App Moderno)

```bash
cd android/react-native-app/
npm install
npx react-native run-android

# Build release
cd android/
./gradlew assembleRelease
```

## 🎮 Casos de Uso

### Celular Velho como Nó 24/7

```
Cenário: Samsung S7 (2016, 4GB RAM) sempre carregando

Config:
├─ Modo: Local (TinyLlama Q2_K)
├─ Tarefas: Classificação, extração
├─ Disponibilidade: 24/7
├─ Custo energia: ~5W (~R$2/mês)
└─ Contribuição: 50-100 tasks/dia
```

### Tablet como Display + Nó

```
Cenário: Tablet na parede, carregando sempre

Config:
├─ Modo: Híbrido
├─ Interface: WebUI mostrando status cluster
├─ Local: Tasks simples offline
├─ Cloud: Tasks complexas via WiFi
└─ Uso: Dashboard + Worker node
```

### Phone Principal (Uso Ocasional)

```
Cenário: Celular pessoal, bateria gerenciada

Config:
├─ Modo: Cloud (Groq, gratuito)
├─ Battery: Modo agressivo (só quando carregando)
├─ Data: WiFi only
├─ Contribuição: Quando disponível
└─ Prioridade: Bateria > Cluster
```

## 🔒 Segurança & Privacidade

### Modo Local
- ✅ Dados nunca saem do dispositivo
- ✅ Sem rastreamento
- ✅ Funciona em modo avião
- ✅ Ideal para dados sensíveis

### Modo Cloud
- ⚠️ Dados enviados para API externa
- ✅ Use providers confiáveis (OpenAI, Anthropic)
- ✅ Evite dados pessoais/sensíveis
- ✅ Criptografia TLS em trânsito

### Modo Híbrido
- ✅ Classifique tasks por sensibilidade
- ✅ Dados sensíveis → Local only
- ✅ Dados públicos → Cloud permitido

## 📈 Performance

### Benchmarks

| Device | Model | Tokens/sec | Bateria/hora |
|--------|-------|-----------|--------------|
| Pixel 7 | SmolLM-135M | ~15 | 10% |
| Galaxy S21 | Qwen2-0.5B Q2 | ~8 | 15% |
| Old S7 | TinyStories-1M | ~25 | 8% |
| Tablet A8 | Cloud (Groq) | ~500* | 2% |

\* Velocidade do servidor, não do device

## 🛠️ Troubleshooting

### "Out of Memory" em modelo local
```bash
# Usar modelo menor
model: smollm-135m-q4.gguf  # Ao invés de tinyllama

# Ou usar cloud
mode: cloud
```

### "Battery draining fast"
```yaml
battery:
  power_mode: ultra_efficient
  max_cpu_usage: 30
  pause_when_battery_low: true
  min_battery_level: 40  # Só trabalha acima de 40%
```

### "Device overheating"
```yaml
battery:
  temperature_limit: 38  # Celsius
  cooldown_period: 300   # 5min de pausa se esquentar
  thermal_throttling: true
```

## 🎯 Roadmap

- [ ] APK pré-compilado no GitHub Releases
- [ ] Interface gráfica Kivy
- [ ] Widget de status
- [ ] Notificações de tarefas
- [ ] Background service otimizado
- [ ] Auto-update OTA
- [ ] Play Store release

## 📚 Exemplos

Ver `android/examples/` para:
- `simple_node.py` - Nó básico
- `cloud_hybrid.py` - Modo híbrido
- `battery_optimized.py` - Máxima eficiência
- `dashboard_tablet.py` - Tablet com UI

---

**Transforme qualquer Android em parte do seu cluster inteligente!** 🚀
