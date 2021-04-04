from PyQt5 import QtWidgets

from lib.common import AbstractView, get_dashboard_instance


class View(QtWidgets.QGroupBox, AbstractView):
    def __init__(self, title, widgets):
        super().__init__()
        self.setTitle(title)

        layout = QtWidgets.QStackedLayout()
        self.setLayout(layout)
        layout.addWidget(get_dashboard_instance().create_widget(widgets[0]))
