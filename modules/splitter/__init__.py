from PyQt5 import QtWidgets, QtCore

from lib.common import AbstractView, get_dashboard_instance


class View(QtWidgets.QSplitter, AbstractView):
    def __init__(self, widgets, orientation="horizontal", sizes=None):
        super().__init__()

        if orientation == "vertical":
            self.setOrientation(QtCore.Qt.Vertical)
        else:
            self.setOrientation(QtCore.Qt.Horizontal)

        dashboard_instance = get_dashboard_instance()
        for child_widget in widgets:
            self.addWidget(dashboard_instance.create_widget(child_widget))

        if sizes:
            self.setSizes(sizes)
