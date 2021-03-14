from PyQt5 import QtWidgets

from dashboard import Dashboard
from lib.common import AbstractView


class View(QtWidgets.QGroupBox, AbstractView):
    def __init__(self, dashboard_instance: Dashboard, title, widgets):
        super().__init__()
        self.setTitle(title)

        layout = QtWidgets.QStackedLayout()
        self.setLayout(layout)
        layout.addWidget(dashboard_instance.create_widget(widgets[0]))
