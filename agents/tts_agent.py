"""
TTS Agent — Text-to-Speech using Microsoft Edge Neural Voices (free)

Exposes /speak endpoint that converts text to natural speech audio.
Uses edge-tts (free, no API key, high quality PT-BR voices).

Voices: pt-BR-FranciscaNeural (female), pt-BR-AntonioNeural (male)
"""

import asyncio
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

log = logging.getLogger("ch8.tts")

CONFIG_DIR = Path.home() / ".config" / "ch8"
STATE_FILE = CONFIG_DIR / "state.json"
PID_FILE = CONFIG_DIR / "tts_agent.pid"
LOG_FILE = CONFIG_DIR / "tts_agent.log"
AUDIO_DIR = Path("/tmp/ch8-tts")
AUDIO_DIR.mkdir(exist_ok=True)

DEFAULT_VOICE = "pt-BR-FranciscaNeural"


def _update_state(status, task):
    try:
        state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
        agents = state.get("agents", [])
        entry = {
            "name": "tts_agent", "status": status, "task": task,
            "model": "edge-tts", "platform": "microsoft",
            "autonomous": True, "updated_at": int(time.time()),
            "tools": ["speak", "list_voices"], "details": {},
            "alerts": 0, "security_findings": 0, "predictions": 0, "heavy_procs": 0,
        }
        agents = [a for a in agents if a.get("name") != "tts_agent"]
        agents.append(entry)
        state["agents"] = agents
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception:
        pass


async def speak(text: str, voice: str = DEFAULT_VOICE) -> str:
    """Convert text to speech, return path to audio file."""
    import edge_tts
    ts = int(time.time() * 1000)
    output_file = str(AUDIO_DIR / f"speech_{ts}.mp3")
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_file)
    return output_file


def run_server():
    """Run FastAPI server for TTS."""
    from fastapi import FastAPI
    from fastapi.responses import FileResponse
    import uvicorn

    app = FastAPI(title="CH8 TTS Agent")

    @app.get("/health")
    async def health():
        return {"status": "ok", "agent": "tts", "voice": DEFAULT_VOICE}

    @app.post("/speak")
    async def speak_endpoint(body: dict = {}):
        text = body.get("text", "")
        voice = body.get("voice", DEFAULT_VOICE)
        if not text:
            return {"error": "text required"}
        try:
            path = await speak(text, voice)
            return {"ok": True, "file": path, "voice": voice, "chars": len(text)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.get("/speak/download/{filename}")
    async def download(filename: str):
        path = AUDIO_DIR / filename
        if path.exists():
            return FileResponse(path, media_type="audio/mpeg", filename=filename)
        return {"error": "file not found"}

    @app.get("/voices")
    async def list_voices():
        import edge_tts
        voices = await edge_tts.list_voices()
        pt_voices = [v for v in voices if "pt-BR" in v.get("Locale", "")]
        return {"voices": [{"name": v["ShortName"], "gender": v["Gender"]} for v in pt_voices]}

    _update_state("running", f"TTS server on :7881 — voice: {DEFAULT_VOICE}")

    # Background heartbeat to keep state fresh
    import threading
    def _heartbeat():
        while True:
            time.sleep(30)
            _update_state("running", f"TTS on :7881 — {DEFAULT_VOICE}")
    threading.Thread(target=_heartbeat, daemon=True).start()

    uvicorn.run(app, host="0.0.0.0", port=7881, log_level="warning")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                        handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()])
    PID_FILE.write_text(str(os.getpid()))
    log.info("TTS Agent starting")
    _update_state("running", "Starting TTS server...")

    try:
        run_server()
    except KeyboardInterrupt:
        pass
    finally:
        _update_state("idle", "Stopped")
        PID_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
