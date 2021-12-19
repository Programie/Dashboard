import os
import re

from PyQt5 import QtWidgets, QtCore, QtMultimedia, QtGui

from lib.common import AbstractView, get_cache_path, disable_screensaver, get_dashboard_instance


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


class View(QtWidgets.QWidget, AbstractView):
    def __init__(self, disable_screensaver_while_active=False):
        super().__init__()

        self.timer_time = None
        self.is_active = False
        self.is_sound_playing = False
        self.disable_screensaver_while_active = disable_screensaver_while_active
        self.disable_screensaver_state = None

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

        if os.path.exists(self.remaining_time_file):
            with open(self.remaining_time_file, "r") as remaining_file:
                end_timestamp = int(remaining_file.readline())

                if end_timestamp > QtCore.QDateTime.currentSecsSinceEpoch():
                    self.timer_time = QtCore.QTime(0, 0, 0).addSecs(end_timestamp - QtCore.QDateTime.currentSecsSinceEpoch())
                    self.start_timer()
                else:
                    os.unlink(self.remaining_time_file)

        self.update_time()
        self.display_widget.update_display()

    def update_time(self):
        if self.is_active:
            remaining_time = self.timer_time.msecsSinceStartOfDay() - self.time.elapsed()

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
            self.stop_alarm()
            self.display_widget.editable = True
            self.is_active = False

            if os.path.exists(self.remaining_time_file):
                os.unlink(self.remaining_time_file)
        else:
            self.timer_time = self.display_widget.get_time()

            if not self.timer_time.isValid():
                QtWidgets.QMessageBox.critical(self, self.windowTitle(), "Invalid time!")
                return

            self.start_timer()

            with open(self.remaining_time_file, "w") as timestamp_file:
                timestamp_file.write(str(int(QtCore.QDateTime.currentSecsSinceEpoch() + (self.timer_time.msecsSinceStartOfDay() / 1000))))

        self.update_time()

    def stop_alarm(self):
        self.is_sound_playing = False
        self.alarm_sound.stop()

    def trigger_alarm(self):
        self.is_sound_playing = True
        self.alarm_sound.play()

    def start_timer(self):
        self.time.start()
        self.display_widget.editable = False
        self.is_active = True

    def update_screensaver(self):
        if self.disable_screensaver_while_active:
            new_state = self.is_active or self.is_sound_playing

            if self.disable_screensaver_state != new_state:
                self.disable_screensaver_state = new_state
                disable_screensaver(get_dashboard_instance().winId(), new_state)
