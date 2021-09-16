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


class View(QtWidgets.QTreeWidget, AbstractView):
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

        self.setHeaderLabels(["Title", "Date"])

        self.setColumnWidth(1, 250)

        self.header().setStretchLastSection(False)
        self.header().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)

        if columns:
            self.setColumnHidden(0, "title" not in columns)
            self.setColumnHidden(1, "date" not in columns)

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
        self.clear()

        self.news = {}

        grouped_items = {}

        for entry in items:
            feed = entry["feed"]

            self.news[entry["id"]] = entry

            if feed not in grouped_items:
                grouped_items[feed] = []

            grouped_items[feed].append(entry)

        for feed, items in grouped_items.items():
            feed_item = QtWidgets.QTreeWidgetItem(self)

            feed_item.setText(0, feed)
            feed_item.setExpanded(True)

            for entry in items:
                entry_item = QtWidgets.QTreeWidgetItem(feed_item)

                datetime_string = datetime.datetime.fromtimestamp(entry["lastModified"]).strftime("%c")

                entry_item.setData(0, QtCore.Qt.UserRole, entry)

                entry_item.setText(0, entry["title"])
                entry_item.setData(0, QtCore.Qt.ToolTipRole, entry["title"])
                entry_item.setText(1, datetime_string)
                entry_item.setData(1, QtCore.Qt.ToolTipRole, datetime_string)

    def get_selected_items(self):
        selected_model_indexes = self.selectedIndexes()

        item_ids = set()

        for model_index in selected_model_indexes:
            entry = model_index.siblingAtColumn(0).data(QtCore.Qt.UserRole)

            if entry:
                item_ids.add(entry["id"])

        items = []

        for item_id in item_ids:
            item = self.news[item_id]

            items.append(item)

        return items

    def open_selected_items(self):
        items = self.get_selected_items()

        if not items:
            return

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
