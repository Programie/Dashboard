from PyQt5 import QtWidgets

from lib.common import AbstractView, get_dashboard_instance


class View(QtWidgets.QTabWidget, AbstractView):
    def __init__(self, widgets, active_tab=None):
        super().__init__()

        self.tab_titles = {}
        self.dashboard_instance = get_dashboard_instance()

        for child_widget in widgets:
            if "tab_title" in child_widget:
                tab_title = child_widget["tab_title"]
                del child_widget["tab_title"]
            else:
                tab_title = child_widget["type"]

            if "tab_id" in child_widget:
                tab_id = child_widget["tab_id"]
                del child_widget["tab_id"]
            else:
                tab_id = None

            self.add_tab(self.dashboard_instance.create_widget(child_widget), tab_title, tab_id)

        if active_tab is not None:
            self.setCurrentIndex(active_tab)

    def add_tab(self, widget, title, tab_id=None):
        tab_index = self.addTab(widget, title)

        self.tab_titles[tab_index] = title

        if tab_id is not None:
            self.dashboard_instance.tabs[tab_id] = (self, tab_index)

        return tab_index

    def append_tab_title(self, index, title: str = None):
        if title is None:
            title = self.tab_titles[index]
        else:
            title = "".join([self.tab_titles[index], title])

        self.setTabText(index, title)
