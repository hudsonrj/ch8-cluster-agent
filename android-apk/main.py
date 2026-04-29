"""
CH8 Agent — Android App (Kivy-based)

Standalone APK that runs the CH8 daemon + orchestrator natively on Android.
Embeds Python + all dependencies, no Termux needed.
"""

import os
import sys
import threading
import logging
from pathlib import Path

# Set up paths BEFORE any CH8 imports
APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_DIR)

# Android app private storage
try:
    from android.storage import app_storage_path  # noqa: F401
    STORAGE_DIR = app_storage_path()
except ImportError:
    STORAGE_DIR = APP_DIR

CONFIG_DIR = Path(STORAGE_DIR) / ".config" / "ch8"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# Set environment BEFORE importing connect modules
os.environ["HOME"] = STORAGE_DIR
os.environ["CH8_CONFIG_DIR"] = str(CONFIG_DIR)
os.environ["PYTHONPATH"] = APP_DIR

# Configure file logging so daemon.log is actually written
LOG_FILE = CONFIG_DIR / "daemon.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), mode='a'),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger("ch8.android")
log.info(f"CH8 Android starting. CONFIG_DIR={CONFIG_DIR}")

from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.utils import get_color_from_hex

# Dark theme
Window.clearcolor = get_color_from_hex('#0D1117')


class SetupScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical', padding=40, spacing=20)

        layout.add_widget(Label(
            text='[b]CH8[/b] Agent',
            markup=True,
            font_size='36sp',
            color=get_color_from_hex('#58A6FF'),
            size_hint_y=None, height=60
        ))

        layout.add_widget(Label(
            text='Distributed AI Node',
            font_size='16sp',
            color=get_color_from_hex('#8B949E'),
            size_hint_y=None, height=30
        ))

        layout.add_widget(Label(size_hint_y=0.3))

        layout.add_widget(Label(
            text='Enter your network token:',
            font_size='14sp',
            color=get_color_from_hex('#C9D1D9'),
            size_hint_y=None, height=30
        ))

        self.token_input = TextInput(
            hint_text='tk_xxxxx...',
            multiline=False,
            size_hint_y=None, height=48,
            background_color=get_color_from_hex('#21262D'),
            foreground_color=get_color_from_hex('#C9D1D9'),
            cursor_color=get_color_from_hex('#58A6FF'),
            padding=[12, 12]
        )
        layout.add_widget(self.token_input)

        layout.add_widget(Label(
            text='AI Provider:',
            font_size='14sp',
            color=get_color_from_hex('#C9D1D9'),
            size_hint_y=None, height=30
        ))

        self.provider_input = TextInput(
            hint_text='groq (recommended for mobile)',
            multiline=False,
            size_hint_y=None, height=48,
            background_color=get_color_from_hex('#21262D'),
            foreground_color=get_color_from_hex('#C9D1D9'),
            cursor_color=get_color_from_hex('#58A6FF'),
            padding=[12, 12]
        )
        layout.add_widget(self.provider_input)

        self.api_key_input = TextInput(
            hint_text='API key (for Groq/OpenAI)',
            multiline=False,
            password=True,
            size_hint_y=None, height=48,
            background_color=get_color_from_hex('#21262D'),
            foreground_color=get_color_from_hex('#C9D1D9'),
            cursor_color=get_color_from_hex('#58A6FF'),
            padding=[12, 12]
        )
        layout.add_widget(self.api_key_input)

        connect_btn = Button(
            text='Connect to Network',
            size_hint_y=None, height=50,
            background_color=get_color_from_hex('#238636'),
            color=get_color_from_hex('#FFFFFF'),
            font_size='16sp'
        )
        connect_btn.bind(on_press=self.connect)
        layout.add_widget(connect_btn)

        self.status_label = Label(
            text='',
            font_size='12sp',
            color=get_color_from_hex('#F85149'),
            size_hint_y=None, height=60,
            text_size=(Window.width - 80, None)
        )
        layout.add_widget(self.status_label)

        layout.add_widget(Label(size_hint_y=0.2))

        self.add_widget(layout)

    def connect(self, instance):
        token = self.token_input.text.strip()
        if not token:
            self.status_label.text = 'Please enter a token'
            return

        provider = self.provider_input.text.strip() or 'groq'
        api_key = self.api_key_input.text.strip()

        self.status_label.color = get_color_from_hex('#58A6FF')
        self.status_label.text = 'Connecting...'

        # Run auth in background thread to avoid blocking UI
        def _do_auth():
            app = App.get_running_app()
            error = app.save_config(token, provider, api_key)
            if error:
                Clock.schedule_once(lambda dt: self._show_error(error))
            else:
                Clock.schedule_once(lambda dt: self._auth_success())

        threading.Thread(target=_do_auth, daemon=True).start()

    def _show_error(self, msg):
        self.status_label.color = get_color_from_hex('#F85149')
        self.status_label.text = msg

    def _auth_success(self):
        self.status_label.color = get_color_from_hex('#4CAF50')
        self.status_label.text = 'Connected!'
        self.manager.current = 'dashboard'
        App.get_running_app().start_daemon()


class DashboardScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.layout = BoxLayout(orientation='vertical', padding=16, spacing=10)

        # Top bar
        top = BoxLayout(size_hint_y=None, height=50, spacing=10)
        top.add_widget(Label(
            text='[b]CH8[/b] Agent',
            markup=True,
            font_size='18sp',
            color=get_color_from_hex('#58A6FF'),
            size_hint_x=0.4
        ))

        self.status_label = Label(
            text='Starting...',
            font_size='14sp',
            color=get_color_from_hex('#FFA500'),
            size_hint_x=0.3
        )
        top.add_widget(self.status_label)

        start_btn = Button(
            text='Start', size_hint_x=0.15,
            background_color=get_color_from_hex('#238636')
        )
        start_btn.bind(on_press=self.start)
        top.add_widget(start_btn)

        stop_btn = Button(
            text='Stop', size_hint_x=0.15,
            background_color=get_color_from_hex('#DA3633')
        )
        stop_btn.bind(on_press=self.stop)
        top.add_widget(stop_btn)

        self.layout.add_widget(top)

        # Info cards
        self.info_box = BoxLayout(orientation='vertical', spacing=8,
                                  size_hint_y=None, height=150)
        self.layout.add_widget(self.info_box)

        # Log output
        self.layout.add_widget(Label(
            text='Logs:', font_size='12sp',
            color=get_color_from_hex('#8B949E'),
            size_hint_y=None, height=25,
            halign='left'
        ))

        scroll = ScrollView(size_hint_y=0.6)
        self.log_label = Label(
            text='Waiting for daemon...',
            font_size='11sp',
            color=get_color_from_hex('#8B949E'),
            size_hint_y=None,
            halign='left',
            valign='top',
            text_size=(Window.width - 40, None)
        )
        self.log_label.bind(texture_size=self.log_label.setter('size'))
        scroll.add_widget(self.log_label)
        self.layout.add_widget(scroll)

        self.add_widget(self.layout)

        # Periodic status update
        Clock.schedule_interval(self.update_status, 3)

    def start(self, instance):
        App.get_running_app().start_daemon()

    def stop(self, instance):
        App.get_running_app().stop_daemon()
        self.status_label.text = 'Stopped'
        self.status_label.color = get_color_from_hex('#F44336')

    def update_status(self, dt):
        app = App.get_running_app()
        if app.daemon_running:
            self.status_label.text = 'Running'
            self.status_label.color = get_color_from_hex('#4CAF50')
        elif app.daemon_error:
            self.status_label.text = 'Error'
            self.status_label.color = get_color_from_hex('#F44336')
        else:
            self.status_label.text = 'Stopped'
            self.status_label.color = get_color_from_hex('#F44336')

        # Update info cards
        self.info_box.clear_widgets()
        state = app.read_state()
        peers = state.get('peers', [])

        self._add_card(f"Status: {state.get('status', 'offline')}")
        self._add_card(f"Node: {app.get_node_id_safe()}")
        self._add_card(f"Peers: {len(peers)}")
        for p in peers[:3]:
            self._add_card(f"  {p.get('hostname', '?')} ({p.get('address', '?')})")

        if app.daemon_error:
            self._add_card(f"Error: {app.daemon_error}", color='#F85149')

        # Update logs from file
        if LOG_FILE.exists():
            try:
                lines = LOG_FILE.read_text(errors='replace').splitlines()[-40:]
                self.log_label.text = '\n'.join(lines)
            except Exception:
                pass

    def _add_card(self, text, color='#C9D1D9'):
        self.info_box.add_widget(Label(
            text=text,
            font_size='12sp',
            color=get_color_from_hex(color),
            size_hint_y=None, height=22,
            halign='left',
            text_size=(Window.width - 40, None)
        ))


