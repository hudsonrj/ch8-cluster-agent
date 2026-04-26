"""
Communication channels for CH8 agents.

Two types of channels:
  1. Notification (one-way) — alerts sent out
  2. Interactive (two-way) — user sends commands, agent responds

Interactive channels:
  - dashboard   — Web dashboard chat (always available)
  - telegram    — Telegram Bot (bidirectional, long-polling)
  - slack       — Slack Bot (bidirectional, socket mode or webhook)

Notification-only channels:
  - discord     — Discord webhook (alerts only)
  - webhook     — Generic HTTP webhook (alerts only)
  - none        — Dashboard only (default)
"""

import json
import os
from pathlib import Path
from typing import Optional

CONFIG_DIR = Path(os.environ.get("CH8_CONFIG_DIR", Path.home() / ".config" / "ch8"))
CHANNELS_FILE = CONFIG_DIR / "channels.json"

CHANNEL_TYPES = {
    "dashboard": {
        "name": "Dashboard only",
        "desc": "Chat via web dashboard — always available, no extra setup",
        "interactive": True,
        "fields": [],
    },
    "telegram": {
        "name": "Telegram Bot (interactive)",
        "desc": "Two-way: send commands and receive responses via Telegram",
        "interactive": True,
        "fields": ["bot_token", "chat_id"],
        "setup_help": "1. Talk to @BotFather on Telegram\n       2. /newbot → get the bot token\n       3. Send a message to your bot, then visit:\n          https://api.telegram.org/bot<TOKEN>/getUpdates\n          to find your chat_id",
    },
    "slack": {
        "name": "Slack Bot (interactive)",
        "desc": "Two-way: send commands and receive responses via Slack",
        "interactive": True,
        "fields": ["bot_token", "channel_id"],
        "setup_help": "1. Create a Slack App at https://api.slack.com/apps\n       2. Add Bot Token Scopes: chat:write, channels:history, channels:read\n       3. Install to workspace → get Bot Token (xoxb-...)\n       4. Invite the bot to your channel",
    },
    "discord": {
        "name": "Discord Webhook (alerts only)",
        "desc": "One-way: receive alerts in a Discord channel",
        "interactive": False,
        "fields": ["webhook_url"],
        "placeholder": "https://discord.com/api/webhooks/.../...",
    },
    "webhook": {
        "name": "Generic Webhook (alerts only)",
        "desc": "One-way: POST JSON alerts to any HTTP endpoint",
        "interactive": False,
        "fields": ["webhook_url"],
        "placeholder": "https://your-server.com/alerts",
    },
}


def load_channels() -> list:
    """Load configured channels."""
    if CHANNELS_FILE.exists():
        try:
            return json.loads(CHANNELS_FILE.read_text())
        except Exception:
            pass
    return []


