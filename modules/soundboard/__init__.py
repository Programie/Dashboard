import os
import random
from glob import glob
from typing import List

from PyQt5 import QtWidgets, QtCore, QtMultimedia

from lib.common import AbstractView


class SoundButton(QtWidgets.QWidget, AbstractView):
    toggled = QtCore.pyqtSignal(bool)

    def __init__(self, urls: List[QtCore.QUrl], text: str, volume: int):
        super().__init__()

        urls = sorted(urls, key=lambda url_item: url_item.fileName())

        self.media_player = QtMultimedia.QMediaPlayer()
        self.media_player.setVolume(volume)
        self.media_player.stateChanged.connect(self.state_changed)

        self.urls = urls
        self.previous_url = None

        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)

        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        button_container_layout = QtWidgets.QHBoxLayout()
        button_container_layout.setContentsMargins(0, 0, 0, 0)
        button_container_layout.setSpacing(0)
        layout.addLayout(button_container_layout)

        self.button = QtWidgets.QPushButton(text)
        self.button.setCheckable(True)
        self.button.released.connect(self.play)
        button_container_layout.addWidget(self.button, 1)

        if len(urls) > 1:
            dropdown_button = QtWidgets.QPushButton()
            dropdown_button.setFixedWidth(25)
            button_container_layout.addWidget(dropdown_button, 0)

            dropdown_menu = QtWidgets.QMenu()
            dropdown_button.setMenu(dropdown_menu)

            for url in urls:
                self.add_dropdown_item(dropdown_menu, url)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setFixedHeight(3)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        size_policy = self.progress_bar.sizePolicy()
        size_policy.setRetainSizeWhenHidden(True)
        self.progress_bar.setSizePolicy(size_policy)

    def set_checked(self, state: bool):
        self.button.setChecked(state)

    def update_progressbar(self):
        self.progress_bar.setMaximum(self.media_player.duration())
        self.progress_bar.setValue(self.media_player.position())
        self.progress_bar.setVisible(self.button.isChecked())

    def state_changed(self, state):
        if state == QtMultimedia.QMediaPlayer.StoppedState:
            self.button.setChecked(False)
            self.progress_bar.setVisible(False)
        else:
            self.button.setChecked(True)

    def add_dropdown_item(self, dropdown_menu: QtWidgets.QMenu, url: QtCore.QUrl):
        dropdown_menu.addAction(url.fileName()).triggered.connect(lambda: self.play_url(url))

    def play_url(self, url: QtCore.QUrl):
        self.previous_url = url

        self.media_player.setMedia(QtMultimedia.QMediaContent(url))
        self.media_player.play()

    def play(self):
        if self.button.isChecked():
            url = random.choice(self.urls)

            if len(self.urls) > 1:
                for random_try in range(10):
                    if self.previous_url is None or self.previous_url != url:
                        break

                    url = random.choice(self.urls)

            self.play_url(url)
        else:
            self.media_player.stop()


class View(QtWidgets.QWidget):
    def __init__(self, base_path, sounds, max_columns=5):
        super().__init__()

        self.media_players = {}
        self.buttons = []
        self.previous_url = {}

        self.row = 0
        self.column = 0
        self.max_columns = max_columns

        self.layout = QtWidgets.QGridLayout()
        self.setLayout(self.layout)

        for sound in sounds:
            files = sound["file"]

            if not isinstance(files, list):
                files = [files]

            resolved_files = []

            for file in files:
                if "*" in file:
                    resolved_files.extend(glob(os.path.join(base_path, file)))
                elif "://" not in file:
                    resolved_files.append(os.path.join(base_path, file))
                else:
                    resolved_files.append(file)

            urls = []

            for file in resolved_files:
                if "://" in file:
                    url = QtCore.QUrl(file)
                else:
                    url = QtCore.QUrl.fromLocalFile(file)

                urls.append(url)

            self.add_sound(urls, sound["title"], sound.get("volume", 100))

        timer = QtCore.QTimer(self)
        timer.timeout.connect(self.update_progressbars)
        timer.start(50)

    def add_sound(self, urls: List[QtCore.QUrl], title: str, volume: int):
        button = SoundButton(urls, title, volume)

        self.layout.addWidget(button, self.row, self.column)
        self.buttons.append(button)

        if self.column == self.max_columns - 1:
            self.column = 0
            self.row += 1
        else:
            self.column += 1

    def update_progressbars(self):
        for button in self.buttons:
            button.update_progressbar()
