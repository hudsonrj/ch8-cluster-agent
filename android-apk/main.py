"""
CH8 Agent — Android App (Kivy-based)

Standalone APK that runs the CH8 daemon + orchestrator natively on Android.
Embeds Python + all dependencies, no Termux needed.
"""

import os
import sys
import threading
import time
from pathlib import Path

# Set up paths before any CH8 imports
APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_DIR)
os.environ["HOME"] = APP_DIR
os.environ.setdefault("PYTHONPATH", APP_DIR)

# Ensure config dir exists
CONFIG_DIR = Path(APP_DIR) / ".config" / "ch8"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

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

        # Title
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

        # Spacer
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

        # AI Provider selection
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
            size_hint_y=None, height=30
        )
        layout.add_widget(self.status_label)

        # Spacer
        layout.add_widget(Label(size_hint_y=0.3))

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

        # Save config
        app = App.get_running_app()
        app.save_config(token, provider, api_key)

        # Switch to dashboard
        self.manager.current = 'dashboard'
        app.start_daemon()


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
            text='Stopped',
            font_size='14sp',
            color=get_color_from_hex('#F44336'),
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
        self.info_box = BoxLayout(orientation='vertical', spacing=8)
        self.layout.add_widget(self.info_box)

        # Log output
        self.layout.add_widget(Label(
            text='Logs:', font_size='12sp',
            color=get_color_from_hex('#8B949E'),
            size_hint_y=None, height=25,
            halign='left'
        ))

        scroll = ScrollView(size_hint_y=0.5)
        self.log_label = Label(
            text='',
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
        Clock.schedule_interval(self.update_status, 5)

    def start(self, instance):
        App.get_running_app().start_daemon()

    def stop(self, instance):
        App.get_running_app().stop_daemon()

    def update_status(self, dt):
        app = App.get_running_app()
        if app.daemon_running:
            self.status_label.text = 'Running'
            self.status_label.color = get_color_from_hex('#4CAF50')
        else:
            self.status_label.text = 'Stopped'
            self.status_label.color = get_color_from_hex('#F44336')

        # Update info
        self.info_box.clear_widgets()
        state = app.read_state()
        peers = state.get('peers', [])

        self._add_card(f"Status: {state.get('status', 'offline')}")
        self._add_card(f"Peers: {len(peers)}")
        for p in peers[:5]:
            self._add_card(f"  {p.get('hostname', '?')} ({p.get('address', '?')})")

        # Update logs
        log_path = CONFIG_DIR / "daemon.log"
        if log_path.exists():
            try:
                lines = log_path.read_text(errors='replace').splitlines()[-30:]
                self.log_label.text = '\n'.join(lines)
            except Exception:
                pass

    def _add_card(self, text):
        self.info_box.add_widget(Label(
            text=text,
            font_size='13sp',
            color=get_color_from_hex('#C9D1D9'),
            size_hint_y=None, height=25,
            halign='left'
        ))


class CH8App(App):
    daemon_running = False
    _daemon_thread = None

    def build(self):
        self.title = 'CH8 Agent'
        sm = ScreenManager()
        sm.add_widget(SetupScreen(name='setup'))
        sm.add_widget(DashboardScreen(name='dashboard'))

        # Check if already configured
        if self.is_configured():
            sm.current = 'dashboard'
            self.start_daemon()
        else:
            sm.current = 'setup'

        return sm

    def is_configured(self):
        from connect.auth import is_authenticated
        return is_authenticated()

    def save_config(self, token, provider, api_key):
        import json

        # Auth with token
        try:
            from connect.auth import login_with_token
            login_with_token(token)
        except Exception as e:
            print(f"Auth error: {e}")

        # Save AI config
        ai_config = {"provider": provider, "model": "auto"}
        if api_key:
            ai_config["api_key"] = api_key
        ai_file = CONFIG_DIR / "ai_config.json"
        ai_file.write_text(json.dumps(ai_config))

    def start_daemon(self):
        if self.daemon_running:
            return

        def _run():
            import asyncio
            from connect.daemon import _main
            self.daemon_running = True
            try:
                asyncio.run(_main())
            except Exception as e:
                print(f"Daemon error: {e}")
            finally:
                self.daemon_running = False

        self._daemon_thread = threading.Thread(target=_run, daemon=True)
        self._daemon_thread.start()

    def stop_daemon(self):
        self.daemon_running = False
        # Daemon will stop on next heartbeat cycle

    def read_state(self):
        import json
        state_file = CONFIG_DIR / "state.json"
        try:
            return json.loads(state_file.read_text())
        except Exception:
            return {"status": "offline", "peers": []}

    def on_pause(self):
        # Allow app to keep running in background on Android
        return True

    def on_resume(self):
        pass


if __name__ == '__main__':
    CH8App().run()
