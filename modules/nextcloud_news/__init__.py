import datetime
import subprocess

import requests
from PyQt5 import QtWidgets, QtCore, QtGui

from lib.common import Timer, AbstractView


class Updater(QtCore.QThread):
    ready = QtCore.pyqtSignal(list)

    def __init__(self, base_url, auth):
        QtCore.QThread.__init__(self)

        self.base_url = base_url
        self.auth = auth

    def run(self):
        request = requests.get("{}/feeds".format(self.base_url), auth=self.auth)

        feeds = {}

        for feed in request.json()["feeds"]:
            feeds[int(feed["id"])] = feed["title"]

        request = requests.get("{}/items".format(self.base_url), auth=self.auth)

        items = []

        for item in request.json()["items"]:
            if not item["unread"]:
                continue

            if len(items) >= 1000:
                break

            item["feed"] = feeds[int(item["feedId"])]

            items.append(item)

        self.ready.emit(items)


class View(QtWidgets.QTreeView, AbstractView):
    def __init__(self, nextcloud_url, username, password, columns=None):
        super().__init__()

        self.news = {}
        self.base_url = "{}/index.php/apps/news/api/v1-2".format(nextcloud_url)
        self.auth = (username, password)

        self.setAlternatingRowColors(True)
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.setRootIsDecorated(False)
        self.doubleClicked.connect(self.open_selected_items)

        self.view_model = QtGui.QStandardItemModel(0, 4)
        self.view_model.setHeaderData(0, QtCore.Qt.Horizontal, "Feed")
        self.view_model.setHeaderData(1, QtCore.Qt.Horizontal, "Title")
        self.view_model.setHeaderData(2, QtCore.Qt.Horizontal, "Date")
        self.view_model.setHeaderData(3, QtCore.Qt.Horizontal, "ID")
        self.setModel(self.view_model)

        self.setColumnWidth(0, 200)
        self.setColumnWidth(1, 600)
        self.setColumnWidth(2, 100)

        # Do not show the ID
        self.setColumnHidden(3, True)

        if columns:
            self.setColumnHidden(0, "feed" not in columns)
            self.setColumnHidden(1, "title" not in columns)
            self.setColumnHidden(2, "date" not in columns)

        open_action = QtWidgets.QAction(self)
        open_action.setShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Return))
        open_action.setShortcutContext(QtCore.Qt.WidgetShortcut)
        open_action.triggered.connect(self.open_selected_items)
        self.addAction(open_action)

        mark_as_read_action = QtWidgets.QAction(self)
        mark_as_read_action.setShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Delete))
        mark_as_read_action.triggered.connect(self.mark_selected_item_as_read)
        self.addAction(mark_as_read_action)

        self.updater_thread = Updater(self.base_url, self.auth)
        self.updater_thread.ready.connect(self.update_data)

        timer = Timer(self, 10 * 60 * 1000, self)
        timer.timeout.connect(self.updater_thread.start)

    def update_data(self, items):
        self.view_model.removeRows(0, self.view_model.rowCount())

        for item in items:
            self.news[item["id"]] = item

            self.view_model.appendRow([])
            row = self.view_model.rowCount() - 1

            datetime_string = datetime.datetime.fromtimestamp(item["lastModified"]).strftime("%c")

            self.view_model.setData(self.view_model.index(row, 0), item["feed"])
            self.view_model.setData(self.view_model.index(row, 0), item["feed"], QtCore.Qt.ToolTipRole)
            self.view_model.setData(self.view_model.index(row, 1), item["title"])
            self.view_model.setData(self.view_model.index(row, 1), item["title"], QtCore.Qt.ToolTipRole)
            self.view_model.setData(self.view_model.index(row, 2), datetime_string)
            self.view_model.setData(self.view_model.index(row, 2), datetime_string, QtCore.Qt.ToolTipRole)
            self.view_model.setData(self.view_model.index(row, 3), item["id"])

    def get_selected_items(self):
        selected_model_indexes = self.selectedIndexes()

        item_ids = set()

        for model_index in selected_model_indexes:
            item_ids.add(model_index.siblingAtColumn(3).data())

        items = []

        for item_id in item_ids:
            item = self.news[item_id]

            items.append(item)

        return items

    def open_selected_items(self):
        items = self.get_selected_items()

        for item in items:
            subprocess.run(["xdg-open", item["url"]])

            self.mark_item_as_read(item)

        self.updater_thread.start()

    def mark_selected_item_as_read(self):
        items = self.get_selected_items()

        for item in items:
            self.mark_item_as_read(item)

        self.updater_thread.start()

    def mark_item_as_read(self, item):
        requests.put("{}/items/{}/read".format(self.base_url, item["id"]), auth=self.auth)
