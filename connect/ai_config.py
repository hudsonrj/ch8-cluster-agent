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
        "desc": "Claude via AWS — uses HTTPS bearer token",
        "needs_key": False,
        "key_env": "AWS_ACCESS_KEY_ID",
        "default_url": "",
        "default_model": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        "models": [
            "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
            "us.anthropic.claude-sonnet-4-6",
            "us.anthropic.claude-opus-4-6-v1",
            "us.anthropic.claude-haiku-4-5-20251001-v1:0",
            "us.anthropic.claude-sonnet-4-20250514-v1:0",
        ],
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
    """
    Return the current provider config with env vars resolved.

    Auto-detection priority:
      1. CLAUDE_CODE_USE_BEDROCK=1 + AWS_BEARER_TOKEN_BEDROCK → bedrock via HTTPS
      2. ai.json config file
      3. Fallback to ollama
    """
    # Auto-detect: if CLAUDE_CODE_USE_BEDROCK is set, use Bedrock without needing ai.json
    if os.environ.get("CLAUDE_CODE_USE_BEDROCK", "").strip() in ("1", "true", "yes"):
        region = os.environ.get("AWS_REGION", "us-east-1")
        # Try to get model from ai.json or default
        config = load_ai_config()
        model = config.get("model", "") or "us.anthropic.claude-sonnet-4-20250514-v1:0"
        return {
            "provider":   "bedrock",
            "name":       "AWS Bedrock (auto)",
            "api_key":    "",
            "api_url":    "",
            "model":      model,
            "aws_region": region,
            "extra":      {},
        }

    config = load_ai_config()
    provider = config.get("provider", "ollama")
    pdef = PROVIDERS.get(provider, PROVIDERS["ollama"])

    return {
        "provider":  provider,
        "name":      pdef["name"],
        "api_key":   config.get("api_key") or os.environ.get(pdef.get("key_env", ""), ""),
        "api_url":   config.get("api_url") or pdef["default_url"],
        "model":     config.get("model") or pdef["default_model"],
        "aws_region": config.get("aws_region", os.environ.get("AWS_REGION", "us-east-1")),
        "extra":     config.get("extra", {}),
    }


class AIClient:
    """
    Wrapper unificado para qualquer provedor AI configurado.
    Expõe um único método: chat(messages, **kwargs) -> str
    """
    def __init__(self, config: dict):
        self.provider = config["provider"]
        self.model    = config["model"]
        self.api_key  = config["api_key"]
        self.api_url  = config["api_url"]
        self.aws_region = config.get("aws_region", "us-east-1")

    def chat(self, messages: list, max_tokens: int = 4096, temperature: float = 0.7) -> str:
        p = self.provider
        if p == "ollama":
            return self._ollama(messages, max_tokens, temperature)
        elif p in ("openai", "groq", "custom"):
            return self._openai_compat(messages, max_tokens, temperature)
        elif p == "anthropic":
            return self._anthropic(messages, max_tokens, temperature)
        elif p == "bedrock":
            return self._bedrock(messages, max_tokens, temperature)
        else:
            raise ValueError(f"Unknown provider: {p}")

    def _ollama(self, messages, max_tokens, temperature):
        import httpx
        base = self.api_url or "http://localhost:11434"
        r = httpx.post(f"{base}/api/chat", json={
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"num_predict": max_tokens, "temperature": temperature},
        }, timeout=180)
        r.raise_for_status()
        return r.json()["message"]["content"]

    def _openai_compat(self, messages, max_tokens, temperature):
        import httpx
        base = self.api_url
        key  = self.api_key
        if self.provider == "groq":
            base = base or "https://api.groq.com/openai/v1"
            key  = key or os.environ.get("GROQ_API_KEY", "")
        elif self.provider == "openai":
            base = base or "https://api.openai.com/v1"
            key  = key or os.environ.get("OPENAI_API_KEY", "")
        r = httpx.post(f"{base}/chat/completions", json={
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }, headers={"Authorization": f"Bearer {key}"}, timeout=180)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    def _anthropic(self, messages, max_tokens, temperature):
        import httpx
        key = self.api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        system_msgs = [m for m in messages if m["role"] == "system"]
        user_msgs   = [m for m in messages if m["role"] != "system"]
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": user_msgs,
        }
        if system_msgs:
            payload["system"] = system_msgs[0]["content"]
        r = httpx.post("https://api.anthropic.com/v1/messages", json=payload,
                       headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                       timeout=180)
        r.raise_for_status()
        return r.json()["content"][0]["text"]

    def _bedrock(self, messages, max_tokens, temperature):
        import json as _json
        import httpx
        from urllib.parse import quote

        region = self.aws_region or os.environ.get("AWS_REGION", "us-east-1")
        bearer_token = os.environ.get("AWS_BEARER_TOKEN_BEDROCK", "")

        system_msgs = [m for m in messages if m["role"] == "system"]
        user_msgs   = [m for m in messages if m["role"] != "system"]
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "messages": user_msgs,
        }
        if system_msgs:
            body["system"] = system_msgs[0]["content"]
        if temperature is not None:
            body["temperature"] = temperature

        # Prefer bearer token via httpx (no boto3 needed)
        if bearer_token:
            model_id = self.model
            encoded = quote(model_id, safe="")
            url = f"https://bedrock-runtime.{region}.amazonaws.com/model/{encoded}/invoke"
            headers = {
                "Authorization": f"Bearer {bearer_token}",
                "Content-Type": "application/json",
            }
            resp = httpx.post(url, json=body, headers=headers, timeout=120)
            if resp.status_code != 200:
                raise RuntimeError(f"Bedrock error {resp.status_code}: {resp.text[:200]}")
            result = resp.json()
            return result["content"][0]["text"]

        # Fallback: boto3 (requires AWS_ACCESS_KEY_ID/SECRET)
        import boto3
        client = boto3.client("bedrock-runtime", region_name=region)
        resp = client.invoke_model(
            modelId=self.model,
            body=_json.dumps(body),
            contentType="application/json",
        )
        result = _json.loads(resp["body"].read())
        return result["content"][0]["text"]


