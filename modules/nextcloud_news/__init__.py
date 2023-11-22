import datetime
import os
import re
import subprocess
from collections import OrderedDict
from enum import Enum

import pyperclip
import requests
from PyQt5 import QtWidgets, QtCore, QtGui

from lib.common import Timer, AbstractView, get_dashboard_instance


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

        folders = {
            -1: "No folder"
        }

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
            folder_id = feed["folderId"]

            if folder_id is None:
                folder_id = -1

            item["folder"] = folders[int(folder_id)]
            item["feed"] = feed["title"]

            items.append(item)

        self.ready.emit(items)


class View(QtWidgets.QTreeWidget, AbstractView):
    def __init__(self, nextcloud_url, username, password, columns=None, item_options=None, context_menu_items=None, update_interval=600, update_in_background=False, tab_id_status=None):
        super().__init__()

        self.news = {}
        self.base_url = "{}/index.php/apps/news/api/v1-2".format(nextcloud_url)
        self.auth = (username, password)
        self.item_options = item_options
        self.context_menu_items = context_menu_items
        self.tab_id_status = tab_id_status
        self.seen_items = set()

        self.new_items_icon = QtGui.QIcon(os.path.join(os.path.dirname(os.path.realpath(__file__)), "images", "new_items.png"))

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

        if self.context_menu_items:
            self.context_menu.addSeparator()

            self.add_context_menu_items()

        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        self.visibility_changed.connect(self.on_visibility_changed)

        self.updater_thread = Updater(self.base_url, self.auth)
        self.updater_thread.ready.connect(self.update_data)

        timer = Timer(self, update_interval * 1000, self, auto_enable=not update_in_background)
        timer.timeout.connect(self.trigger_update_by_timer)

        if update_in_background:
            timer.start()

    def on_visibility_changed(self, state: bool):
        if state:
            self.seen_items = set(self.news)

        self.update_tab()

    def trigger_update_by_timer(self):
        if len(self.get_selected_items()) > 1:
            return

        self.updater_thread.start()

    def add_context_menu_item(self, menu_item):
        if menu_item.get("type") == "separator":
            self.context_menu.addSeparator()
            return

        icon_name = menu_item.get("icon")
        if icon_name is not None:
            action = QtWidgets.QAction(QtGui.QIcon.fromTheme(icon_name), menu_item.get("title"), self)
        else:
            action = QtWidgets.QAction(menu_item.get("title"), self)

        shortcut = menu_item.get("shortcut")
        if shortcut is not None:
            action.setShortcut(QtGui.QKeySequence.fromString(shortcut))
            action.setShortcutContext(QtCore.Qt.WidgetShortcut)

        action.triggered.connect(lambda: self.execute_context_menu_action(menu_item))
        self.addAction(action)
        self.context_menu.addAction(action)

    def add_context_menu_items(self):
        if not self.context_menu_items:
            return

        for menu_item in self.context_menu_items:
            self.add_context_menu_item(menu_item)

    def execute_context_menu_action(self, menu_item):
        items = self.get_selected_items()

        if not items:
            return

        for list_item in items:
            self.execute_context_menu_action_for_item(menu_item, list_item)

        self.updater_thread.start()

    def execute_context_menu_action_for_item(self, menu_item, list_item):
        command = menu_item.get("command")
        if command is not None:
            subprocess.check_call(command.format_map(list_item), shell=True)

        if menu_item.get("mark_as_read"):
            self.mark_item_as_read(list_item)

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

        if self.isVisible():
            self.seen_items = set(self.news.keys())

        self.update_tab()

    def get_unseen_items(self):
        return set(self.news.keys()) - self.seen_items

    def update_tab(self):
        if self.tab_id_status is None:
            return

        tab_widget, tab_index = get_dashboard_instance().tab_by_id(self.tab_id_status)
        if tab_widget is not None:
            unseen_items = self.get_unseen_items()
            if unseen_items:
                tab_title = " ({})".format(len(unseen_items))
                tab_icon = self.new_items_icon
            else:
                tab_title = None
                tab_icon = QtGui.QIcon()

            tab_widget.append_tab_title(tab_index, tab_title)
            tab_widget.setTabIcon(tab_index, tab_icon)

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
