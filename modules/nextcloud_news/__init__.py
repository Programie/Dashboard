import datetime
import re
import subprocess
from collections import OrderedDict
from enum import Enum

import pyperclip
import requests
from PyQt5 import QtWidgets, QtCore, QtGui

from lib.common import Timer, AbstractView


class ItemAction(Enum):
    EXCLUDE = "exclude"
    COLLAPSE = "collapse"


class Updater(QtCore.QThread):
    ready = QtCore.pyqtSignal(list)

    def __init__(self, base_url, auth):
        QtCore.QThread.__init__(self)

        self.base_url = base_url
        self.auth = auth

    def run(self):
        request = requests.get("{}/folders".format(self.base_url), auth=self.auth)

        folders = {}

        for folder in request.json()["folders"]:
            folders[int(folder["id"])] = folder["name"]

        request = requests.get("{}/feeds".format(self.base_url), auth=self.auth)

        feeds = {}

        for feed in request.json()["feeds"]:
            feeds[int(feed["id"])] = feed

        request = requests.get("{}/items".format(self.base_url), auth=self.auth, params={"type": 3, "getRead": "false", "batchSize": -1})

        items = []

        for item in request.json()["items"]:
            if len(items) >= 1000:
                break

            feed = feeds[int(item["feedId"])]

            item["folder"] = folders[int(feed["folderId"])]
            item["feed"] = feed["title"]

            items.append(item)

        self.ready.emit(items)


class View(QtWidgets.QTreeWidget, AbstractView):
    def __init__(self, nextcloud_url, username, password, columns=None, item_options=None, update_interval=600):
        super().__init__()

        self.news = {}
        self.base_url = "{}/index.php/apps/news/api/v1-2".format(nextcloud_url)
        self.auth = (username, password)
        self.item_options = item_options

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

        self.updater_thread = Updater(self.base_url, self.auth)
        self.updater_thread.ready.connect(self.update_data)

        timer = Timer(self, update_interval * 1000, self)
        timer.timeout.connect(self.trigger_update_by_timer)

    def trigger_update_by_timer(self):
        if len(self.get_selected_items()) > 1:
            return

        self.updater_thread.start()

    def show_context_menu(self, position):
        if not self.itemAt(position):
            return

        self.context_menu.exec(self.mapToGlobal(position))

    def check_item_options(self, item_type: str, value: str, action: ItemAction):
        if not self.item_options:
            return False

        for item in self.item_options:
            if item["type"] != item_type:
                continue

            if "value" in item:
                if item["value"] == value and item["action"] == action.value:
                    return True
            elif "regex" in item and item["action"] == action.value:
                if re.match(item["regex"], value):
                    return True

        return False

    def update_data(self, items):
        self.clear()

        self.news = {}

        grouped_items = {}

        for entry in items:
            folder = entry["folder"]
            feed = entry["feed"]

            self.news[entry["id"]] = entry

            if folder not in grouped_items:
                grouped_items[folder] = {}

            if feed not in grouped_items[folder]:
                grouped_items[folder][feed] = []

            grouped_items[folder][feed].append(entry)

        sorted_folders = OrderedDict(sorted(grouped_items.items(), key=lambda item: item[0].lower()))

        for folder_name, feeds in sorted_folders.items():
            if self.check_item_options("folder", folder_name, ItemAction.EXCLUDE):
                continue

            folder_item = QtWidgets.QTreeWidgetItem(self)

            folder_item.setText(0, "{} ({})".format(folder_name, sum([len(entries) for entries in feeds.values()])))
            folder_item.setExpanded(not self.check_item_options("folder", folder_name, ItemAction.COLLAPSE))

            sorted_feeds = OrderedDict(sorted(feeds.items(), key=lambda item: item[0].lower()))

            for feed_name, entries in sorted_feeds.items():
                if self.check_item_options("feed", feed_name, ItemAction.EXCLUDE):
                    continue

                feed_item = QtWidgets.QTreeWidgetItem(folder_item)

                feed_item.setText(0, "{} ({})".format(feed_name, len(entries)))
                feed_item.setExpanded(not self.check_item_options("feed", feed_name, ItemAction.COLLAPSE))

                for entry in entries:
                    if self.check_item_options("entry", entry["title"], ItemAction.EXCLUDE):
                        continue

                    entry_item = QtWidgets.QTreeWidgetItem(feed_item)

                    datetime_string = datetime.datetime.fromtimestamp(entry["pubDate"]).strftime("%c")

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
