import os

from PyQt5 import QtMultimediaWidgets, QtMultimedia, QtCore, QtDBus

from lib.common import AbstractView, get_dashboard_instance, is_visible


class View(QtMultimediaWidgets.QVideoWidget, AbstractView):
    def __init__(self, url, width=None, height=None, stop_on_inactive=True, auto_restart_playback=False, auto_restart_playback_on_error=False):
        super().__init__()

        self.url = url
        self.screensaver_state = False
        self.playing = False

        self.dbus = QtDBus.QDBusConnection.systemBus()
        self.dbus_login_manager = QtDBus.QDBusInterface("org.freedesktop.login1", "/org/freedesktop/login1", "org.freedesktop.login1.Manager", self.dbus)

        self.dbus.connect("org.freedesktop.login1", "/org/freedesktop/login1/seat/seat0", "org.freedesktop.DBus.Properties", "PropertiesChanged", self.login_seat_changed)
        self.dbus.connect("org.freedesktop.login1", "/org/freedesktop/login1", "org.freedesktop.login1.Manager", "PrepareForSleep", self.prepare_for_sleep_changed)

        if width and height:
            self.setFixedSize(QtCore.QSize(width, height))

        self.player = QtMultimedia.QMediaPlayer(self)
        self.player.setVideoOutput(self)

        if auto_restart_playback:
            self.player.stateChanged.connect(self.state_changed)

        if auto_restart_playback_on_error:
            self.player.error.connect(self.on_error)

        if stop_on_inactive:
            self.visibility_changed.connect(self.update_state_by_visibility)
            get_dashboard_instance().window_state_changed.connect(self.update_state_by_visibility)
            get_dashboard_instance().screensaver_state_changed.connect(self.screensaver_state_changed)
        else:
            self.play()

    def on_error(self):
        if self.playing:
            self.stop()
            self.play()

    def state_changed(self, new_state: QtMultimedia.QMediaPlayer.State):
        if self.playing and new_state != QtMultimedia.QMediaPlayer.State.PlayingState:
            self.play()

    def update_state_by_visibility(self):
        visible = is_visible(self)

        if self.screensaver_state:
            visible = False

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

    def stop(self):
        self.playing = False
        self.player.stop()

    @QtCore.pyqtSlot(bool)
    def prepare_for_sleep_changed(self, state):
        if not state and self.playing:
            # Restart playback after waking up from suspend if previously played back
            self.player.stop()
            self.player.play()

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
        if active_session_user_id != process_user_id and self.player is not None:
            self.stop()