def save_channels(channels: list) -> None:
    """Save channel config."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CHANNELS_FILE.write_text(json.dumps(channels, indent=2))
    CHANNELS_FILE.chmod(0o600)


def send_alert(title: str, message: str, severity: str = "info") -> None:
    """Send an alert to all configured channels."""
    import httpx
    channels = load_channels()

    for ch in channels:
        ch_type = ch.get("type", "none")
        if ch_type == "none":
            continue
        try:
            if ch_type == "slack":
                _send_slack(ch, title, message, severity)
            elif ch_type == "discord":
                _send_discord(ch, title, message, severity)
            elif ch_type == "telegram":
                _send_telegram(ch, title, message, severity)
            elif ch_type == "webhook":
                _send_webhook(ch, title, message, severity)
        except Exception:
            pass


def _send_slack(ch: dict, title: str, message: str, severity: str) -> None:
    import httpx
    colors = {"critical": "#ef4444", "high": "#f59e0b", "warning": "#f59e0b", "info": "#0070f3"}
    payload = {
        "attachments": [{
            "color": colors.get(severity, "#0070f3"),
            "title": f"CH8 Alert: {title}",
            "text": message,
            "footer": f"CH8 Agent | {os.uname().nodename}",
        }]
    }
    httpx.post(ch["webhook_url"], json=payload, timeout=10)


def _send_discord(ch: dict, title: str, message: str, severity: str) -> None:
    import httpx
    colors = {"critical": 0xef4444, "high": 0xf59e0b, "warning": 0xf59e0b, "info": 0x0070f3}
    payload = {
        "embeds": [{
            "title": f"CH8 Alert: {title}",
            "description": message,
            "color": colors.get(severity, 0x0070f3),
            "footer": {"text": f"CH8 Agent | {os.uname().nodename}"},
        }]
    }
    httpx.post(ch["webhook_url"], json=payload, timeout=10)


def _send_telegram(ch: dict, title: str, message: str, severity: str) -> None:
    import httpx
    icons = {"critical": "🔴", "high": "🟠", "warning": "🟡", "info": "🔵"}
    text = f"{icons.get(severity, 'ℹ️')} *CH8 Alert: {title}*\n\n{message}\n\n_Node: {os.uname().nodename}_"
    httpx.post(
        f"https://api.telegram.org/bot{ch['bot_token']}/sendMessage",
        json={"chat_id": ch["chat_id"], "text": text, "parse_mode": "Markdown"},
        timeout=10,
    )


def _send_webhook(ch: dict, title: str, message: str, severity: str) -> None:
    import httpx
    import socket
    payload = {
        "event": "ch8_alert",
        "title": title,
        "message": message,
        "severity": severity,
        "hostname": socket.gethostname(),
        "timestamp": __import__("time").time(),
    }
    httpx.post(ch["webhook_url"], json=payload, timeout=10)


def interactive_setup() -> list:
    """Interactive channel setup. Returns the channel list."""
    print("\n  Communication Channels\n")
    print("  How do you want to interact with your CH8 agents?\n")
    print("  Interactive channels let you send commands and chat with agents.")
    print("  Notification channels only receive alerts.\n")

    types_list = list(CHANNEL_TYPES.items())
    for i, (key, info) in enumerate(types_list, 1):
        tag = " [interactive]" if info.get("interactive") else " [alerts only]"
        print(f"    {i}) {info['name']}{tag}")
        print(f"       {info['desc']}")
        print()

    while True:
        choice = input(f"  Select channel [1-{len(types_list)}] (default: 1 — Dashboard only): ").strip()
        if not choice:
            idx = 0
            break
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(types_list):
                break
        except ValueError:
            pass
        print("  Invalid choice, try again.")

    ch_key, ch_info = types_list[idx]

    if ch_key == "dashboard":
        channels = [{"type": "dashboard"}]
        save_channels(channels)
        print("\n  Dashboard chat enabled. Access at your control server URL.")
        return channels

    print(f"\n  Configuring {ch_info['name']}:\n")

    # Show setup help if available
    if ch_info.get("setup_help"):
        print(f"  Setup guide:")
        print(f"       {ch_info['setup_help']}")
        print()

    ch_config = {"type": ch_key, "interactive": ch_info.get("interactive", False)}

    for field in ch_info.get("fields", []):
        placeholder = ch_info.get("placeholder", "")
        hint = f" (e.g. {placeholder})" if placeholder and field == "webhook_url" else ""
        value = input(f"  {field}{hint}: ").strip()
        ch_config[field] = value

    channels = [{"type": "dashboard"}, ch_config]  # dashboard always available

    # Offer to add another
    while True:
        more = input("\n  Add another channel? [y/N] ").strip().lower()
        if more != "y":
            break
        for i, (key, info) in enumerate(types_list[1:], 2):
            tag = " [interactive]" if info.get("interactive") else " [alerts only]"
            print(f"    {i}) {info['name']}{tag}")
        try:
            idx2 = int(input("  Select: ").strip()) - 1
            if 0 <= idx2 < len(types_list):
                k2, i2 = types_list[idx2]
                cfg2 = {"type": k2, "interactive": i2.get("interactive", False)}
                for field in i2.get("fields", []):
                    cfg2[field] = input(f"  {field}: ").strip()
                channels.append(cfg2)
        except (ValueError, IndexError):
            pass

    save_channels(channels)
    interactive_count = sum(1 for c in channels if c.get("interactive") or c["type"] == "dashboard")
    print(f"\n  {len(channels)} channel(s) configured ({interactive_count} interactive).")
    return channels
