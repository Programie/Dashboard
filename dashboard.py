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

from PyQt5 import QtWidgets, QtGui, QtCore, QtDBus
from PyQt5.QtWidgets import QTabWidget

from lib.common import AbstractView, set_dashboard_instance, get_dashboard_instance, AbstractPlugin

modules = {}


class DBusHandler(dbus.service.Object):
    def __init__(self, dashboard_instance: "Dashboard", session_bus: dbus.Bus):
        dbus.service.Object.__init__(self, session_bus, "/")

        self.dashboard_instance = dashboard_instance

    @dbus.service.method("com.selfcoders.Dashboard", in_signature="b", out_signature="")
    def fake_screensaver(self, state: bool):
        self.dashboard_instance.screensaver_active_changed(state)


class Dashboard(QtWidgets.QMainWindow, AbstractView):
    instance: "Dashboard" = None
    screensaver_state_changed = QtCore.pyqtSignal(bool)
    window_state_changed = QtCore.pyqtSignal(QtCore.Qt.WindowState)
    screensaver_active = False
    window_active = False

    def __init__(self, config_filepath: str, screens: List[QtGui.QScreen], session_dbus: dbus.Bus):
        super().__init__()

        set_dashboard_instance(self)

        self.overlay_widget = None

        self.session_dbus = session_dbus
        self.tabs: Dict[str, Tuple[QTabWidget, int]] = {}
        self.widget_instances: Dict[str, List[AbstractView]] = {}
        self.plugin_instances: Dict[str, List[AbstractPlugin]] = {}
        self.error_message = QtWidgets.QErrorMessage(self)

        self.splash_screen = QtWidgets.QSplashScreen(QtGui.QPixmap(os.path.join(os.path.dirname(os.path.realpath(__file__)), "images", "splash.png")))
        self.splash_screen.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint)
        self.splash_screen.show()
        self.update_splash_screen("Loading...")

        with open(config_filepath, "r") as config_file:
            config = yaml.safe_load(config_file)

            self.show_error_messages = config.get("show_error_messages", True)

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

            font_options = config.get("font", {})
            font = self.font()

            if "family" in font_options:
                font.setFamily(font_options.get("family"))

            if "size" in font_options:
                font.setPointSize(font_options.get("size"))

            self.setFont(font)

            if window_options.get("maximize", True):
                self.showMaximized()

            self.setCentralWidget(self.create_widget(config["central_widget"]))

            widget_instance: AbstractView
            for widget_instances in self.widget_instances.values():
                for widget_instance in widget_instances:
                    if hasattr(widget_instance, "start_view"):
                        widget_instance.start_view()

            if "overlay_widget" in config:
                self.overlay_widget: QtWidgets.QWidget = self.create_widget(config["overlay_widget"])
                self.overlay_widget.setParent(self)
                self.overlay_widget.size_changed.connect(self.move_overlay_widget)
                self.move_overlay_widget()

            if "plugins" in config:
                for plugin in config["plugins"]:
                    self.init_plugin(plugin)

        self.size_changed.connect(self.move_overlay_widget)

        self.register_screensaver_events()

        self.splash_screen.hide()

        self.window_active = not bool(self.windowState() & QtCore.Qt.WindowMinimized)
        self.window_state_changed.emit(self.windowState())

        DBusHandler(self, self.session_dbus)

    def move_overlay_widget(self):
        if self.overlay_widget is None:
            return

        size = self.overlay_widget.size()

        x = int(self.width() / 2 - size.width() / 2)
        y = int(self.height() / 2 - size.height() / 2)

        if x < 0:
            x = 0

        if y < 0:
            y = 0

        self.overlay_widget.move(x, y)

    def create_widget(self, config):
        widget_type = config["type"]

        self.update_splash_screen("Creating widget '{}'".format(widget_type))

        module = modules[widget_type]

        options = dict(config)
        del options["type"]

        if "size" in options:
            widget_size = QtCore.QSize(options["size"][0], options["size"][1])
            del options["size"]
        else:
            widget_size = None

        parameters = inspect.signature(module.View.__init__).parameters
        if "dashboard_instance" in parameters:
            options["dashboard_instance"] = self

        widget = module.View(**options)

        if widget_size:
            widget.resize(widget_size)

        if widget_type not in self.widget_instances:
            self.widget_instances[widget_type] = []

        self.widget_instances[widget_type].append(widget)

        return widget

    def init_plugin(self, config):
        plugin_type = config["type"]

        self.update_splash_screen("Loading plugin '{}'".format(plugin_type))

        module = modules[plugin_type]

        options = dict(config)
        del options["type"]

        parameters = inspect.signature(module.Plugin.__init__).parameters
        if "dashboard_instance" in parameters:
            options["dashboard_instance"] = self

        plugin = module.Plugin(**options)

        if plugin_type not in self.plugin_instances:
            self.plugin_instances[plugin_type] = []

        self.plugin_instances[plugin_type].append(plugin)

    def tab_by_id(self, tab_id):
        return self.tabs.get(tab_id, (None, 0))

    def get_widget_instance(self, name, index=0):
        instances = self.widget_instances.get(name)

        if instances is None or len(instances) - 1 < index:
            return None

        return instances[index]

    def get_plugin_instance(self, name, index=0):
        instances = self.plugin_instances.get(name)

        if instances is None or len(instances) - 1 < index:
            return None

        return instances[index]

    def show_error(self, message: str):
        if not self.show_error_messages:
            return

        self.error_message.showMessage(message, message)

    def update_splash_screen(self, message: str):
        self.splash_screen.showMessage(message, color=QtCore.Qt.white)
        QtCore.QCoreApplication.processEvents()

    def register_screensaver_events(self):
        session_bus = QtDBus.QDBusConnection.sessionBus()

        session_bus.connect("org.freedesktop.ScreenSaver", "/org/freedesktop/ScreenSaver", "org.freedesktop.ScreenSaver", "ActiveChanged", self.screensaver_active_changed)
        session_bus.connect("org.gnome.ScreenSaver", "/org/gnome/ScreenSaver", "org.gnome.ScreenSaver", "ActiveChanged", self.screensaver_active_changed)
        session_bus.connect("org.cinnamon.ScreenSaver", "/org/cinnamon/ScreenSaver", "org.cinnamon.ScreenSaver", "ActiveChanged", self.screensaver_active_changed)
        session_bus.connect("org.kde.ScreenSaver", "/org/kde/ScreenSaver", "org.kde.ScreenSaver", "ActiveChanged", self.screensaver_active_changed)
        session_bus.connect("org.mate.ScreenSaver", "/org/mate/ScreenSaver", "org.mate.ScreenSaver", "ActiveChanged", self.screensaver_active_changed)
        session_bus.connect("org.xfce.ScreenSaver", "/org/xfce/ScreenSaver", "org.xfce.ScreenSaver", "ActiveChanged", self.screensaver_active_changed)

    @QtCore.pyqtSlot(bool)
    def screensaver_active_changed(self, state):
        self.screensaver_active = state
        self.screensaver_state_changed.emit(state)

    def closeEvent(self, event: QtGui.QCloseEvent):
        QtWidgets.QApplication.quit()

    def changeEvent(self, event):
        if event.type() == QtCore.QEvent.WindowStateChange:
            self.window_active = not bool(self.windowState() & QtCore.Qt.WindowMinimized)
            self.window_state_changed.emit(self.windowState())


def import_modules(config, children_property=None):
    module_type = config["type"]

    if children_property is not None and children_property in config:
        for child_module in config[children_property]:
            import_modules(child_module, children_property)

    if module_type not in modules:
        modules[module_type] = importlib.import_module("modules.{}".format(module_type))


def exception_hook(exception_type, exception_value, exception_traceback):
    traceback_string = "".join(traceback.format_exception(exception_type, exception_value, exception_traceback))
    print(traceback_string, file=sys.stderr)

    dashboard_instance = get_dashboard_instance()
    if dashboard_instance:
        dashboard_instance.show_error(traceback_string)
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

        import_modules(config["central_widget"], "widgets")

        if "overlay_widget" in config:
            import_modules(config["overlay_widget"], "widgets")

        if "plugins" in config:
            for plugin in config["plugins"]:
                import_modules(plugin)

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

        for plugin_type, plugin_instances in dashboard.plugin_instances.items():
            for plugin_instance in plugin_instances:
                plugin_instance.on_quit.emit()
    finally:
        if pid_file is not None and os.path.exists(pid_file):
            os.remove(pid_file)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
