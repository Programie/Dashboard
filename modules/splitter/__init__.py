from PyQt5 import QtWidgets, QtCore

from dashboard import Dashboard
from lib.common import AbstractView


class View(QtWidgets.QSplitter, AbstractView):
    def __init__(self, dashboard_instance: Dashboard, widgets, orientation="horizontal", sizes=None):
        super().__init__()

        if orientation == "vertical":
            self.setOrientation(QtCore.Qt.Vertical)
        else:
            self.setOrientation(QtCore.Qt.Horizontal)

        for child_widget in widgets:
            self.addWidget(dashboard_instance.create_widget(child_widget))

        if sizes:
            self.setSizes(sizes)
