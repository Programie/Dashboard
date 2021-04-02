import datetime
import os
import subprocess
import time
import traceback
from collections import deque
from typing import Dict

import requests
from PyQt5 import QtCore, QtWidgets, QtChart, QtGui


class AbstractView:
    visibility_changed = QtCore.pyqtSignal(bool)

    def showEvent(self, event: QtGui.QShowEvent):
        self.showEvent(event)
        self.visibility_changed.emit(True)

    def hideEvent(self, event: QtGui.QHideEvent):
        self.hideEvent(event)
        self.visibility_changed.emit(False)

    def start_view(self):
        pass


class RingBuffer(deque):
    def __init__(self, size):
        deque.__init__(self)
        self.size = size

    def full_append(self, item):
        deque.append(self, item)
        self.popleft()

    def append(self, item):
        deque.append(self, item)

        if len(self) == self.size:
            self.append = self.full_append

    def get(self):
        return list(self)


class ThreadedRequest(QtCore.QThread):
    ready = QtCore.pyqtSignal(requests.Response)

    def __init__(self, method, url, params=None, parent=None, **kwargs):
        QtCore.QThread.__init__(self, parent)

        kwargs.setdefault("allow_redirects", True)

        self.method = method
        self.url = url
        self.params = params
        self.kwargs = kwargs

        self.response = None

    def run(self):
        try:
            self.response = requests.request(self.method, self.url, params=self.params, **self.kwargs)
            self.ready.emit(self.response)
        except:
            traceback.print_exc()


class ThreadedRequests(QtCore.QThread):
    ready = QtCore.pyqtSignal(dict)

    def __init__(self, requests_to_execute: Dict[str, ThreadedRequest], parent=None):
        QtCore.QThread.__init__(self, parent)

        self.requests_to_execute = requests_to_execute

    def run(self):
        for request in self.requests_to_execute.values():
            request.start()

        responses = {}

        for name, request in self.requests_to_execute.items():
            request.wait()
            responses[name] = request.response

        self.ready.emit(responses)


class ThreadedDownloadAndCache(QtCore.QThread):
    all_done = QtCore.pyqtSignal(dict)
    file_done = QtCore.pyqtSignal(object, str, int, int)
    finished = QtCore.pyqtSignal()

    def __init__(self, cache_dir_name: str, urls: Dict[str, str], max_age: int = None, cleanup_age: int = None):
        QtCore.QThread.__init__(self)

        self.urls = urls
        self.max_age = max_age
        self.cleanup_age = cleanup_age
        self.stop_requested = False

        self.cache_dir = get_cache_path(cache_dir_name)

    def download_and_cache(self, name: str, url: str):
        os.makedirs(self.cache_dir, exist_ok=True)

        filename_path = os.path.join(self.cache_dir, name)

        if os.path.exists(filename_path):
            file_age = time.time() - os.path.getmtime(filename_path)
        else:
            file_age = None

        if file_age is None or (self.max_age is not None and file_age >= self.max_age):
            with requests.get(url, stream=True) as response:
                response.raise_for_status()

                with open(filename_path, "wb") as cache_file:
                    for chunk in response.iter_content(chunk_size=8192):
                        cache_file.write(chunk)

        return filename_path

    def run(self):
        if self.cleanup_age is not None and os.path.isdir(self.cache_dir):
            for dir_item in os.listdir(self.cache_dir):
                filename_path = os.path.join(self.cache_dir, dir_item)

                if not os.path.isfile(filename_path):
                    continue

                file_age = time.time() - os.path.getmtime(filename_path)

                if file_age >= self.cleanup_age:
                    os.unlink(filename_path)

        paths = {}

        for name, url in self.urls.items():
            try:
                path = self.download_and_cache(name, url)
                paths[name] = path
                self.file_done.emit(name, path, len(paths), len(self.urls))
            except:
                traceback.print_exc()

            # Stop requested -> do not emit all_done signal
            if self.stop_requested:
                self.finished.emit()
                return

        self.all_done.emit(paths)
        self.finished.emit()

    def stop(self):
        self.stop_requested = True


class Timer(QtCore.QObject):
    timeout = QtCore.pyqtSignal()

    def __init__(self, parent, interval, view: AbstractView, auto_enable=True):
        super().__init__(parent)

        self.timer = QtCore.QTimer(parent)
        self.timer.timeout.connect(self.emit)

        self.interval = interval
        self.last_emit = None

        if auto_enable:
            view.visibility_changed.connect(self.visibility_changed)
            self.visibility_changed(view.isVisible())

    def start(self):
        self.timer.start(self.interval)

        if self.last_emit is None or self.time() - self.last_emit >= self.interval:
            self.emit()

    def stop(self):
        self.timer.stop()

    def visibility_changed(self, state: bool):
        if state:
            self.start()
        else:
            self.stop()

    def emit(self):
        self.last_emit = self.time()
        self.timeout.emit()

    @staticmethod
    def time():
        return time.time() * 1000


