import traceback

import requests
from PyQt5 import QtWidgets, QtCore, QtDBus, QtGui

from lib.common import Timer, AbstractView


class View(QtWidgets.QWidget, AbstractView):
    def __init__(self):
        super().__init__()

        self.old_art_url = 1

        # Required to allow setting pixmap as background
        self.setAutoFillBackground(True)

        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)

        self.player_dropdown = QtWidgets.QComboBox()
        layout.addWidget(self.player_dropdown)

        layout.addWidget(QtWidgets.QWidget(), 1)

        self.artist_label = QtWidgets.QLabel()
        self.artist_label.setAlignment(QtCore.Qt.AlignCenter)
        self.artist_label.setWordWrap(True)
        layout.addWidget(self.artist_label)

        self.title_label = QtWidgets.QLabel()
        self.title_label.setAlignment(QtCore.Qt.AlignCenter)
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)

        control_buttons = QtWidgets.QWidget()
        control_buttons_layout = QtWidgets.QHBoxLayout()
        control_buttons.setLayout(control_buttons_layout)
        layout.addWidget(control_buttons)

        self.previous_button = QtWidgets.QPushButton(QtGui.QIcon.fromTheme("media-skip-backward-symbolic"), "")
        self.previous_button.clicked.connect(lambda: self.control_action("Previous"))
        control_buttons_layout.addWidget(self.previous_button)

        self.play_button = QtWidgets.QPushButton(QtGui.QIcon.fromTheme("media-playback-start-symbolic"), "")
        self.play_button.clicked.connect(lambda: self.control_action("Play"))
        control_buttons_layout.addWidget(self.play_button)

        self.pause_button = QtWidgets.QPushButton(QtGui.QIcon.fromTheme("media-playback-pause-symbolic"), "")
        self.pause_button.clicked.connect(lambda: self.control_action("Pause"))
        control_buttons_layout.addWidget(self.pause_button)

        self.stop_button = QtWidgets.QPushButton(QtGui.QIcon.fromTheme("media-playback-stop-symbolic"), "")
        self.stop_button.clicked.connect(lambda: self.control_action("Stop"))
        control_buttons_layout.addWidget(self.stop_button)

        self.next_button = QtWidgets.QPushButton(QtGui.QIcon.fromTheme("media-skip-forward-symbolic"), "")
        self.next_button.clicked.connect(lambda: self.control_action("Next"))
        control_buttons_layout.addWidget(self.next_button)

        self.progress_bar = QtWidgets.QProgressBar()
        layout.addWidget(self.progress_bar)

        self.bus = QtDBus.QDBusConnection.sessionBus()

        timer = Timer(self, 1000, self)
        timer.timeout.connect(self.update_data)

    def update_data(self):
        selected_service = self.player_dropdown.currentData(QtCore.Qt.UserRole)

        services_info_data = {}
        playing_service = None

        for service in self.get_player_services():
            info_data = self.get_service_info_data(service)

            services_info_data[service] = info_data

            if info_data.get("PlaybackStatus") == "Playing":
                playing_service = service

        if not selected_service or selected_service not in services_info_data:
            selected_service = playing_service

        if selected_service and services_info_data[selected_service].get("PlaybackStatus") != "Playing":
            selected_service = playing_service

        self.player_dropdown.clear()

        if services_info_data:
            for service, info_data in services_info_data.items():
                self.player_dropdown.addItem(self.get_service_identity(service), service)

                if not selected_service or service == selected_service:
                    selected_service = service

                    self.set_info(info_data)
                    self.player_dropdown.setCurrentIndex(self.player_dropdown.count() - 1)
        else:
            self.show_nothing_playing()

    def get_service_info_data(self, service):
        return self.get_dbus_interface(service, "org.freedesktop.DBus.Properties").call("GetAll", "org.mpris.MediaPlayer2.Player").arguments()[0]

    def get_service_identity(self, service):
        return self.get_dbus_interface(service, "org.freedesktop.DBus.Properties").call("Get", "org.mpris.MediaPlayer2", "Identity").arguments()[0]

    def set_info(self, info_data):
        meta_data = info_data.get("Metadata", {})

        length_seconds = 0
        if "mpris:length" in meta_data:
            self.progress_bar.setMaximum(meta_data["mpris:length"])
            length_seconds = int(meta_data["mpris:length"] / 1000000)

        position = info_data.get("Position", 0)
        self.progress_bar.setValue(position)

        length_hours, length_minutes, length_seconds = self.split_seconds(length_seconds)
        position_hours, position_minutes, position_seconds = self.split_seconds(int(position / 1000000))

        if length_hours:
            progress_string = "{:02d}:{:02d}:{:02d} / {:02d}:{:02d}:{:02d}".format(position_hours, position_minutes, position_seconds, length_hours, length_minutes, length_seconds)
        else:
            progress_string = "{:02d}:{:02d} / {:02d}:{:02d}".format(position_minutes, position_seconds, length_minutes, length_seconds)

        self.progress_bar.setFormat(progress_string)

        if "xesam:title" in meta_data and meta_data["xesam:title"]:
            self.artist_label.setText(", ".join(meta_data.get("xesam:artist", "")))
            self.title_label.setText(meta_data["xesam:title"])
            self.progress_bar.setVisible(True)
        elif "xesam:url" in meta_data and meta_data["xesam:url"]:
            self.artist_label.setText("")
            self.title_label.setText(meta_data["xesam:url"])
            self.progress_bar.setVisible(True)
        else:
            self.show_nothing_playing()

        if "mpris:artUrl" in meta_data and meta_data["mpris:artUrl"]:
            art_url = meta_data["mpris:artUrl"]
        else:
            art_url = None

        if self.old_art_url != art_url:
            self.old_art_url = art_url

            brush = None

            if art_url is not None:
                try:
                    url = QtCore.QUrl.fromUserInput(art_url)
                    if url.isLocalFile():
                        pixmap = QtGui.QPixmap(url.path())
                    else:
                        pixmap = QtGui.QPixmap()
                        pixmap.loadFromData(requests.get(url.toString()).content)

                    brush = QtGui.QBrush(pixmap.scaled(self.size(), QtCore.Qt.KeepAspectRatioByExpanding))
                except:
                    traceback.print_exc()

            if not brush:
                brush = QtGui.QBrush()

            palette = self.palette()
            palette.setBrush(QtGui.QPalette.Background, brush)
            self.setPalette(palette)

        self.previous_button.setEnabled(info_data.get("CanGoPrevious", False))
        self.next_button.setEnabled(info_data.get("CanGoNext", False))

        is_playing = info_data.get("PlaybackStatus") == "Playing"

        self.pause_button.setVisible(is_playing)
        self.play_button.setVisible(not is_playing)

        if is_playing:
            self.pause_button.setEnabled(info_data.get("CanPause", False))
        else:
            self.play_button.setEnabled(info_data.get("CanPlay", False))

    def show_nothing_playing(self):
        self.artist_label.setText("")
        self.title_label.setText("Nothing playing")
        self.progress_bar.setVisible(False)
        self.previous_button.setEnabled(False)
        self.pause_button.setEnabled(False)
        self.play_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.next_button.setEnabled(False)

    def get_player_services(self):
        service: str
        for service in self.bus.interface().registeredServiceNames().value():
            if service.startswith("org.mpris.MediaPlayer2."):
                yield service

    def get_dbus_interface(self, service, interface):
        return QtDBus.QDBusInterface(service, "/org/mpris/MediaPlayer2", interface, self.bus)

    def control_action(self, method):
        service = self.player_dropdown.currentData(QtCore.Qt.UserRole)

        if not service:
            return

        self.get_dbus_interface(service, "org.mpris.MediaPlayer2.Player").call(method)

    @staticmethod
    def split_seconds(seconds):
        return seconds // 3600 % 24, seconds // 60 % 60, seconds % 60
