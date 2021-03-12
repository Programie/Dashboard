#! /usr/bin/env python3
import importlib
import inspect
import signal
import traceback
from typing import Dict, List, Tuple

import os
import sys

import dbus
import dbus.mainloop.glib
import dbus.service
import yaml

from PyQt5 import QtWidgets, QtGui, QtCore

from lib.common import AbstractView

modules = {}


class TabWidget(QtWidgets.QTabWidget):
    def __init__(self):
        super().__init__()

        self.tab_titles = {}

    def add_tab(self, widget, title, tab_id=None):
        tab_index = self.addTab(widget, title)

        self.tab_titles[tab_index] = title

        if tab_id is not None:
            Dashboard.instance.tabs[tab_id] = (self, tab_index)

        return tab_index

    def append_tab_title(self, index, title: str = None):
        if title is None:
            title = self.tab_titles[index]
        else:
            title = "".join([self.tab_titles[index], title])

        self.setTabText(index, title)


class WidgetContainer:
    def __init__(self, config: dict, create_widget: callable):
        self.config = config
        self.create_widget = create_widget

    def container(self):
        widget = QtWidgets.QWidget()

        if self.config["orientation"] == "vertical":
            layout = QtWidgets.QVBoxLayout()
        else:
            layout = QtWidgets.QHBoxLayout()

        layout.setContentsMargins(0, 0, 0, 0)
        widget.setLayout(layout)

        stretch_widgets = self.config.get("stretch", [])
        fixed_widget_sizes = self.config.get("sizes", [])

        for index, child_widget in enumerate(self.config["widgets"]):
            child_widget_instance: QtWidgets.QWidget = self.create_widget(child_widget)

            if len(stretch_widgets) - 1 > index:
                stretch = stretch_widgets[index]
            else:
                stretch = 0

            if len(fixed_widget_sizes) - 1 > index and fixed_widget_sizes[index]:
                child_widget_instance.setFixedWidth(fixed_widget_sizes[index])

            layout.addWidget(child_widget_instance, stretch=stretch)

        return widget

    def groupbox(self):
        widget = QtWidgets.QGroupBox()
        widget.setTitle(self.config["title"])

        layout = QtWidgets.QStackedLayout()
        widget.setLayout(layout)
        layout.addWidget(self.create_widget(self.config["widgets"][0]))

        return widget

    def splitter(self):
        widget = QtWidgets.QSplitter()

        if self.config["orientation"] == "vertical":
            widget.setOrientation(QtCore.Qt.Vertical)
        else:
            widget.setOrientation(QtCore.Qt.Horizontal)

        for child_widget in self.config["widgets"]:
            widget.addWidget(self.create_widget(child_widget))

        if "sizes" in self.config:
            widget.setSizes(self.config["sizes"])

        return widget

    def tabs(self):
        widget = TabWidget()

        for child_widget in self.config["widgets"]:
            if "tab_title" in child_widget:
                tab_title = child_widget["tab_title"]
                del child_widget["tab_title"]
            else:
                tab_title = child_widget["type"]

            if "tab_id" in child_widget:
                tab_id = child_widget["tab_id"]
                del child_widget["tab_id"]
            else:
                tab_id = None

            widget.add_tab(self.create_widget(child_widget), tab_title, tab_id)

        if "active_tab" in self.config:
            widget.setCurrentIndex(self.config["active_tab"])

        return widget