class HorizontalScrollArea(QtWidgets.QScrollArea):
    def __init__(self):
        super().__init__()

        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

    def eventFilter(self, event_object: QtCore.QObject, event: QtCore.QEvent):
        if event_object == self.widget() and event.type() == QtCore.QEvent.Resize:
            height = self.widget().minimumSizeHint().height() + self.horizontalScrollBar().height()

            self.setMinimumHeight(height)
            self.setMaximumHeight(height)

        return False


class ChartWindow(QtWidgets.QDialog):
    def __init__(self, parent, value_label_format="%i", date_time_format="hh:mm"):
        super().__init__(parent)

        self.chart = QtChart.QChart()
        self.chart.setTheme(QtChart.QChart.ChartThemeDark)
        self.chart.setMargins(QtCore.QMargins(0, 0, 0, 0))
        self.chart.setBackgroundVisible(False)
        self.chart.legend().hide()

        self.value_series = QtChart.QLineSeries()
        self.lower_series = QtChart.QLineSeries()
        area_series = QtChart.QAreaSeries(self.value_series, self.lower_series)
        self.chart.addSeries(area_series)

        axis_x = QtChart.QDateTimeAxis()
        axis_x.setFormat(date_time_format)
        axis_x.setTitleText("Time")
        self.chart.addAxis(axis_x, QtCore.Qt.AlignBottom)
        area_series.attachAxis(axis_x)

        axis_y = QtChart.QValueAxis()
        axis_y.setLabelFormat(value_label_format)
        axis_y.setTitleText("Value")
        self.chart.addAxis(axis_y, QtCore.Qt.AlignLeft)
        area_series.attachAxis(axis_y)

        self.chart_view = QtChart.QChartView(self.chart)
        self.chart_view.setRenderHint(QtGui.QPainter.Antialiasing)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.chart_view)
        self.setLayout(layout)

        self.resize(800, 500)

    def set_data(self, entries):
        values = [entry["value"] for entry in entries]

        if len(entries):
            first_date = QtCore.QDateTime.fromString(entries[0]["time"], QtCore.Qt.ISODateWithMs)
            last_date = QtCore.QDateTime.fromString(entries[-1]["time"], QtCore.Qt.ISODateWithMs)
        else:
            first_date = QtCore.QDateTime.currentDateTime()
            last_date = QtCore.QDateTime.currentDateTime()

        min_value = min(values)
        max_value = max(values)
        chart_values = []
        lower_values = []

        if min_value == max_value:
            min_value = min_value - 5
            max_value = max_value + 5

        for entry in entries:
            date = QtCore.QDateTime.fromString(entry["time"], QtCore.Qt.ISODateWithMs)

            chart_values.append(QtCore.QPointF(date.toMSecsSinceEpoch(), entry["value"]))
            lower_values.append(QtCore.QPointF(date.toMSecsSinceEpoch(), min_value))

        self.value_series.replace(chart_values)
        self.lower_series.replace(lower_values)

        self.chart.axisX().setRange(first_date, last_date)
        self.chart.axisY().setRange(min_value, max_value)


def format_timedelta(delta: datetime.timedelta, with_seconds=False):
    strings = []

    if delta.days:
        strings.append("{} {}".format(delta.days, "day" if delta.days == 1 else "days"))

    hours, seconds = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(seconds, 60)

    if hours:
        strings.append("{} {}".format(hours, "hour" if hours == 1 else "hours"))

    if minutes:
        strings.append("{} {}".format(minutes, "minute" if minutes == 1 else "minutes"))

    if (seconds and with_seconds) or not strings:
        strings.append("{} {}".format(seconds, "second" if seconds == 1 else "seconds"))

    return ", ".join(strings)


def get_cache_path(name: str):
    return os.path.join(QtCore.QStandardPaths.standardLocations(QtCore.QStandardPaths.CacheLocation)[0], name)


def disable_screensaver(window_id, state: bool):
    if state:
        subprocess.call(["xdg-screensaver", "suspend", str(int(window_id))])
    else:
        subprocess.call(["xdg-screensaver", "resume", str(int(window_id))])
