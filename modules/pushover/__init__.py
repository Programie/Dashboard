import datetime
import json
import os

import requests
import websocket
from PyQt5 import QtWidgets, QtCore, QtGui

from dashboard import Dashboard
from lib.common import AbstractView, ThreadedRequest, ThreadedDownloadAndCache, get_cache_path, RingBuffer


class WebSocketThread(QtCore.QThread):
    sync = QtCore.pyqtSignal()

    def __init__(self, parent, secret, device_id):
        QtCore.QThread.__init__(self, parent)

        self.secret = secret
        self.device_id = device_id

        self.client = websocket.WebSocketApp("wss://client.pushover.net/push")

        self.client.on_open = lambda ws: self.on_open()
        self.client.on_message = lambda ws, message: self.on_message(message)

    def run(self):
        self.client.run_forever()

    def on_open(self):
        self.client.send("login:{}:{}\n".format(self.device_id, self.secret))

    def on_message(self, message):
        message = message.decode("utf-8")

        if message[0] == "!":
            self.sync.emit()


class ListWidget(QtWidgets.QTreeView):
    def __init__(self):
        super().__init__()

        self.icon_name_rows = {}
        self.icon_cache_dir = None

        self.setAlternatingRowColors(True)
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.setRootIsDecorated(False)
        self.setHeaderHidden(True)
        self.setIconSize(QtCore.QSize(100, 100))

        self.view_model = QtGui.QStandardItemModel(0, 3)
        self.view_model.setHeaderData(0, QtCore.Qt.Horizontal, "")
        self.view_model.setHeaderData(1, QtCore.Qt.Horizontal, "")
        self.setModel(self.view_model)

        # Meta data column
        self.setColumnHidden(2, True)

    def clear(self):
        self.view_model.removeRows(0, self.view_model.rowCount())

        self.icon_name_rows = {}

    def add_row(self, item):
        self.view_model.appendRow([])
        row = self.view_model.rowCount() - 1

        icon_name = item["icon"]

        if icon_name not in self.icon_name_rows:
            self.icon_name_rows[icon_name] = []

        self.icon_name_rows[icon_name].append(row)

        icon_index = self.view_model.index(row, 0)
        message_index = self.view_model.index(row, 1)
        meta_index = self.view_model.index(row, 2)

        message = "{}\n{}\n\n{}".format(item.get("title", item["app"]), item["message"], datetime.datetime.fromtimestamp(item["date"]).strftime("%c"))

        self.view_model.setData(icon_index, "")
        self.view_model.setData(message_index, message)
        self.view_model.setData(message_index, message, QtCore.Qt.ToolTipRole)
        self.view_model.setData(meta_index, item, QtCore.Qt.UserRole)

        if self.icon_cache_dir is not None:
            self.update_image(item["icon"], os.path.join(self.icon_cache_dir, icon_name))

    def update_image(self, name, icon_path):
        rows = self.icon_name_rows.get(name)
        if rows is None:
            return

        for row in rows:
            self.view_model.item(row, 0).setIcon(QtGui.QIcon(icon_path))


class View(QtWidgets.QWidget, AbstractView):
    def __init__(self, dashboard_instance: Dashboard, secret, device_id, tab_id_status=None):
        super().__init__()

        self.dashboard_instance = dashboard_instance
        self.secret = secret
        self.device_id = device_id
        self.tab_id_status = tab_id_status
        self.download_thread = None
        self.unseen_messages = 0

        self.new_messages_icon = QtGui.QIcon(os.path.join(os.path.dirname(os.path.realpath(__file__)), "images", "new_messages.png"))

        layout = QtWidgets.QVBoxLayout()

        self.list_widget = ListWidget()
        layout.addWidget(self.list_widget)

        self.setLayout(layout)

        self.messages = RingBuffer(100)
        self.messages_cache_file = get_cache_path("pushover/messages.json")

        self.update_thread = ThreadedRequest("get", "https://api.pushover.net/1/messages.json", params={"secret": self.secret, "device_id": self.device_id})

    def start_view(self):
        if os.path.exists(self.messages_cache_file):
            with open(self.messages_cache_file, "r") as cache_file:
                loaded_data = json.load(cache_file)

                self.unseen_messages = loaded_data["unseen_messages"]
                if self.isVisible():
                    self.unseen_messages = 0

                loaded_messages = sorted(loaded_data["messages"], key=lambda item: item["id"])

                for message in loaded_messages:
                    self.add_message(message)

        self.update_tab()
        self.update_list()

        self.visibility_changed.connect(self.on_visibility_changed)

        self.update_thread.ready.connect(self.fetch_new_messages)

        websocket_thread = WebSocketThread(self, self.secret, self.device_id)
        websocket_thread.sync.connect(self.update_thread.start)
        websocket_thread.start()

    def on_visibility_changed(self, state: bool):
        if state:
            if self.unseen_messages:
                self.unseen_messages = 0

                self.save_messages()

        self.update_tab()

    def save_messages(self):
        os.makedirs(os.path.dirname(self.messages_cache_file), exist_ok=True)

        temp_file = "{}.tmp".format(self.messages_cache_file)

        with open(temp_file, "w") as cache_file:
            json.dump({
                "messages": list(self.messages),
                "unseen_messages": self.unseen_messages
            }, cache_file)

        os.rename(temp_file, self.messages_cache_file)

    def fetch_new_messages(self, response: requests.Response):
        new_messages = sorted(response.json()["messages"], key=lambda list_item: list_item["id"])

        if new_messages:
            for message in new_messages:
                self.add_message(message)

            if self.isVisible():
                self.unseen_messages = 0
            else:
                self.unseen_messages += len(new_messages)
                self.update_tab()

            self.save_messages()

            requests.post("https://api.pushover.net/1/devices/{}/update_highest_message.json".format(self.device_id), data={"secret": self.secret, "message": new_messages[-1]["id"]})

        self.update_list()

    def update_list(self):
        self.list_widget.clear()

        image_urls = {}

        for item in reversed(self.messages):
            icon_name = item["icon"]

            image_urls[icon_name] = "https://api.pushover.net/icons/{}.png".format(icon_name)

            self.list_widget.add_row(item)

        if self.download_thread is None or not self.download_thread.isRunning():
            # Download icons and cleanup cached images after 7 days
            self.download_thread = ThreadedDownloadAndCache("images/icons", image_urls, cleanup_age=60 * 60 * 24 * 7)
            self.list_widget.image_cache_dir = self.download_thread.cache_dir
            self.download_thread.file_done.connect(self.list_widget.update_image)
            self.download_thread.start()

    def update_tab(self):
        if self.tab_id_status is None:
            return

        tab_widget, tab_index = self.dashboard_instance.tab_by_id(self.tab_id_status)
        if tab_widget is not None:
            if self.unseen_messages:
                tab_title = " ({})".format(self.unseen_messages)
                tab_icon = self.new_messages_icon
            else:
                tab_title = None
                tab_icon = QtGui.QIcon()

            tab_widget.append_tab_title(tab_index, tab_title)
            tab_widget.setTabIcon(tab_index, tab_icon)

    def add_message(self, message):
        if list(filter(lambda this_message: this_message["id"] == message["id"], self.messages)):
            return

        self.messages.append(message)