class Dashboard(QtWidgets.QMainWindow):
    instance: "Dashboard" = None

    def __init__(self, config_filepath: str, screens: List[QtGui.QScreen], session_dbus: dbus.Bus):
        super().__init__()

        Dashboard.instance = self

        self.session_dbus = session_dbus
        self.tabs: Dict[str, Tuple[TabWidget, int]] = {}
        self.widget_instances: Dict[str, List[AbstractView]] = {}
        self.error_message = QtWidgets.QErrorMessage(self)

        self.splash_screen = QtWidgets.QSplashScreen(QtGui.QPixmap(os.path.join(os.path.dirname(os.path.realpath(__file__)), "images", "splash.png")))
        self.splash_screen.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint)
        self.splash_screen.show()
        self.update_splash_screen("Loading...")

        with open(config_filepath, "r") as config_file:
            config = yaml.safe_load(config_file)

            window_options = config.get("window_options", {})

            screen = window_options.get("screen", None)
            if screen is not None:
                screen = screens[screen]

                screen_geometry: QtCore.QRect = screen.geometry()
                self.move(screen_geometry.x(), screen_geometry.y())

            size = window_options.get("size")

            window_flags = QtCore.Qt.Window

            if window_options.get("stay_on_bottom", False):
                window_flags |= QtCore.Qt.WindowStaysOnBottomHint

            if window_options.get("frameless", True):
                window_flags |= QtCore.Qt.FramelessWindowHint
            else:
                window_flags |= QtCore.Qt.WindowMinimizeButtonHint | QtCore.Qt.WindowCloseButtonHint

            if window_options.get("tool", False):
                window_flags |= QtCore.Qt.Tool

            if window_options.get("allow_resize", False):
                window_flags |= QtCore.Qt.WindowMaximizeButtonHint

                if size:
                    self.resize(size[0], size[1])
            else:
                if size:
                    self.setFixedSize(size[0], size[1])

            self.setWindowFlags(window_flags)

            if window_options.get("maximize", True):
                self.showMaximized()

            self.setCentralWidget(self.create_widget(config["central_widget"]))

            widget_instance: AbstractView
            for widget_instances in self.widget_instances.values():
                for widget_instance in widget_instances:
                    if hasattr(widget_instance, "start_view"):
                        widget_instance.start_view()

        self.splash_screen.hide()

    def create_widget(self, config):
        widget_type = config["type"]

        self.update_splash_screen("Creating widget '{}'".format(widget_type))

        widget = None

        widget_container_helper = WidgetContainer(config, self.create_widget)
        if hasattr(widget_container_helper, widget_type):
            method = getattr(widget_container_helper, widget_type)
            if callable(method):
                widget = method()

        if widget is None:
            module = modules[widget_type]

            options = dict(config)
            del options["type"]

            parameters = inspect.signature(module.View.__init__).parameters
            if "dashboard_instance" in parameters:
                options["dashboard_instance"] = self

            widget = module.View(**options)

        if widget_type not in self.widget_instances:
            self.widget_instances[widget_type] = []

        self.widget_instances[widget_type].append(widget)

        return widget

    def tab_by_id(self, tab_id):
        return self.tabs.get(tab_id, (None, 0))

    def get_widget_instance(self, name, index=0):
        instances = self.widget_instances.get(name)

        if instances is None or len(instances) - 1 < index:
            return None

        return instances[index]

    def show_error(self, message: str):
        self.error_message.showMessage(message, message)

    def update_splash_screen(self, message: str):
        self.splash_screen.showMessage(message, color=QtCore.Qt.white)
        QtCore.QCoreApplication.processEvents()

    def closeEvent(self, event: QtGui.QCloseEvent):
        QtWidgets.QApplication.quit()


def import_modules(config):
    widget_type = config["type"]

    if hasattr(WidgetContainer, widget_type):
        for child_widget in config["widgets"]:
            import_modules(child_widget)
    else:
        if widget_type not in modules:
            modules[widget_type] = importlib.import_module("modules.{}".format(widget_type))


def exception_hook(exception_type, exception_value, exception_traceback):
    traceback_string = "".join(traceback.format_exception(exception_type, exception_value, exception_traceback))
    print(traceback_string, file=sys.stderr)

    if Dashboard.instance:
        Dashboard.instance.show_error(traceback_string)
    else:
        error_message = QtWidgets.QErrorMessage()
        error_message.showMessage(traceback_string, traceback_string)
        error_message.exec()


def main():
    if len(sys.argv) > 1:
        config_filepath = sys.argv[1]
    else:
        config_filepath = "~/.config/dashboard.yml"

    config_filepath = os.path.expanduser(config_filepath)

    with open(config_filepath, "r") as config_file:
        config = yaml.safe_load(config_file)

        pid_file = config.get("pid_file", "~/.cache/dashboard.pid")

        if isinstance(pid_file, str):
            pid_file = os.path.expanduser(pid_file)
        else:
            pid_file = None

        import_modules(config["central_widget"])

    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("Dashboard")

    # Prevent closing main window if it is a tool window and a sub window is closed
    app.setQuitOnLastWindowClosed(False)

    sys.excepthook = exception_hook

    try:
        if pid_file is not None:
            if os.path.exists(pid_file):
                try:
                    with open(pid_file, "r") as pid_file_stream:
                        pid = int(pid_file_stream.readline().strip())
                        if pid:
                            os.kill(pid, signal.SIGTERM)
                except:
                    pass

            with open(pid_file, "w") as pid_file_stream:
                pid_file_stream.write(str(app.applicationPid()))

        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        session_bus = dbus.SessionBus()

        # Returned value must be stored in a variable even if not used?!
        bus = dbus.service.BusName("com.selfcoders.Dashboard", session_bus)

        dashboard = Dashboard(config_filepath, app.screens(), session_bus)
        dashboard.show()

        exit_code = app.exec()
    finally:
        if pid_file is not None and os.path.exists(pid_file):
            os.remove(pid_file)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
