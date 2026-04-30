"""
CH8 Agent — Android App

Startup order matters:
1. Set env vars and paths FIRST (before any connect imports)
2. Configure file logging SECOND
3. Then import Kivy and connect modules
"""

# ── Step 1: paths and env (nothing else imported yet) ─────────────────────
import os
import sys
import time

APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_DIR)

# Try Android storage, fall back to app directory
STORAGE_DIR = APP_DIR
try:
    from android.storage import app_storage_path
    STORAGE_DIR = app_storage_path()
except Exception:
    pass

from pathlib import Path
CONFIG_DIR = Path(STORAGE_DIR) / ".config" / "ch8"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# Try external storage for accessible log files
try:
    from android.storage import primary_external_storage_path
    EXT_DIR = Path(primary_external_storage_path()) / "CH8"
    EXT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE = EXT_DIR / "ch8-agent.log"
except Exception:
    LOG_FILE = CONFIG_DIR / "daemon.log"

# Set env vars before any connect module is imported
os.environ["HOME"] = STORAGE_DIR
os.environ["CH8_CONFIG_DIR"] = str(CONFIG_DIR)

# ── Step 2: logging ───────────────────────────────────────────────────────
import logging
import threading

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), mode='a'),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger("ch8.android")
log.info("=" * 60)
log.info(f"CH8 Android starting. APP_DIR={APP_DIR}")
log.info(f"CONFIG_DIR={CONFIG_DIR}")
log.info(f"LOG_FILE={LOG_FILE}")
log.info(f"Python {sys.version}")

# ── Step 3: Kivy ──────────────────────────────────────────────────────────
from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.utils import get_color_from_hex

Window.clearcolor = get_color_from_hex('#0D1117')

# ── In-memory log capture ─────────────────────────────────────────────────
_log_lines = []

class _CapHandler(logging.Handler):
    def emit(self, record):
        _log_lines.append(self.format(record))
        if len(_log_lines) > 200:
            _log_lines.pop(0)

_cap = _CapHandler()
_cap.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s", "%H:%M:%S"))
logging.getLogger().addHandler(_cap)


# ── Screens ───────────────────────────────────────────────────────────────

class SetupScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical', padding=30, spacing=12)

        layout.add_widget(Label(
            text='[b]CH8[/b] Agent', markup=True,
            font_size='32sp', color=get_color_from_hex('#58A6FF'),
            size_hint_y=None, height=50
        ))
        layout.add_widget(Label(
            text='Distributed AI Node',
            font_size='14sp', color=get_color_from_hex('#8B949E'),
            size_hint_y=None, height=24
        ))

        layout.add_widget(Label(size_hint_y=0.05))

        layout.add_widget(Label(
            text='Token de rede:', font_size='13sp',
            color=get_color_from_hex('#C9D1D9'),
            size_hint_y=None, height=24, halign='left'
        ))
        self.token_input = TextInput(
            hint_text='tk_xxxxx  (obtido via: ch8 token create)',
            multiline=False, size_hint_y=None, height=44,
            background_color=get_color_from_hex('#21262D'),
            foreground_color=get_color_from_hex('#E6EDF3'),
            padding=[10, 10]
        )
        layout.add_widget(self.token_input)

        layout.add_widget(Label(
            text='Provedor AI (ex: groq, openai, bedrock):',
            font_size='13sp', color=get_color_from_hex('#C9D1D9'),
            size_hint_y=None, height=24, halign='left'
        ))
        self.provider_input = TextInput(
            hint_text='groq', multiline=False,
            size_hint_y=None, height=44,
            background_color=get_color_from_hex('#21262D'),
            foreground_color=get_color_from_hex('#E6EDF3'),
            padding=[10, 10]
        )
        layout.add_widget(self.provider_input)

        layout.add_widget(Label(
            text='API Key:', font_size='13sp',
            color=get_color_from_hex('#C9D1D9'),
            size_hint_y=None, height=24, halign='left'
        ))
        self.api_key_input = TextInput(
            hint_text='sk-...', multiline=False,
            size_hint_y=None, height=44,
            password=True,
            background_color=get_color_from_hex('#21262D'),
            foreground_color=get_color_from_hex('#E6EDF3'),
            padding=[10, 10]
        )
        layout.add_widget(self.api_key_input)

        self.connect_btn = Button(
            text='Conectar', size_hint_y=None, height=48,
            background_color=get_color_from_hex('#238636'),
            font_size='16sp'
        )
        self.connect_btn.bind(on_press=self.connect)
        layout.add_widget(self.connect_btn)

        self.status_label = Label(
            text='', font_size='12sp',
            color=get_color_from_hex('#F85149'),
            size_hint_y=None, height=40,
            text_size=(Window.width - 60, None),
            halign='center'
        )
        layout.add_widget(self.status_label)

        # Log viewer toggle
        log_btn = Button(
            text='Ver Logs', size_hint_y=None, height=36,
            background_color=get_color_from_hex('#21262D'),
            font_size='12sp'
        )
        log_btn.bind(on_press=self.show_logs)
        layout.add_widget(log_btn)

        self.log_box = ScrollView(size_hint_y=0.35)
        self.log_label = Label(
            text='Log vazio', font_size='9sp',
            color=get_color_from_hex('#484F58'),
            size_hint_y=None, halign='left', valign='top',
            text_size=(Window.width - 40, None)
        )
        self.log_label.bind(texture_size=self.log_label.setter('size'))
        self.log_box.add_widget(self.log_label)
        self.log_box.opacity = 0
        layout.add_widget(self.log_box)

        self.add_widget(layout)
        Clock.schedule_interval(self._refresh_log, 2)

    def show_logs(self, *a):
        self.log_box.opacity = 1 if self.log_box.opacity == 0 else 0

    def _refresh_log(self, dt):
        if self.log_box.opacity > 0:
            self.log_label.text = '\n'.join(_log_lines[-30:]) or 'sem logs'

    def connect(self, instance):
        token = self.token_input.text.strip()
        if not token:
            self._set_status('Informe o token', error=True)
            return
        provider = self.provider_input.text.strip() or 'groq'
        api_key  = self.api_key_input.text.strip()

        self.connect_btn.disabled = True
        self._set_status('Autenticando...', error=False)
        threading.Thread(
            target=self._do_connect,
            args=(token, provider, api_key),
            daemon=True
        ).start()

    def _do_connect(self, token, provider, api_key):
        app = App.get_running_app()
        msg = app.save_config(token, provider, api_key)
        if msg:
            Clock.schedule_once(lambda dt: self._on_fail(msg))
        else:
            Clock.schedule_once(lambda dt: self._on_success())

    def _on_fail(self, msg):
        self._set_status(f'Erro: {msg}', error=True)
        self.connect_btn.disabled = False
        self.log_box.opacity = 1

    def _on_success(self):
        self._set_status('Conectado!', error=False)
        self.manager.current = 'dashboard'
        App.get_running_app().start_daemon()

    def _set_status(self, msg, error=True):
        self.status_label.color = get_color_from_hex('#F85149' if error else '#4CAF50')
        self.status_label.text = msg


class DashboardScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical', padding=16, spacing=8)

        # Header
        hdr = BoxLayout(size_hint_y=None, height=44, spacing=8)
        hdr.add_widget(Label(
            text='[b]CH8[/b]', markup=True,
            font_size='18sp', color=get_color_from_hex('#58A6FF'),
            size_hint_x=0.2
        ))
        self.status_lbl = Label(
            text='...', font_size='13sp',
            color=get_color_from_hex('#FFA500'),
            size_hint_x=0.3
        )
        hdr.add_widget(self.status_lbl)
        start_btn = Button(text='Start', size_hint_x=0.25,
                           background_color=get_color_from_hex('#238636'))
        start_btn.bind(on_press=lambda *a: App.get_running_app().start_daemon())
        stop_btn  = Button(text='Stop',  size_hint_x=0.25,
                           background_color=get_color_from_hex('#DA3633'))
        stop_btn.bind(on_press=lambda *a: App.get_running_app().stop_daemon())
        hdr.add_widget(start_btn)
        hdr.add_widget(stop_btn)
        layout.add_widget(hdr)

        # Info cards
        self.info_lbl = Label(
            text='', font_size='12sp',
            color=get_color_from_hex('#C9D1D9'),
            size_hint_y=None, height=80,
            halign='left', valign='top',
            text_size=(Window.width - 32, None)
        )
        layout.add_widget(self.info_lbl)

        # Log path info
        self.logpath_lbl = Label(
            text=f'Log: {LOG_FILE}',
            font_size='10sp', color=get_color_from_hex('#484F58'),
            size_hint_y=None, height=28,
            halign='left', text_size=(Window.width - 32, None)
        )
        layout.add_widget(self.logpath_lbl)

        # Log view
        layout.add_widget(Label(
            text='Logs:', font_size='11sp',
            color=get_color_from_hex('#8B949E'),
            size_hint_y=None, height=20, halign='left'
        ))
        scroll = ScrollView()
        self.log_lbl = Label(
            text='', font_size='10sp',
            color=get_color_from_hex('#8B949E'),
            size_hint_y=None, halign='left', valign='top',
            text_size=(Window.width - 32, None)
        )
        self.log_lbl.bind(texture_size=self.log_lbl.setter('size'))
        scroll.add_widget(self.log_lbl)
        layout.add_widget(scroll)

        self.add_widget(layout)
        Clock.schedule_interval(self.refresh, 3)

    def refresh(self, dt):
        app = App.get_running_app()
        if app.daemon_running:
            self.status_lbl.text = 'Running'
            self.status_lbl.color = get_color_from_hex('#4CAF50')
        elif app.daemon_error:
            self.status_lbl.text = 'Erro'
            self.status_lbl.color = get_color_from_hex('#F85149')
        else:
            self.status_lbl.text = 'Stopped'
            self.status_lbl.color = get_color_from_hex('#8B949E')

        state = app.read_state()
        peers = state.get('peers', [])
        node_id = app.get_node_id_safe()
        error_line = f'\nErro: {app.daemon_error}' if app.daemon_error else ''
        self.info_lbl.text = (
            f'Node: {node_id}\n'
            f'Status: {state.get("status","offline")}   '
            f'Peers: {len(peers)}'
            f'{error_line}'
        )

        # Logs
        self.log_lbl.text = '\n'.join(_log_lines[-50:]) or 'sem logs'


