import os
import subprocess

import vlc
from PyQt5 import QtDBus, QtCore, QtWidgets

from lib.common import AbstractView, get_dashboard_instance, is_visible


class View(QtWidgets.QFrame, AbstractView):
    def __init__(self, url, width, height, open_url=None, stop_on_inactive=True, allow_screensaver=True, auto_restart_playback=False):
        super().__init__(None)

        self.url = url
        self.open_url = open_url
        self.auto_restart_playback_active = False

        self.dbus = QtDBus.QDBusConnection.systemBus()
        self.dbus_login_manager = QtDBus.QDBusInterface("org.freedesktop.login1", "/org/freedesktop/login1", "org.freedesktop.login1.Manager", self.dbus)

        self.dbus.connect("org.freedesktop.login1", "/org/freedesktop/login1/seat/seat0", "org.freedesktop.DBus.Properties", "PropertiesChanged", self.login_seat_changed)

        self.vlc_instance = vlc.Instance("--no-disable-screensaver" if allow_screensaver else "")

        self.setFixedSize(QtCore.QSize(width, height))

        self.media_player = None
        self.screensaver_state = False

        if auto_restart_playback:
            self.update_timer = QtCore.QTimer(self)
            self.update_timer.timeout.connect(self.update_auto_restart_playback)
            self.update_timer.start(1000)

        if stop_on_inactive:
            self.visibility_changed.connect(self.update_state_by_visibility)
            get_dashboard_instance().window_state_changed.connect(self.update_state_by_visibility)
            get_dashboard_instance().screensaver_state_changed.connect(self.screensaver_state_changed)
        else:
            self.play()

    def mouseDoubleClickEvent(self, event):
        if self.open_url is None:
            return

        subprocess.Popen(["vlc", self.open_url])

    def update_auto_restart_playback(self):
        if self.auto_restart_playback_active and (self.media_player is None or not self.media_player.is_playing()):
            self.play()

    def update_state_by_visibility(self):
        visible = is_visible(self)

        if self.screensaver_state:
            visible = False

        if visible:
            if self.media_player is None or not self.media_player.is_playing():
                self.play()
        else:
            self.stop()

    def screensaver_state_changed(self, state: bool):
        self.screensaver_state = state
        self.update_state_by_visibility()

    def play(self):
        if self.media_player is not None:
            self.media_player.release()

        self.init_media_player()

        self.media_player.set_media(self.vlc_instance.media_new(self.url))
        self.media_player.play()

        self.auto_restart_playback_active = True

    def stop(self):
        self.auto_restart_playback_active = False

        if self.media_player is not None:
            self.media_player.stop()

            self.media_player.release()
            self.media_player = None

    def init_media_player(self):
        self.media_player = self.vlc_instance.media_player_new()
        self.media_player.set_xwindow(int(self.winId()))

    @QtCore.pyqtSlot("QString", "QVariantMap")
    def login_seat_changed(self, interface, properties):
        if "ActiveSession" not in properties:
            return

        active_session_id = properties["ActiveSession"][0]

        sessions = self.dbus_login_manager.call("ListSessions").arguments()[0]

        active_session_user_id = None
        for session in sessions:
            if active_session_id == session[0]:
                active_session_user_id = session[1]
                break

        process_user_id = os.getuid()
        if active_session_user_id != process_user_id and self.media_player is not None:
            self.stop()
