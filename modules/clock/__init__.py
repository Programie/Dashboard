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

    def __init__(self, font=None, colors=None, hands=None):
        super().__init__()

        if font is None:
            font = {}

        if colors is None:
            colors = {}

        if hands is None:
            hands = {}

        self.font = QtGui.QFont()
        self.font.setFamily(font.get("family", "FreeSans"))
        self.font.setPointSize(font.get("size", 15))

        self.numbers_color = QtGui.QColor(colors.get("numbers", "black"))
        self.hours_color = QtGui.QColor(colors.get("hours", "black"))
        self.minutes_color = QtGui.QColor(colors.get("minutes", "black"))

        self.hour_hand_pen = self.create_hand_pen(hands.get("hour"), 2, "black")
        self.minute_hand_pen = self.create_hand_pen(hands.get("minute"), 2, "black")
        self.second_hand_pen = self.create_hand_pen(hands.get("second"), 1, "red")

        timer = Timer(self, 500, self)
        timer.timeout.connect(self.update)

    @staticmethod
    def create_hand_pen(config, width, color):
        if not config:
            config = {}

        pen = QtGui.QPen()
        pen.setWidth(config.get("width", width))
        pen.setBrush(QtGui.QColor(config.get("color", color)))
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)

        return pen

    def paintEvent(self, event):
        side = min(self.width(), self.height())

        time: QtCore.QTime = QtCore.QTime.currentTime()

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.translate(self.width() / 2, self.height() / 2)
        painter.scale(side / 200.0, side / 200.0)
        painter.setFont(self.font)

        painter.setPen(self.hours_color)
        for hour in range(12):
            painter.drawLine(88, 0, 96, 0)
            painter.rotate(30.0)

        painter.setPen(self.minutes_color)
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

        painter.setPen(self.second_hand_pen)
        painter.save()
        painter.rotate(6.0 * time.second())
        painter.drawLine(0, 0, 0, -85)
        painter.restore()