def get_ai_client() -> AIClient:
    """Return a configured AIClient ready to call .chat()."""
    return AIClient(get_provider_info())


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

    # Bedrock: configure via bearer token (saves to env file)
    if provider_key == "bedrock":
        existing_token = os.environ.get("AWS_BEARER_TOKEN_BEDROCK", "")
        existing_region = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))

        if existing_token:
            masked = existing_token[:12] + "..." + existing_token[-6:]
            print(f"\n  ✓ Bearer token found: {masked}")
            print(f"  ✓ Region: {existing_region}")
            keep = input("  Keep current config? [Y/n] ").strip().lower()
            if keep != "n":
                config["aws_region"] = existing_region
            else:
                existing_token = ""  # force re-entry below

        if not existing_token:
            print("\n  Bedrock via HTTPS (Bearer Token)")
            print("  ─────────────────────────────────")
            print("  This uses direct HTTPS calls to AWS Bedrock.")
            print("  No boto3, no IAM credentials needed.\n")

            token = input("  AWS_BEARER_TOKEN_BEDROCK: ").strip()
            region = input(f"  AWS_REGION [{existing_region}]: ").strip() or existing_region
            config["aws_region"] = region

            if token:
                # Save to env file so all agents pick it up
                env_file = CONFIG_DIR / "env"
                env_lines = []
                if env_file.exists():
                    env_lines = [l for l in env_file.read_text().splitlines()
                                 if not l.startswith("AWS_BEARER_TOKEN_BEDROCK=")
                                 and not l.startswith("AWS_REGION=")
                                 and not l.startswith("CLAUDE_CODE_USE_BEDROCK=")]

                env_lines.append(f"CLAUDE_CODE_USE_BEDROCK=1")
                env_lines.append(f"AWS_REGION={region}")
                env_lines.append(f"AWS_BEARER_TOKEN_BEDROCK={token}")

                env_file.write_text("\n".join(env_lines) + "\n")
                env_file.chmod(0o600)
                print(f"\n  ✓ Credentials saved to {env_file}")
                print(f"  ✓ CLAUDE_CODE_USE_BEDROCK=1")
                print(f"  ✓ AWS_REGION={region}")
                print(f"  ✓ AWS_BEARER_TOKEN_BEDROCK={token[:12]}...")

                # Also set in current process
                os.environ["CLAUDE_CODE_USE_BEDROCK"] = "1"
                os.environ["AWS_REGION"] = region
                os.environ["AWS_BEARER_TOKEN_BEDROCK"] = token
            else:
                print("\n  ⚠ No token provided. Bedrock will need boto3/IAM credentials.")

        # Test connection
        print("\n  Testing Bedrock connection...")
        try:
            test_client = AIClient({
                "provider": "bedrock",
                "model": config.get("model", "us.anthropic.claude-sonnet-4-20250514-v1:0"),
                "api_key": "", "api_url": "",
                "aws_region": config.get("aws_region", "us-east-1"),
            })
            result = test_client.chat([{"role": "user", "content": "say OK"}], max_tokens=5)
            print(f"  ✓ Connection OK! Response: {result.strip()}")
        except Exception as e:
            print(f"  ✗ Connection failed: {e}")
            print("    Check your token and try again.")

    save_ai_config(config)
    print(f"\n  Config saved to {AI_CONFIG_FILE}")
    return config
