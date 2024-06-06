import os
import signal
import subprocess

import Xlib.display
from PyQt5 import QtWidgets, QtGui, QtCore

from lib.common import AbstractView


class View(QtWidgets.QWidget, AbstractView):
    def __init__(self, command_line: str, window_selector: dict, max_window_searches: int = 10):
        super().__init__()

        self.command_line = command_line
        self.window_selector = window_selector
        self.remaining_window_searches = max_window_searches

        self.process = None

        self.layout = QtWidgets.QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.layout)

        self.wait_window_timer = QtCore.QTimer(self)
        self.wait_window_timer.setInterval(1000)
        self.wait_window_timer.timeout.connect(self.handle_wait_window_timer)

    def start_view(self):
        self.process = subprocess.Popen(self.command_line, shell=True, stdout=subprocess.PIPE, preexec_fn=os.setsid)
        self.wait_window_timer.start()

    def stop_view(self):
        self.wait_window_timer.stop()
        os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)

    def handle_wait_window_timer(self):
        self.remaining_window_searches = self.remaining_window_searches - 1

        if self.steal_window() or self.remaining_window_searches <= 0:
            self.wait_window_timer.stop()

    def steal_window(self):
        window_id = self.get_window_id()
        if window_id is None:
            return False

        window = QtGui.QWindow.fromWinId(window_id)
        if window is None:
            return False

        widget = QtWidgets.QWidget.createWindowContainer(window)
        widget.setContentsMargins(0, 0, 0, 0)
        self.layout.addWidget(widget)
        return True

    def get_window_id(self):
        display = Xlib.display.Display()
        root = display.screen().root

        window_ids = root.get_full_property(display.intern_atom("_NET_CLIENT_LIST"), Xlib.X.AnyPropertyType).value

        for window_id in window_ids:
            window = display.create_resource_object("window", window_id)
            app_name, class_name = window.get_wm_class()
            window_name = window.get_wm_name()

            if self.check_window_selector("app", app_name) or self.check_window_selector("class", class_name) or self.check_window_selector("title", window_name):
                return window_id

            title_contains = self.window_selector.get("title_contains")
            if title_contains is not None and title_contains in window_name:
                return window_id

        return None

    def check_window_selector(self, selector: str, string: str):
        value = self.window_selector.get(selector)
        if value is None:
            return False

        return value == string
