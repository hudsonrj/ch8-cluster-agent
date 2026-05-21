
import logging, os
log = logging.getLogger("ch8.computer")
ENABLED = os.environ.get("CH8_COMPUTER_USE","false").lower() == "true"

def computer_screenshot() -> dict:
    if not ENABLED: return {"ok":False,"error":"Computer use disabled. Set CH8_COMPUTER_USE=true"}
    try:
        import pyautogui, base64, io
        from PIL import Image
        img = pyautogui.screenshot()
        buf = io.BytesIO(); img.save(buf, format='PNG')
        return {"ok":True,"screenshot_b64":base64.b64encode(buf.getvalue()).decode()}
    except ImportError: return {"ok":False,"error":"pip install pyautogui Pillow"}
    except Exception as e: return {"ok":False,"error":str(e)}

def computer_click(x: int, y: int) -> dict:
    if not ENABLED: return {"ok":False,"error":"Disabled"}
    try:
        import pyautogui; pyautogui.click(x, y)
        return {"ok":True,"x":x,"y":y}
    except Exception as e: return {"ok":False,"error":str(e)}

def computer_type(text: str) -> dict:
    if not ENABLED: return {"ok":False,"error":"Disabled"}
    try:
        import pyautogui; pyautogui.typewrite(text, interval=0.05)
        return {"ok":True}
    except Exception as e: return {"ok":False,"error":str(e)}
