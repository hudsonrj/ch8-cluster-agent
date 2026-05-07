"""
STT Agent — Speech-to-Text using faster-whisper (free, local)

Exposes /transcribe endpoint that converts audio to text.
Uses faster-whisper with CTranslate2 (runs on CPU, no GPU needed).
Model: base or small (auto-downloads on first use)
"""

import json
import logging
import os
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

log = logging.getLogger("ch8.stt")

CONFIG_DIR = Path.home() / ".config" / "ch8"
STATE_FILE = CONFIG_DIR / "state.json"
PID_FILE = CONFIG_DIR / "stt_agent.pid"
LOG_FILE = CONFIG_DIR / "stt_agent.log"
UPLOAD_DIR = Path("/tmp/ch8-stt")
UPLOAD_DIR.mkdir(exist_ok=True)

MODEL_SIZE = "base"  # base=~150MB, small=~500MB, medium=~1.5GB


def _update_state(status, task):
    try:
        state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
        agents = state.get("agents", [])
        entry = {
            "name": "stt_agent", "status": status, "task": task,
            "model": f"whisper-{MODEL_SIZE}", "platform": "faster-whisper",
            "autonomous": True, "updated_at": int(time.time()),
            "tools": ["transcribe"], "details": {},
            "alerts": 0, "security_findings": 0, "predictions": 0, "heavy_procs": 0,
        }
        agents = [a for a in agents if a.get("name") != "stt_agent"]
        agents.append(entry)
        state["agents"] = agents
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception:
        pass


_model = None

def get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        log.info(f"Loading Whisper model '{MODEL_SIZE}' (first time downloads ~150MB)...")
        _model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
        log.info("Model loaded")
    return _model


def transcribe(audio_path: str, language: str = "pt") -> dict:
    """Transcribe audio file to text."""
    model = get_model()
    segments, info = model.transcribe(audio_path, language=language, beam_size=5)
    text = " ".join([s.text.strip() for s in segments])
    return {
        "text": text,
        "language": info.language,
        "language_probability": round(info.language_probability, 2),
        "duration": round(info.duration, 1),
    }


def run_server():
    """Run FastAPI server for STT."""
    from fastapi import FastAPI, UploadFile, File
    import uvicorn
    import shutil

    app = FastAPI(title="CH8 STT Agent")

    @app.get("/health")
    async def health():
        return {"status": "ok", "agent": "stt", "model": f"whisper-{MODEL_SIZE}"}

    @app.post("/transcribe")
    async def transcribe_endpoint(file: UploadFile = File(...), language: str = "pt"):
        # Save uploaded file
        ts = int(time.time() * 1000)
        ext = Path(file.filename).suffix or ".wav"
        save_path = str(UPLOAD_DIR / f"audio_{ts}{ext}")
        with open(save_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        try:
            result = transcribe(save_path, language)
            return {"ok": True, **result}
        except Exception as e:
            return {"ok": False, "error": str(e)}
        finally:
            # Cleanup
            try:
                os.unlink(save_path)
            except Exception:
                pass

    @app.post("/transcribe/url")
    async def transcribe_url(body: dict = {}):
        """Transcribe from a URL (downloads first)."""
        import httpx
        url = body.get("url", "")
        language = body.get("language", "pt")
        if not url:
            return {"error": "url required"}
        try:
            r = httpx.get(url, timeout=30)
            ts = int(time.time() * 1000)
            save_path = str(UPLOAD_DIR / f"audio_{ts}.wav")
            with open(save_path, "wb") as f:
                f.write(r.content)
            result = transcribe(save_path, language)
            os.unlink(save_path)
            return {"ok": True, **result}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # Pre-load model on startup
    _update_state("running", f"Loading whisper-{MODEL_SIZE}...")
    get_model()
    _update_state("running", f"STT server on :7882 — model: whisper-{MODEL_SIZE}")
    uvicorn.run(app, host="0.0.0.0", port=7882, log_level="warning")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                        handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()])
    PID_FILE.write_text(str(os.getpid()))
    log.info("STT Agent starting")

    try:
        run_server()
    except KeyboardInterrupt:
        pass
    finally:
        _update_state("idle", "Stopped")
        PID_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
