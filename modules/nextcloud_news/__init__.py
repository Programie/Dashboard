import datetime
import subprocess
from collections import OrderedDict

import pyperclip
import requests
from PyQt5 import QtWidgets, QtCore, QtGui

from lib.common import Timer, AbstractView


class Updater(QtCore.QThread):
    ready = QtCore.pyqtSignal(list)

    def __init__(self, base_url, auth, tree_widget: QtWidgets.QTreeWidget):
        QtCore.QThread.__init__(self)

        self.base_url = base_url
        self.auth = auth
        self.tree_widget = tree_widget

    def run(self):
        if len(self.tree_widget.selectedIndexes()) > 1:
            return

        request = requests.get("{}/feeds".format(self.base_url), auth=self.auth)

        feeds = {}

        for feed in request.json()["feeds"]:
            feeds[int(feed["id"])] = feed["title"]

        request = requests.get("{}/items".format(self.base_url), auth=self.auth, params={"type": 3, "getRead": "false", "batchSize": -1})

        items = []

        for item in request.json()["items"]:
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

        open_action = QtWidgets.QAction(QtGui.QIcon.fromTheme("document-open"), "Open", self)
        open_action.setShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_Return))
        open_action.setShortcutContext(QtCore.Qt.WidgetShortcut)
        open_action.triggered.connect(self.open_selected_items)
        self.addAction(open_action)

        copy_action = QtWidgets.QAction(QtGui.QIcon.fromTheme("edit-copy"), "Copy URL", self)
        copy_action.setShortcut(QtGui.QKeySequence(QtGui.QKeySequence.StandardKey.Copy))
        copy_action.setShortcutContext(QtCore.Qt.WidgetShortcut)
        copy_action.triggered.connect(self.copy_selected_items)
        self.addAction(copy_action)

        mark_as_read_action = QtWidgets.QAction(QtGui.QIcon.fromTheme("mail-mark-read"), "Mark as read", self)
        mark_as_read_action.setShortcut(QtGui.QKeySequence(QtGui.QKeySequence.StandardKey.Delete))
        mark_as_read_action.setShortcutContext(QtCore.Qt.WidgetShortcut)
        mark_as_read_action.triggered.connect(self.mark_selected_item_as_read)
        self.addAction(mark_as_read_action)

        self.context_menu = QtWidgets.QMenu()
        self.context_menu.addAction(open_action)
        self.context_menu.addAction(copy_action)
        self.context_menu.addSeparator()
        self.context_menu.addAction(mark_as_read_action)

        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        self.updater_thread = Updater(self.base_url, self.auth, self)
        self.updater_thread.ready.connect(self.update_data)

        timer = Timer(self, 10 * 60 * 1000, self)
        timer.timeout.connect(self.updater_thread.start)

    def show_context_menu(self, position):
        if not self.itemAt(position):
            return

        self.context_menu.exec(self.mapToGlobal(position))

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

        grouped_items = OrderedDict(sorted(grouped_items.items(), key=lambda item: item[0].lower()))

        for feed, items in grouped_items.items():
            feed_item = QtWidgets.QTreeWidgetItem(self)

            feed_item.setText(0, "{} ({})".format(feed, len(items)))
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

    def copy_selected_items(self):
        items = self.get_selected_items()

        if not items:
            return

        lines = [item["url"] for item in items]

        pyperclip.copy("\n".join(lines))

    def mark_selected_item_as_read(self):
        items = self.get_selected_items()

        if not items:
            return

        for item in items:
            self.mark_item_as_read(item)

        self.updater_thread.start()

    def mark_item_as_read(self, item):
        requests.put("{}/items/{}/read".format(self.base_url, item["id"]), auth=self.auth)
