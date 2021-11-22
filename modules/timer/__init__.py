import os
import re

from PyQt5 import QtWidgets, QtCore, QtMultimedia, QtGui

from lib.common import AbstractView, get_cache_path, disable_screensaver, get_dashboard_instance


class ScrollingLCDNumber(QtWidgets.QLCDNumber):
    clicked = QtCore.pyqtSignal()

    def __init__(self):
        super().__init__()

        self.control_pressed = False
        self.time = QtCore.QTime(0, 0, 0)
        self.editable = True

        self.setFocusPolicy(QtCore.Qt.StrongFocus)

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        super().keyPressEvent(event)

        if event.key() == QtCore.Qt.Key_Control:
            self.control_pressed = True

    def keyReleaseEvent(self, event: QtGui.QKeyEvent):
        super().keyReleaseEvent(event)

        if event.key() == QtCore.Qt.Key_Control:
            self.control_pressed = False
        elif self.editable:
            time_input = "{:02d}{:02d}{:02d}".format(self.time.hour(), self.time.minute(), self.time.second())

            if event.key() == QtCore.Qt.Key_Backspace:
                self.update_time_from_text("0{}".format(time_input)[:6])
            else:
                text = event.text()

                if text != "" and re.match(r"^[0-9]$", text):
                    self.update_time_from_text("{}{}".format(time_input, text)[-6:])

    def focusOutEvent(self, event: QtGui.QFocusEvent):
        self.control_pressed = False

    def wheelEvent(self, event: QtGui.QWheelEvent):
        super().wheelEvent(event)

        if not self.editable:
            return

        if event.angleDelta().y() > 0:
            add_number = 1
        else:
            add_number = -1

        if self.control_pressed:
            self.time = self.time.addSecs(add_number * 60)
        else:
            self.time = self.time.addSecs(add_number)

        self.update_display()

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent):
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit()

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent):
        if event.button() == QtCore.Qt.LeftButton:
            if self.editable:
                self.time = QtCore.QTime(0, 0, 0)
                self.update_display()

    def update_time_from_text(self, text):
        hours = int(text[0:2])
        minutes = int(text[2:4])
        seconds = int(text[4:6])

        if hours > 23 or minutes > 59 or seconds > 59:
            return

        self.time = QtCore.QTime(hours, minutes, seconds)

        self.update_display()

    def update_display(self):
        self.display("{:02d}:{:02d}:{:02d}".format(self.time.hour(), self.time.minute(), self.time.second()))


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

        self.display_widget = ScrollingLCDNumber()
        self.display_widget.setDigitCount(8)
        self.display_widget.clicked.connect(self.stop_alarm)
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
            self.display_widget.time = time
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
            self.timer_time = QtCore.QTime(self.display_widget.time)
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
