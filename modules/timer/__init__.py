import json
import os
import re

import dbus
from PyQt5 import QtWidgets, QtCore, QtMultimedia, QtGui

from lib.common import AbstractView, get_cache_path, disable_screensaver, get_dashboard_instance
from modules.mqtt_listener import mqtt_publish_json, mqtt_subscribe


def absolute_time_to_relative_time(end_time: QtCore.QDateTime):
    now = QtCore.QDateTime.currentDateTime()
    time_diff = now.msecsTo(end_time)

    return QtCore.QTime(0, 0, 0).addMSecs(time_diff)


def relative_time_to_absolute_time(new_time: QtCore.QTime):
    now = QtCore.QDateTime.currentDateTime()

    return now.addMSecs(new_time.msecsSinceStartOfDay())


class DisplayWidget(QtWidgets.QLCDNumber):
    clicked = QtCore.pyqtSignal()
    return_pressed = QtCore.pyqtSignal()

    def __init__(self):
        super().__init__()

        self.time_input = "000000"
        self.editable = True

        self.setFocusPolicy(QtCore.Qt.StrongFocus)

    def keyReleaseEvent(self, event: QtGui.QKeyEvent):
        super().keyReleaseEvent(event)

        if event.key() == QtCore.Qt.Key_Return:
            self.return_pressed.emit()
            return

        if self.editable:
            if event.key() == QtCore.Qt.Key_Backspace:
                self.time_input = "0{}".format(self.time_input)[:6]
            else:
                text = event.text()

                if text != "" and re.match(r"^[0-9]$", text):
                    self.time_input = "{}{}".format(self.time_input, text)[-6:]

            self.update_display()

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent):
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit()

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent):
        if event.button() == QtCore.Qt.LeftButton:
            if self.editable:
                self.time_input = "000000"
                self.update_display()

    def set_time(self, time: QtCore.QTime):
        self.time_input = "{:02d}{:02d}{:02d}".format(time.hour(), time.minute(), time.second())

    def get_time(self):
        hours, minutes, seconds = self.parse_time()

        hour_seconds = int(hours) * 60 * 60
        minute_seconds = int(minutes) * 60
        seconds = int(seconds)

        return QtCore.QTime(0, 0, 0).addSecs(hour_seconds + minute_seconds + seconds)

    def parse_time(self):
        hours = self.time_input[0:2]
        minutes = self.time_input[2:4]
        seconds = self.time_input[4:6]

        return hours, minutes, seconds

    def update_display(self):
        hours, minutes, seconds = self.parse_time()

        self.display("{}:{}:{}".format(hours, minutes, seconds))


class DBusHandler(dbus.service.Object):
    def __init__(self, view_instance: "View", session_bus: dbus.Bus):
        dbus.service.Object.__init__(self, session_bus, "/timer")

        self.view_instance = view_instance

    @dbus.service.method("com.selfcoders.Dashboard", in_signature="", out_signature="b")
    def is_active(self):
        return self.view_instance.is_active


