import os
import subprocess

import vlc
from PyQt5 import QtDBus, QtCore, QtWidgets

from lib.common import AbstractView


class View(QtWidgets.QFrame, AbstractView):
    def __init__(self, url, width, height, open_url=None, stop_on_inactive=True, allow_screensaver=True):
        super().__init__(None)

        self.url = url

        if open_url is not None:
            self.open_url = open_url
        else:
            self.open_url = url

        self.dbus = QtDBus.QDBusConnection.systemBus()
        self.dbus_login_manager = QtDBus.QDBusInterface("org.freedesktop.login1", "/org/freedesktop/login1", "org.freedesktop.login1.Manager", self.dbus)

        self.dbus.connect("org.freedesktop.login1", "/org/freedesktop/login1/seat/seat0", "org.freedesktop.DBus.Properties", "PropertiesChanged", self.login_seat_changed)

        self.vlc_instance = vlc.Instance("--no-disable-screensaver" if allow_screensaver else "")

        self.setFixedSize(QtCore.QSize(width, height))

        self.media_player = None
        self.init_media_player()

        if stop_on_inactive:
            self.visibility_changed.connect(self.set_playing_state)
        else:
            self.play()

    def mouseDoubleClickEvent(self, event):
        subprocess.Popen(["vlc", self.open_url])

    def set_playing_state(self, state: bool):
        if state:
            self.play()
        else:
            self.stop()

    def play(self):
        self.media_player.set_media(self.vlc_instance.media_new(self.url))
        self.media_player.play()

    def stop(self):
        self.media_player.stop()

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
        if active_session_user_id == process_user_id:
            if self.media_player is None:
                self.init_media_player()
        else:
            if self.media_player is not None:
                self.media_player.release()
                self.media_player = None
