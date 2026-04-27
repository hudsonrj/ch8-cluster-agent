#!/usr/bin/env python3
"""
CH8 Telegram Listener Agent

Polls Telegram for incoming messages and forwards them to the orchestrator.
Sends responses back to the Telegram chat.

Started automatically by `ch8 up` if Telegram is configured in channels.json.
"""

import json
import logging
import os
import sys
import time
from pathlib import Path

try:
    import httpx
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet",
                           "--break-system-packages", "httpx"])
    import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

log = logging.getLogger("ch8.telegram")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")

CONFIG_DIR = Path.home() / ".config" / "ch8"

# Load env vars from ~/.config/ch8/env
def _load_env_file():
    env_file = CONFIG_DIR / "env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                if key.strip():
                    os.environ.setdefault(key.strip(), val.strip())

_load_env_file()

STATE_FILE = CONFIG_DIR / "state.json"
AGENT_PORT = int(os.environ.get("CH8_AGENT_PORT", "7879"))


def _load_telegram_config() -> dict | None:
    """Load Telegram channel config from channels.json."""
    channels_file = CONFIG_DIR / "channels.json"
    if not channels_file.exists():
        return None
    try:
        channels = json.loads(channels_file.read_text())
        for ch in channels:
            if ch.get("type") == "telegram" and ch.get("bot_token") and ch.get("chat_id"):
                return ch
    except Exception:
        pass
    return None


def _register_agent(status="idle", task="listening"):
    """Register this agent in state.json."""
    import fcntl
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        lock_file = STATE_FILE.with_suffix(".lock")
        with open(lock_file, "w") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            state = {}
            if STATE_FILE.exists():
                state = json.loads(STATE_FILE.read_text())
            agents = state.get("agents", [])
            agents = [a for a in agents if a.get("name") != "telegram"]
            agents.append({
                "name": "telegram",
                "status": status,
                "task": task,
                "model": "bot listener",
                "platform": "telegram",
                "autonomous": False,
                "alerts": 0,
                "security_findings": 0,
                "predictions": 0,
                "heavy_procs": 0,
                "details": {},
                "updated_at": int(time.time()),
            })
            state["agents"] = agents
            STATE_FILE.write_text(json.dumps(state, indent=2))
            fcntl.flock(lf, fcntl.LOCK_UN)
    except Exception as e:
        log.warning(f"Failed to register agent: {e}")


def _send_telegram(bot_token: str, chat_id: str, text: str):
    """Send a message to Telegram."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    # Split long messages (Telegram limit is 4096 chars)
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        try:
            httpx.post(url, json={
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": "Markdown",
            }, timeout=15)
        except Exception:
            # Retry without markdown if parse fails
            try:
                httpx.post(url, json={
                    "chat_id": chat_id,
                    "text": chunk,
                }, timeout=15)
            except Exception as e:
                log.error(f"Failed to send Telegram message: {e}")


def _send_typing(bot_token: str, chat_id: str):
    """Send 'typing...' indicator to Telegram."""
    try:
        httpx.post(
            f"https://api.telegram.org/bot{bot_token}/sendChatAction",
            json={"chat_id": chat_id, "action": "typing"},
            timeout=5,
        )
    except Exception:
        pass


def _chat_with_orchestrator(message: str, bot_token: str = "", chat_id: str = "") -> str:
    """Send a message to the local orchestrator and collect the full response."""
    import threading

    uds_path = os.environ.get("CH8_UDS") or str(CONFIG_DIR / "orchestrator.sock")
    payload = {
        "messages": [{"role": "user", "content": message}],
    }

    # Try Unix socket first, fall back to TCP
    transport = None
    if Path(uds_path).exists():
        transport = httpx.HTTPTransport(uds=uds_path)
        url = "http://localhost/chat"
    else:
        url = f"http://127.0.0.1:{AGENT_PORT}/chat"

    # Send typing indicator every 5s while waiting
    typing_active = [True]

    def _typing_loop():
        while typing_active[0]:
            _send_typing(bot_token, chat_id)
            time.sleep(5)

    if bot_token and chat_id:
        threading.Thread(target=_typing_loop, daemon=True).start()

    full_response = ""
    try:
        with httpx.Client(timeout=120, transport=transport) as client:
            with client.stream("POST", url, json=payload) as resp:
                if resp.status_code != 200:
                    return f"Error: orchestrator returned {resp.status_code}"
                for line in resp.iter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            msg = json.loads(data)
                            content = msg.get("message", {}).get("content", "")
                            if content:
                                full_response += content
                        except json.JSONDecodeError:
                            pass
    except httpx.ConnectError:
        return "Error: orchestrator is not running"
    except httpx.ReadTimeout:
        return full_response + "\n\n(timeout — response truncated)"
    except Exception as e:
        return f"Error: {e}"
    finally:
        typing_active[0] = False

    return full_response or "(no response)"


def main():
    config = _load_telegram_config()
    if not config:
        log.error("No Telegram channel configured. Run: ch8 config channels")
        sys.exit(1)

    bot_token = config["bot_token"]
    chat_id = str(config["chat_id"])

    log.info(f"Telegram listener starting (chat_id={chat_id})")
    _register_agent("running", f"polling chat {chat_id}")

    # Get bot info
    try:
        resp = httpx.get(f"https://api.telegram.org/bot{bot_token}/getMe", timeout=10)
        if resp.status_code == 200:
            bot_info = resp.json().get("result", {})
            log.info(f"Bot: @{bot_info.get('username', '?')}")
        else:
            log.error(f"Invalid bot token: {resp.status_code}")
            sys.exit(1)
    except Exception as e:
        log.error(f"Cannot reach Telegram API: {e}")
        sys.exit(1)

    offset = 0
    poll_timeout = 30  # long-polling timeout in seconds

    while True:
        try:
            _register_agent("running", f"polling chat {chat_id}")

            # Long-poll for updates
            resp = httpx.get(
                f"https://api.telegram.org/bot{bot_token}/getUpdates",
                params={
                    "offset": offset,
                    "timeout": poll_timeout,
                    "allowed_updates": json.dumps(["message"]),
                },
                timeout=poll_timeout + 10,
            )

            if resp.status_code != 200:
                log.warning(f"Telegram API error: {resp.status_code}")
                time.sleep(5)
                continue

            updates = resp.json().get("result", [])

            for update in updates:
                offset = update["update_id"] + 1

                msg = update.get("message", {})
                text = msg.get("text", "")
                msg_chat_id = str(msg.get("chat", {}).get("id", ""))
                from_user = msg.get("from", {}).get("first_name", "?")

                if not text:
                    continue

                # Only respond to the configured chat_id
                if msg_chat_id != chat_id:
                    log.info(f"Ignoring message from unauthorized chat {msg_chat_id}")
                    continue

                log.info(f"Message from {from_user}: {text[:80]}")
                _register_agent("running", f"responding to: {text[:40]}")

                # Forward to orchestrator
                response = _chat_with_orchestrator(text, bot_token, chat_id)

                # Send response back to Telegram
                _send_telegram(bot_token, chat_id, response)
                log.info(f"Response sent ({len(response)} chars)")

        except httpx.ReadTimeout:
            # Normal — long-polling timeout, just retry
            continue
        except KeyboardInterrupt:
            log.info("Shutting down")
            break
        except Exception as e:
            log.error(f"Error in polling loop: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
