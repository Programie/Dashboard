from PyQt5 import QtWidgets, QtGui, QtCore

from lib.common import Timer, AbstractView


class View(QtWidgets.QWidget, AbstractView):
    hour_numbers = [
        QtCore.QPoint(35, -57),  # 1
        QtCore.QPoint(61, -31),  # 2
        QtCore.QPoint(73, 7),  # 3
        QtCore.QPoint(62, 45),  # 4
        QtCore.QPoint(33, 72),  # 5
        QtCore.QPoint(-6, 82),  # 6
        QtCore.QPoint(-43, 70),  # 7
        QtCore.QPoint(-72, 42),  # 8
        QtCore.QPoint(-83, 7),  # 9
        QtCore.QPoint(-73, -30),  # 10
        QtCore.QPoint(-45, -58),  # 11
        QtCore.QPoint(-12, -68),  # 12
    ]

    def __init__(self, font=None, numbers_color="black", ticks=None, center_circle=None, center_circle_second=None, hands=None):
        super().__init__()

        if font is None:
            font = {}

        if ticks is None:
            ticks = {}

        if center_circle is None:
            center_circle = {}

        if center_circle_second is None:
            center_circle_second = {}

        if hands is None:
            hands = {}

        self.font = QtGui.QFont()
        self.font.setFamily(font.get("family", "FreeSans"))
        self.font.setPointSize(font.get("size", 15))

        self.numbers_color = QtGui.QColor(numbers_color)

        self.hours_pen = self.create_pen(ticks.get("hours"), 1, "black")
        self.minutes_pen = self.create_pen(ticks.get("minutes"), 1, "black")

        self.center_circle_size = center_circle.get("size", 10)
        self.center_circle_color = QtGui.QColor(center_circle.get("color", 10))

        self.center_circle_second_size = center_circle_second.get("size", 10)
        self.center_circle_second_color = QtGui.QColor(center_circle_second.get("color", 10))

        self.hour_hand_pen = self.create_pen(hands.get("hour"), 2, "black", "round")
        self.minute_hand_pen = self.create_pen(hands.get("minute"), 2, "black", "round")
        self.second_hand_pen = self.create_pen(hands.get("second"), 1, "red", "round")

        timer = Timer(self, 500, self)
        timer.timeout.connect(self.update)

    @staticmethod
    def create_pen(config, width, color, cap_style="flat"):
        if not config:
            config = {}

        pen = QtGui.QPen()
        pen.setWidth(config.get("width", width))
        pen.setBrush(QtGui.QColor(config.get("color", color)))

        cap_style = config.get("cap_style", cap_style)

        if cap_style == "square":
            cap_style = QtCore.Qt.PenCapStyle.SquareCap
        elif cap_style == "round":
            cap_style = QtCore.Qt.PenCapStyle.RoundCap
        else:
            cap_style = QtCore.Qt.PenCapStyle.FlatCap

        pen.setCapStyle(cap_style)

        return pen

    def paintEvent(self, event):
        side = min(self.width(), self.height())

        time: QtCore.QTime = QtCore.QTime.currentTime()

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.translate(self.width() / 2, self.height() / 2)
        painter.scale(side / 200.0, side / 200.0)
        painter.setFont(self.font)

        painter.setPen(self.hours_pen)
        for hour in range(12):
            painter.drawLine(88, 0, 96, 0)
            painter.rotate(30.0)

        painter.setPen(self.minutes_pen)
        for minute in range(60):
            if (minute % 5) != 0:
                painter.drawLine(92, 0, 96, 0)

            painter.rotate(6.0)

        painter.setPen(self.numbers_color)
        painter.save()
        for number, point in enumerate(self.hour_numbers):
            painter.drawText(point, str(number + 1))
        painter.restore()

        painter.setPen(self.hour_hand_pen)
        painter.save()
        painter.rotate(30.0 * (time.hour() + time.minute() / 60.0))
        painter.drawLine(0, 0, 0, -40)
        painter.restore()

        painter.setPen(self.minute_hand_pen)
        painter.save()
        painter.rotate(6.0 * (time.minute() + time.second() / 60.0))
        painter.drawLine(0, 0, 0, -60)
        painter.restore()

        painter.setBrush(self.center_circle_color)
        painter.setPen(self.center_circle_color)
        painter.save()
        painter.drawEllipse(QtCore.QRectF(-(self.center_circle_size / 2), -(self.center_circle_size / 2), self.center_circle_size, self.center_circle_size))
        painter.restore()

        painter.setPen(self.second_hand_pen)
        painter.save()
        painter.rotate(6.0 * time.second())
        painter.drawLine(0, 0, 0, -85)
        painter.restore()

        painter.setBrush(self.center_circle_second_color)
        painter.setPen(self.center_circle_second_color)
        painter.save()
        painter.drawEllipse(QtCore.QRectF(-(self.center_circle_second_size / 2), -(self.center_circle_second_size / 2), self.center_circle_second_size, self.center_circle_second_size))
        painter.restore()