class CH8App(App):
    daemon_running = False
    daemon_error = None
    _daemon_thread = None

    def build(self):
        self.title = 'CH8 Agent'
        sm = ScreenManager()
        sm.add_widget(SetupScreen(name='setup'))
        sm.add_widget(DashboardScreen(name='dashboard'))

        if self.is_configured():
            sm.current = 'dashboard'
            Clock.schedule_once(lambda dt: self.start_daemon(), 1)
        else:
            sm.current = 'setup'

        return sm

    def is_configured(self):
        try:
            from connect.auth import is_authenticated
            return is_authenticated()
        except Exception as e:
            log.error(f"Auth check failed: {e}")
            return False

    def get_node_id_safe(self):
        try:
            from connect.auth import get_node_id
            nid = get_node_id()
            return nid[:12] + "..." if len(nid) > 12 else nid
        except Exception:
            return "unknown"

    def save_config(self, token, provider, api_key):
        """Save config. Returns error string or None on success."""
        import json

        # Auth with token
        try:
            from connect.auth import login_with_token
            login_with_token(token)
            log.info("Authentication successful")
        except Exception as e:
            log.error(f"Auth error: {e}")
            return f"Auth failed: {e}"

        # Save AI config
        try:
            ai_config = {"provider": provider, "model": "auto"}
            if api_key:
                ai_config["api_key"] = api_key
            ai_file = CONFIG_DIR / "ai_config.json"
            ai_file.write_text(json.dumps(ai_config))
            log.info(f"AI config saved: provider={provider}")
        except Exception as e:
            log.error(f"Config save error: {e}")
            return f"Config save failed: {e}"

        return None

    def start_daemon(self):
        if self.daemon_running:
            return

        self.daemon_error = None
        log.info("Starting daemon thread...")

        def _run():
            import asyncio
            self.daemon_running = True
            try:
                from connect.daemon import _main
                asyncio.run(_main())
            except SystemExit:
                # Daemon called sys.exit — treat as auth error
                self.daemon_error = "Not authenticated. Enter token in setup."
                log.error("Daemon exited: not authenticated")
            except Exception as e:
                self.daemon_error = str(e)
                log.error(f"Daemon crashed: {e}", exc_info=True)
            finally:
                self.daemon_running = False
                log.info("Daemon thread stopped")

        self._daemon_thread = threading.Thread(target=_run, daemon=True, name="ch8-daemon")
        self._daemon_thread.start()

        # Start Android foreground service if available
        self._start_foreground_service()

    def _start_foreground_service(self):
        """Start Android foreground service to prevent OS from killing us."""
        try:
            from android import mActivity
            from jnius import autoclass

            Context = autoclass('android.content.Context')
            Intent = autoclass('android.content.Intent')
            PythonService = autoclass('org.kivy.android.PythonService')

            service = autoclass('com.ch8.ch8agent.ServiceCh8daemon')
            service.start(mActivity, '')
            log.info("Android foreground service started")
        except Exception as e:
            log.warning(f"Foreground service not available (not fatal): {e}")

    def stop_daemon(self):
        self.daemon_running = False
        try:
            from connect.daemon import get_daemon_pid
            import os, signal
            pid = get_daemon_pid()
            if pid:
                os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
        log.info("Stop requested")

    def read_state(self):
        import json
        state_file = CONFIG_DIR / "state.json"
        try:
            return json.loads(state_file.read_text())
        except Exception:
            return {"status": "offline", "peers": []}

    def on_pause(self):
        return True

    def on_resume(self):
        pass


if __name__ == '__main__':
    CH8App().run()
