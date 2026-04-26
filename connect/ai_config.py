"""
AI provider configuration for CH8 agents.

Supports:
  - ollama    — Local Ollama (default, no API key needed)
  - openai    — OpenAI API (GPT-4o, GPT-4, etc.)
  - anthropic — Anthropic Claude API
  - bedrock   — AWS Bedrock (Claude, Titan, etc.)
  - groq      — Groq API (fast inference)
  - custom    — Any OpenAI-compatible endpoint
"""

import json
import os
from pathlib import Path
from typing import Optional

CONFIG_DIR = Path(os.environ.get("CH8_CONFIG_DIR", Path.home() / ".config" / "ch8"))
AI_CONFIG_FILE = CONFIG_DIR / "ai.json"

PROVIDERS = {
    "ollama": {
        "name": "Ollama (local)",
        "desc": "Local LLM — no API key, runs on your machine",
        "needs_key": False,
        "default_url": "http://localhost:11434",
        "default_model": "",
    },
    "openai": {
        "name": "OpenAI",
        "desc": "GPT-4o, GPT-4, GPT-3.5 — requires API key",
        "needs_key": True,
        "key_env": "OPENAI_API_KEY",
        "default_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
    },
    "anthropic": {
        "name": "Anthropic Claude",
        "desc": "Claude Opus, Sonnet, Haiku — requires API key",
        "needs_key": True,
        "key_env": "ANTHROPIC_API_KEY",
        "default_url": "https://api.anthropic.com",
        "default_model": "claude-sonnet-4-6",
        "models": ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"],
    },
    "bedrock": {
        "name": "AWS Bedrock",
        "desc": "Claude, Titan, Llama via AWS — requires AWS credentials",
        "needs_key": False,
        "key_env": "AWS_ACCESS_KEY_ID",
        "default_url": "",
        "default_model": "anthropic.claude-sonnet-4-6-v1",
        "models": ["anthropic.claude-opus-4-6-v1", "anthropic.claude-sonnet-4-6-v1", "anthropic.claude-haiku-4-5-20251001-v1"],
        "extra_config": ["aws_region"],
    },
    "groq": {
        "name": "Groq",
        "desc": "Fast inference — Llama, Mixtral — requires API key",
        "needs_key": True,
        "key_env": "GROQ_API_KEY",
        "default_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile",
        "models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"],
    },
    "custom": {
        "name": "Custom (OpenAI-compatible)",
        "desc": "Any endpoint that speaks the OpenAI chat API",
        "needs_key": False,
        "default_url": "",
        "default_model": "",
    },
}


def load_ai_config() -> dict:
    """Load saved AI provider config."""
    if AI_CONFIG_FILE.exists():
        try:
            return json.loads(AI_CONFIG_FILE.read_text())
        except Exception:
            pass
    return {}


def save_ai_config(config: dict) -> None:
    """Save AI provider config (chmod 600 — contains API keys)."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    AI_CONFIG_FILE.write_text(json.dumps(config, indent=2))
    AI_CONFIG_FILE.chmod(0o600)


def is_ai_configured() -> bool:
    """Check if AI provider has been configured."""
    config = load_ai_config()
    return bool(config.get("provider"))


def get_provider_info() -> dict:
    """Return the current provider config with env vars resolved."""
    config = load_ai_config()
    provider = config.get("provider", "ollama")
    pdef = PROVIDERS.get(provider, PROVIDERS["ollama"])

    return {
        "provider":  provider,
        "name":      pdef["name"],
        "api_key":   config.get("api_key") or os.environ.get(pdef.get("key_env", ""), ""),
        "api_url":   config.get("api_url") or pdef["default_url"],
        "model":     config.get("model") or pdef["default_model"],
        "aws_region": config.get("aws_region", os.environ.get("AWS_DEFAULT_REGION", "us-east-1")),
        "extra":     config.get("extra", {}),
    }


def interactive_setup() -> dict:
    """Interactive AI provider setup. Returns the config dict."""
    print("\n  AI Provider Configuration\n")
    print("  Choose how the orchestrator agent will generate responses:\n")

    providers_list = list(PROVIDERS.items())
    for i, (key, pdef) in enumerate(providers_list, 1):
        print(f"    {i}) {pdef['name']}")
        print(f"       {pdef['desc']}")
        print()

    while True:
        choice = input(f"  Select provider [1-{len(providers_list)}] (default: 1 — Ollama): ").strip()
        if not choice:
            idx = 0
            break
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(providers_list):
                break
        except ValueError:
            pass
        print("  Invalid choice, try again.")

    provider_key, pdef = providers_list[idx]
    config = {"provider": provider_key}

    print(f"\n  Selected: {pdef['name']}\n")

    # API key
    if pdef.get("needs_key"):
        env_key = pdef.get("key_env", "")
        existing = os.environ.get(env_key, "")
        if existing:
            masked = existing[:8] + "..." + existing[-4:] if len(existing) > 12 else "***"
            print(f"  Found {env_key} in environment: {masked}")
            use_env = input(f"  Use this key? [Y/n] ").strip().lower()
            if use_env != "n":
                config["api_key"] = ""  # will use env var
            else:
                config["api_key"] = input(f"  Enter API key: ").strip()
        else:
            config["api_key"] = input(f"  Enter API key ({env_key}): ").strip()

    # API URL (for custom endpoints)
    if provider_key == "custom":
        config["api_url"] = input(f"  API base URL (OpenAI-compatible): ").strip()

    # Model selection
    models = pdef.get("models", [])
    if models:
        print(f"\n  Available models:")
        for i, m in enumerate(models, 1):
            default_mark = " (default)" if m == pdef["default_model"] else ""
            print(f"    {i}) {m}{default_mark}")
        model_choice = input(f"\n  Select model [1-{len(models)}] (default: {pdef['default_model']}): ").strip()
        if model_choice:
            try:
                config["model"] = models[int(model_choice) - 1]
            except (ValueError, IndexError):
                config["model"] = model_choice  # let user type a custom model name
        else:
            config["model"] = pdef["default_model"]
    elif provider_key == "ollama":
        # Auto-detect Ollama models
        try:
            import httpx
            r = httpx.get(f"{pdef['default_url']}/api/tags", timeout=3)
            if r.status_code == 200:
                local_models = [m["name"] for m in r.json().get("models", [])]
                if local_models:
                    print(f"\n  Detected Ollama models:")
                    for i, m in enumerate(local_models, 1):
                        print(f"    {i}) {m}")
                    mc = input(f"\n  Select model [1-{len(local_models)}] (default: {local_models[0]}): ").strip()
                    if mc:
                        try:
                            config["model"] = local_models[int(mc) - 1]
                        except (ValueError, IndexError):
                            config["model"] = mc
                    else:
                        config["model"] = local_models[0]
                else:
                    print("\n  No Ollama models found. Pull one with: ollama pull qwen2.5:1.5b")
                    config["model"] = input("  Model name (or press Enter to skip): ").strip()
        except Exception:
            print("\n  Ollama not reachable. Make sure it's running: ollama serve")
            config["model"] = input("  Model name (or press Enter to skip): ").strip()
    elif provider_key == "custom":
        config["model"] = input(f"  Model name: ").strip()

    # Bedrock: AWS region
    if provider_key == "bedrock":
        region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
        config["aws_region"] = input(f"  AWS region [{region}]: ").strip() or region
        if not os.environ.get("AWS_ACCESS_KEY_ID"):
            print("\n  AWS credentials not found in environment.")
            print("  Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY, or configure AWS CLI.")

    save_ai_config(config)
    print(f"\n  Config saved to {AI_CONFIG_FILE}")
    return config