# ── App ───────────────────────────────────────────────────────────────────

class CH8App(App):
    daemon_running = False
    daemon_error   = None
    _daemon_thread = None

    def build(self):
        sm = ScreenManager()
        sm.add_widget(SetupScreen(name='setup'))
        sm.add_widget(DashboardScreen(name='dashboard'))

        log.info("Checking authentication...")
        if self._is_auth():
            log.info("Already authenticated, going to dashboard")
            sm.current = 'dashboard'
            Clock.schedule_once(lambda dt: self.start_daemon(), 1)
        else:
            log.info("Not authenticated, showing setup")
            sm.current = 'setup'

        return sm

    def _is_auth(self):
        try:
            from connect.auth import is_authenticated
            result = is_authenticated()
            log.info(f"is_authenticated() = {result}")
            return result
        except Exception as e:
            log.error(f"Auth check error: {e}")
            return False

    def get_node_id_safe(self):
        try:
            from connect.auth import get_node_id
            nid = get_node_id()
            return nid[:14] + "..."
        except Exception as e:
            return f"err:{e}"

    def save_config(self, token, provider, api_key):
        """Returns error string or None on success."""
        import json

        log.info(f"Authenticating with token {token[:8]}...")
        try:
            from connect.auth import login_with_token
            result = login_with_token(token)
            log.info(f"Auth OK: network={result.get('network_id','?')}")
        except Exception as e:
            log.error(f"Auth failed: {e}")
            return str(e)

        log.info(f"Saving AI config: provider={provider}")
        try:
            cfg = {"provider": provider, "model": "auto"}
            if api_key:
                cfg["api_key"] = api_key
            (CONFIG_DIR / "ai_config.json").write_text(json.dumps(cfg))
        except Exception as e:
            log.error(f"Config write error: {e}")
            return str(e)

        log.info("Config saved OK")
        return None

    def start_daemon(self):
        if self.daemon_running:
            log.info("Daemon already running, skip")
            return

        self.daemon_error = None
        log.info("Launching daemon thread...")

        def _run():
            import asyncio
            self.daemon_running = True
            log.info("Daemon thread started")
            try:
                from connect.daemon import _main
                log.info("connect.daemon imported OK")
                asyncio.run(_main())
            except RuntimeError as e:
                if "Not authenticated" in str(e):
                    self.daemon_error = "Não autenticado — configure o token"
                    log.error(f"Daemon: not authenticated")
                else:
                    self.daemon_error = str(e)
                    log.error(f"Daemon RuntimeError: {e}")
            except Exception as e:
                self.daemon_error = str(e)
                log.error(f"Daemon crash: {e}", exc_info=True)
            finally:
                self.daemon_running = False
                log.info("Daemon thread ended")

        self._daemon_thread = threading.Thread(target=_run, daemon=True, name="ch8-daemon")
        self._daemon_thread.start()

        # Try foreground service (Android only, not fatal if fails)
        threading.Thread(target=self._try_foreground_service, daemon=True).start()

    def _try_foreground_service(self):
        try:
            from jnius import autoclass
            PythonService = autoclass('org.kivy.android.PythonService')
            mActivity = autoclass('org.kivy.android.PythonActivity').mActivity
            # Start the background service
            service_cls = autoclass('com.ch8.ch8agent.ServiceCh8daemon')
            service_cls.start(mActivity, str(CONFIG_DIR))
            log.info("Foreground service started")
        except Exception as e:
            log.info(f"Foreground service not available: {e}")

    def stop_daemon(self):
        log.info("Stop daemon requested")
        self.daemon_running = False
        try:
            from connect.daemon import get_daemon_pid
            import signal as _sig
            pid = get_daemon_pid()
            if pid:
                os.kill(pid, _sig.SIGTERM)
        except Exception:
            pass

    def read_state(self):
        import json
        try:
            return json.loads((CONFIG_DIR / "state.json").read_text())
        except Exception:
            return {"status": "offline", "peers": []}

    def on_pause(self):
        return True

    def on_resume(self):
        pass


if __name__ == '__main__':
    log.info("Starting CH8App")
    try:
        CH8App().run()
    except Exception as e:
        log.error(f"App fatal error: {e}", exc_info=True)
