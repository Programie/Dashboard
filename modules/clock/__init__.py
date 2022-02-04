from PyQt5 import QtWidgets, QtGui, QtCore

from lib.common import Timer, AbstractView


class View(QtWidgets.QWidget, AbstractView):
    pen = QtGui.QPen()
    pen.setWidth(2)
    pen.setBrush(QtCore.Qt.white)
    pen.setCapStyle(QtCore.Qt.RoundCap)

    second_pen = QtGui.QPen()
    second_pen.setWidth(1)
    second_pen.setBrush(QtCore.Qt.white)
    second_pen.setCapStyle(QtCore.Qt.RoundCap)

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)

        self.painting_widget = QtWidgets.QWidget()
        layout.addWidget(self.painting_widget)

        timer = Timer(self, 500, self)
        timer.timeout.connect(self.update)

    def paintEvent(self, event):
        side = min(self.width(), self.height())

        time: QtCore.QTime = QtCore.QTime.currentTime()

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.translate(self.width() / 2, self.height() / 2)
        painter.scale(side / 200.0, side / 200.0)

        painter.setPen(QtCore.Qt.gray)

        font = QtGui.QFont()
        font.setFamily("FreeSans")
        font.setPointSize(15)
        painter.setFont(font)

        painter.save()
        for number, point in enumerate(self.hour_numbers):
            painter.drawText(point, str(number + 1))
        painter.restore()

        painter.setPen(self.pen)

        painter.save()
        painter.rotate(30.0 * (time.hour() + time.minute() / 60.0))
        painter.drawLine(0, 0, 0, -40)
        painter.restore()

        painter.setPen(QtCore.Qt.white)

        for hour in range(12):
            painter.drawLine(88, 0, 96, 0)
            painter.rotate(30.0)

        painter.setPen(self.pen)

        painter.save()
        painter.rotate(6.0 * (time.minute() + time.second() / 60.0))
        painter.drawLine(0, 0, 0, -60)
        painter.restore()

        painter.setPen(QtCore.Qt.gray)

        for minute in range(60):
            if (minute % 5) != 0:
                painter.drawLine(92, 0, 96, 0)

            painter.rotate(6.0)

        painter.setPen(self.second_pen)

        painter.save()
        painter.rotate(6.0 * time.second())
        painter.drawLine(0, 0, 0, -80)
        painter.restore()
