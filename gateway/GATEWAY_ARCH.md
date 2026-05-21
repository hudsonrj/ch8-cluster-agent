# CH8 Gateway Multi-Plataforma

## Arquitetura (inspirada no Hermes Agent)

```
gateway/
  __init__.py
  run.py          # Processo principal do gateway
  session.py      # Gerenciamento de sessões cross-platform
  platforms/
    telegram.py   # Já existe (telegram_listener.py)
    discord.py    # TODO: discord.py library
    slack.py      # TODO: slack_bolt library
    whatsapp.py   # TODO: Baileys ou Twilio
```

## Como estender o telegram_listener.py para Discord

```python
# pip install discord.py
import discord

client = discord.Client(intents=discord.Intents.default())

@client.event
async def on_message(message):
    if message.author == client.user: return
    response = _chat_with_orchestrator(message.content)
    await message.channel.send(response)

# No main: asyncio.run(client.start(DISCORD_TOKEN))
```

## Variáveis de configuração (adicionar ao vault):
- gateway/discord_token
- gateway/slack_bot_token
- gateway/whatsapp_number (via Twilio)

## Status de implementação:
- ✅ Telegram: /data/ch8-agent/agents/telegram_listener.py
- 🔄 Discord: Arquitetura documentada, aguarda discord.py install
- 🔄 Slack: Aguarda slack_bolt install
- 🔄 WhatsApp: Aguarda decisão API (Baileys/Twilio)