class View(QtWidgets.QWidget, AbstractView):
    def __init__(self, disable_screensaver_while_active=False, sync_to_mqtt_topic=None):
        super().__init__()

        DBusHandler(self, get_dashboard_instance().session_dbus)

        self.timer_time = None
        self.is_active = False
        self.is_sound_playing = False
        self.disable_screensaver_while_active = disable_screensaver_while_active
        self.disable_screensaver_state = None

        self.sync_to_mqtt_topic = sync_to_mqtt_topic

        self.remaining_time_file = get_cache_path("timer")

        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)

        self.display_widget = DisplayWidget()
        self.display_widget.setDigitCount(8)
        self.display_widget.clicked.connect(self.stop_alarm)
        self.display_widget.return_pressed.connect(self.button_action)
        layout.addWidget(self.display_widget, 1)

        self.button = QtWidgets.QPushButton()
        self.button.clicked.connect(self.button_action)
        layout.addWidget(self.button)

        self.time = QtCore.QTime()

        self.alarm_sound = QtMultimedia.QSound(os.path.join(os.path.dirname(os.path.realpath(__file__)), "sounds", "alarm.wav"))
        self.alarm_sound.setLoops(QtMultimedia.QSound.Infinite)

        self.update_timer = QtCore.QTimer(self)
        self.update_timer.setInterval(1000)
        self.update_timer.timeout.connect(self.update_time)
        self.update_timer.start()

        self.update_time()
        self.display_widget.update_display()

    def start_view(self):
        if os.path.exists(self.remaining_time_file):
            with open(self.remaining_time_file, "r") as remaining_file:
                end_timestamp = int(remaining_file.readline())

                if end_timestamp > QtCore.QDateTime.currentSecsSinceEpoch():
                    self.start_timer(QtCore.QTime(0, 0, 0).addSecs(end_timestamp - QtCore.QDateTime.currentSecsSinceEpoch()), True)
                else:
                    os.unlink(self.remaining_time_file)

        if self.sync_to_mqtt_topic:
            mqtt_subscribe(self.sync_to_mqtt_topic, lambda topic, data: self.update_from_mqtt(json.loads(data)))

    def update_from_mqtt(self, data):
        if not data:
            return

        # Do not trigger again if source was this instance
        if data.get("source") == get_dashboard_instance().instance_name:
            return

        new_time = QtCore.QDateTime().fromTime_t(data.get("time", 0))
        if data.get("active"):
            self.start_timer(absolute_time_to_relative_time(new_time), False)
        else:
            self.stop_timer(False)

    def update_to_mqtt(self):
        if not self.sync_to_mqtt_topic:
            return

        mqtt_publish_json(self.sync_to_mqtt_topic, {
            "source": get_dashboard_instance().instance_name,
            "time": relative_time_to_absolute_time(QtCore.QTime(0, 0, 0).addMSecs(self.get_remaining_time())).toSecsSinceEpoch(),
            "active": self.is_active
        }, True)

    def get_remaining_time(self):
        return self.timer_time.msecsSinceStartOfDay() - self.time.elapsed()

    def update_time(self):
        if self.is_active:
            remaining_time = self.get_remaining_time()

            if remaining_time <= 0:
                remaining_time = 0
                self.is_active = False
                self.trigger_alarm()
        else:
            remaining_time = 0

        time = QtCore.QTime(0, 0, 0).addMSecs(remaining_time)

        if not self.display_widget.editable:
            self.display_widget.set_time(time)
            self.display_widget.update_display()

        if self.is_sound_playing or self.is_active:
            self.button.setText("Stop")
        else:
            self.button.setText("Start")

        self.update_screensaver()

    def button_action(self):
        if self.is_sound_playing or self.is_active:
            self.stop_timer(True)
        else:
            new_time = self.display_widget.get_time()

            if not new_time.isValid():
                QtWidgets.QMessageBox.critical(self, self.windowTitle(), "Invalid time!")
                return

            self.start_timer(new_time, True)

        self.update_time()

    def start_timer(self, new_time: QtCore.QTime, publish_mqtt: bool):
        if not new_time.isValid():
            return

        self.timer_time = new_time

        # Set time to current time
        self.time.start()

        if self.get_remaining_time() <= 0:
            return

        self.display_widget.editable = False
        self.is_active = True

        os.makedirs(os.path.dirname(self.remaining_time_file), exist_ok=True)

        with open(self.remaining_time_file, "w") as timestamp_file:
            timestamp_file.write(str(int(QtCore.QDateTime.currentSecsSinceEpoch() + (self.timer_time.msecsSinceStartOfDay() / 1000))))

        if publish_mqtt:
            self.update_to_mqtt()

    def stop_timer(self, publish_mqtt: bool):
        self.stop_alarm()
        self.display_widget.editable = True
        self.is_active = False

        if os.path.exists(self.remaining_time_file):
            os.unlink(self.remaining_time_file)

        if publish_mqtt:
            self.update_to_mqtt()

    def stop_alarm(self):
        self.is_sound_playing = False
        self.alarm_sound.stop()

    def trigger_alarm(self):
        self.is_sound_playing = True
        self.alarm_sound.play()

    def update_screensaver(self):
        if self.disable_screensaver_while_active:
            new_state = self.is_active or self.is_sound_playing

            if self.disable_screensaver_state != new_state:
                self.disable_screensaver_state = new_state
                disable_screensaver(get_dashboard_instance().winId(), new_state)
