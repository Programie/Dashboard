import os

from PyQt5 import QtMultimediaWidgets, QtMultimedia, QtCore, QtDBus

from lib.common import AbstractView, get_dashboard_instance, is_visible


class View(QtMultimediaWidgets.QVideoWidget, AbstractView):
    def __init__(self, url, width=None, height=None, stop_on_inactive=True, auto_restart_playback=False):
        super().__init__()

        self.url = url
        self.screensaver_state = False
        self.playing = False

        self.dbus = QtDBus.QDBusConnection.systemBus()
        self.dbus_login_manager = QtDBus.QDBusInterface("org.freedesktop.login1", "/org/freedesktop/login1", "org.freedesktop.login1.Manager", self.dbus)

        self.dbus.connect("org.freedesktop.login1", "/org/freedesktop/login1/seat/seat0", "org.freedesktop.DBus.Properties", "PropertiesChanged", self.login_seat_changed)

        if width and height:
            self.setFixedSize(QtCore.QSize(width, height))

        self.player = QtMultimedia.QMediaPlayer(self)
        self.player.setVideoOutput(self)

        if auto_restart_playback:
            self.player.stateChanged.connect(self.state_changed)

        if stop_on_inactive:
            self.visibility_changed.connect(self.update_state_by_visibility)
            get_dashboard_instance().window_state_changed.connect(self.update_state_by_visibility)
            get_dashboard_instance().screensaver_state_changed.connect(self.screensaver_state_changed)
        else:
            self.play()

    def state_changed(self, new_state: QtMultimedia.QMediaPlayer.State):
        print("state_changed", new_state)
        if self.playing and new_state != QtMultimedia.QMediaPlayer.State.PlayingState:
            self.play()

    def update_state_by_visibility(self):
        visible = is_visible(self)

        if self.screensaver_state:
            visible = False

        print("visible", visible)

        if visible:
            if self.player.state() != QtMultimedia.QMediaPlayer.State.PlayingState:
                self.play()
        else:
            self.stop()

    def screensaver_state_changed(self, state: bool):
        self.screensaver_state = state
        self.update_state_by_visibility()

    def play(self):
        self.player.setMedia(QtMultimedia.QMediaContent(QtCore.QUrl(self.url)))

        self.playing = True
        self.player.play()
        print("play")

    def stop(self):
        self.playing = False
        self.player.stop()
        print("stop")

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
