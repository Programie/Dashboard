from PyQt5 import QtWidgets

from lib.common import AbstractView, get_dashboard_instance


class View(QtWidgets.QWidget, AbstractView):
    def __init__(self, widgets, orientation="horizontal", stretch=None, sizes=None):
        super().__init__()

        if orientation == "vertical":
            layout = QtWidgets.QVBoxLayout()
        else:
            layout = QtWidgets.QHBoxLayout()

        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        for index, child_widget in enumerate(widgets):
            child_widget_instance: QtWidgets.QWidget = get_dashboard_instance().create_widget(child_widget)

            if stretch and len(stretch) - 1 > index:
                stretch_widget = stretch[index]
            else:
                stretch_widget = 0

            if sizes and len(sizes) > index and sizes[index]:
                if orientation == "vertical":
                    child_widget_instance.setFixedHeight(sizes[index])
                else:
                    child_widget_instance.setFixedWidth(sizes[index])

            layout.addWidget(child_widget_instance, stretch=stretch_widget)
