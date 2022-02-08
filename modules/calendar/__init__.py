import datetime
import traceback
import uuid
from collections import OrderedDict

import dateutil.rrule
from typing import List, Dict

import caldav
import dbus.service
import dbus.mainloop.glib
import pandas
from PyQt5 import QtCore, QtWidgets, QtGui
from caldav.elements import ical
from vobject import icalendar

from lib.common import Timer, AbstractView, get_dashboard_instance


# Also used in Tasks module
def escape_ical_string(string):
    characters_to_escape = '\\;,"'

    escaped_string = []

    for character in string:
        if character in characters_to_escape:
            character = "\\" + character

        escaped_string.append(character)

    return "".join(escaped_string)


# Also used in Tasks module
class Calendar(caldav.Calendar):
    def __init__(self, **extra):
        super().__init__(**extra)

        self.color = None
        self.icon = None
        self.supported_components = None

    def get_color(self):
        if not hasattr(self, "color"):
            self.color = self.get_properties([ical.CalendarColor()])["{http://apple.com/ns/ical/}calendar-color"]

        return self.color

    def get_icon(self):
        if not hasattr(self, "icon"):
            pixmap = QtGui.QPixmap(100, 100)
            pixmap.fill(QtGui.QColor(self.get_color()))
            self.icon = QtGui.QIcon(pixmap)

        return self.icon

    def supports_component(self, component):
        if not hasattr(self, "supported_components"):
            self.supported_components = super().get_supported_components()

        if not self.supported_components:
            return True

        return component in self.supported_components


class CalendarEventDialog(QtWidgets.QDialog):
    def __init__(self, parent, calendars: Dict[str, Calendar], date: QtCore.QDate, default_calendar=None, updater_thread: "Updater" = None):
        super().__init__(parent)

        self.updater_thread = updater_thread

        self.setModal(True)
        self.setWindowTitle("New event")

        layout = QtWidgets.QGridLayout()
        self.setLayout(layout)

        layout.addWidget(QtWidgets.QLabel("Calendar"), 0, 0)

        self.calendar_dropdown = QtWidgets.QComboBox()

        for calendar in calendars.values():
            self.calendar_dropdown.addItem(calendar.get_icon(), calendar.name, calendar)

        if default_calendar is not None:
            self.calendar_dropdown.setCurrentText(default_calendar)

        layout.addWidget(self.calendar_dropdown, 0, 1, 1, -1)

        layout.addWidget(QtWidgets.QLabel("Title"), 1, 0)

        self.title_widget = QtWidgets.QLineEdit()
        layout.addWidget(self.title_widget, 1, 1)

        layout.addWidget(QtWidgets.QLabel("Date"), 2, 0)

        self.date_widget = QtWidgets.QDateEdit(date)
        self.date_widget.setCalendarPopup(True)
        self.date_widget.calendarWidget().setFirstDayOfWeek(QtCore.Qt.Monday)
        self.date_widget.setDisplayFormat("dd.MM.yyyy")
        layout.addWidget(self.date_widget, 2, 1)

        self.time_checkbox = QtWidgets.QCheckBox("Time")
        self.time_checkbox.stateChanged.connect(self.update_time_widgets)
        layout.addWidget(self.time_checkbox, 3, 0)

        time_layout = QtWidgets.QHBoxLayout()
        self.start_time_widget = QtWidgets.QTimeEdit()
        self.start_time_widget.setDisplayFormat("HH:mm")
        time_layout.addWidget(self.start_time_widget, 1)

        time_layout.addWidget(QtWidgets.QLabel("-"), 0)

        self.end_time_widget = QtWidgets.QTimeEdit()
        self.end_time_widget.setDisplayFormat("HH:mm")
        time_layout.addWidget(self.end_time_widget, 1)

        layout.addLayout(time_layout, 3, 1)

        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        layout.addWidget(button_box, 4, 0, 1, -1)

        button_box.accepted.connect(self.save)
        button_box.rejected.connect(self.close)

        self.update_time_widgets()
        self.show()
        self.setFixedSize(self.size())

    def update_time_widgets(self):
        enabled = self.time_checkbox.isChecked()

        self.start_time_widget.setEnabled(enabled)
        self.end_time_widget.setEnabled(enabled)

    def save(self):
        title = self.title_widget.text().strip()

        if not title:
            QtWidgets.QMessageBox.critical(self, self.windowTitle(), "No title given!")
            return

        date = self.date_widget.date()
        start_time = self.start_time_widget.time()
        end_time = self.end_time_widget.time()

        year = date.year()
        month = date.month()
        day = date.day()

        if self.time_checkbox.isChecked():
            start_date = datetime.datetime(year, month, day, start_time.hour(), start_time.minute(), start_time.second())
            end_date = datetime.datetime(year, month, day, end_time.hour(), end_time.minute(), end_time.second())
            date_format = "%Y%m%dT%H%M%S"
        else:
            start_date = datetime.datetime(year, month, day)
            end_date = start_date + datetime.timedelta(days=1)
            date_format = "%Y%m%d"

        ics = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Dashboard//CalDAV Client//EN",
            "BEGIN:VEVENT",
            "UID:{}@dashboard.selfcoders.com".format(uuid.uuid4()),
            "DTSTAMP:{}".format(datetime.datetime.now().strftime("%Y%m%dT%H%M%S")),
            "DTSTART:{}".format(start_date.strftime(date_format)),
            "DTEND:{}".format(end_date.strftime(date_format)),
            "SUMMARY:{}".format(escape_ical_string(title)),
            "END:VEVENT",
            "END:VCALENDAR"
        ]

        calendar = self.calendar_dropdown.currentData(QtCore.Qt.UserRole)
        calendar.add_event("\n".join(ics))

        if self.updater_thread:
            self.updater_thread.start()

        self.accept()


class Event:
    def __init__(self, vevent: icalendar.RecurringComponent, calendar: Calendar, upcoming_days: int, past_days: int):
        self.vevent = vevent
        self.calendar = calendar
        self.upcoming_days = upcoming_days
        self.past_days = past_days

    def get_dates(self):
        rrule = self.vevent.getChildValue("rrule")
        if rrule:
            return self.get_from_rrule(rrule)
        else:
            return self.get_in_range(self.vevent.getChildValue("dtstart"), self.vevent.getChildValue("dtend"))

    def get_from_rrule(self, rrule):
        today_date = datetime.date.today()
        today = datetime.datetime(today_date.year, today_date.month, today_date.day)
        range_start = today - datetime.timedelta(days=self.past_days)
        range_end = today + datetime.timedelta(days=self.upcoming_days)

        start_datetime = self.vevent.getChildValue("dtstart")
        end_datetime = self.vevent.getChildValue("dtend")
        if isinstance(start_datetime, datetime.datetime):
            start_datetime = start_datetime.astimezone().replace(tzinfo=None)
        if isinstance(end_datetime, datetime.datetime):
            end_datetime = end_datetime.astimezone().replace(tzinfo=None)

        exdate_list = self.vevent.getChildValue("exdate")

        if not exdate_list:
            exdate_list = []

        for index, exdate in enumerate(exdate_list):
            if not isinstance(exdate, datetime.datetime):
                exdate = datetime.datetime(exdate.year, exdate.month, exdate.day)

            exdate_list[index] = exdate.astimezone().replace(tzinfo=None)

        rules = dateutil.rrule.rruleset()
        rules.rrule(dateutil.rrule.rrulestr(rrule, dtstart=start_datetime))

        for exdate in exdate_list:
            rules.exdate(exdate)

        start_end_diff = end_datetime - start_datetime

        all_dates = []
        dates = rules.between(range_start, range_end, True)
        for date in dates:
            # dateutil.rrule.rruleset.between() always returns a datetime object?
            if not isinstance(start_datetime, datetime.datetime):
                date = date.date()

            all_dates.extend(self.get_in_range(date, date + start_end_diff))

        return all_dates

    def get_in_range(self, start, end):
        if isinstance(start, datetime.datetime):
            start = start.astimezone().replace(tzinfo=None)
            all_day_event = False
        else:
            all_day_event = True

        if isinstance(end, datetime.datetime):
            end = end.astimezone().replace(tzinfo=None)

        return pandas.date_range(start=start, end=end, closed="left" if all_day_event else None).tolist()

    def get_summary(self):
        return self.vevent.getChildValue("summary")

    def get_summary_with_time(self):
        datetime_start = self.vevent.getChildValue("dtstart")

        summary = self.get_summary()

        if isinstance(datetime_start, datetime.datetime):
            return "{} {}".format(datetime_start.strftime("%H:%M"), summary)
        else:
            return summary


class CalendarEventList(QtWidgets.QListWidget):
    def update_list(self, events, filter_string):
        self.clear()

        for date_events in events.values():
            header_created = False

            for date, event in date_events:
                if filter_string != "" and filter_string.lower() not in event.get_summary().lower():
                    continue

                if not header_created:
                    self.create_header_item(date)
                    header_created = True

                list_item = QtWidgets.QListWidgetItem(event.calendar.get_icon(), event.get_summary_with_time())
                list_item.setData(QtCore.Qt.ItemDataRole.UserRole, ("event", date, event))
                self.addItem(list_item)

    def create_header_item(self, date: datetime.datetime):
        item = QtWidgets.QListWidgetItem(date.strftime("%Y-%m-%d"))
        item.setFlags(QtCore.Qt.ItemFlag.NoItemFlags)
        item.setData(QtCore.Qt.ItemDataRole.UserRole, ("header", date))

        font = item.font()
        font.setPointSize(font.pointSize() + 5)
        item.setFont(font)

        self.addItem(item)

    def scroll_to_date(self, date: QtCore.QDate):
        date = datetime.datetime(date.year(), date.month(), date.day())

        scroll_to_item = None

        for index in range(self.count() - 1):
            item = self.item(index)
            item_data = item.data(QtCore.Qt.ItemDataRole.UserRole)

            if item_data[0] != "header":
                continue

            item_date: datetime.datetime = item_data[1]
            if datetime.datetime(item_date.year, item_date.month, item_date.day) > date:
                break

            scroll_to_item = item

        if scroll_to_item is None:
            self.scrollToTop()
        else:
            self.scrollToItem(scroll_to_item, QtWidgets.QListWidget.PositionAtTop)


class SearchBar(QtWidgets.QLineEdit):
    search_triggered = QtCore.pyqtSignal(str)

    def __init__(self):
        super().__init__()

        self.previous_focus = None

        self.setPlaceholderText("Search...")

        escape_action = QtWidgets.QAction(self)
        escape_action.setShortcut(QtCore.Qt.Key.Key_Escape)
        escape_action.setShortcutContext(QtCore.Qt.ShortcutContext.WidgetShortcut)
        escape_action.triggered.connect(self.deactivate)
        self.addAction(escape_action)

        self.textChanged.connect(self.search)

    def search(self):
        self.search_triggered.emit(self.text().strip())

    def activate(self):
        self.previous_focus = QtWidgets.QApplication.focusWidget()

        self.setText("")
        self.setVisible(True)
        self.setFocus()

    def deactivate(self):
        self.setVisible(False)

        if self.previous_focus:
            self.previous_focus.setFocus()

        self.search_triggered.emit("")


class Updater(QtCore.QThread):
    ready = QtCore.pyqtSignal(dict)

    def __init__(self, calendars: List[caldav.Calendar], upcoming_days: int, past_days: int):
        QtCore.QThread.__init__(self)

        self.calendars = calendars
        self.upcoming_days = upcoming_days
        self.past_days = past_days

    def run(self):
        try:
            events = {}

            today = datetime.date.today()
            start_date = today - datetime.timedelta(days=self.past_days)
            end_date = today + datetime.timedelta(days=self.upcoming_days)

            for calendar in self.calendars:
                # TODO: Specifying end date in date_search does not return recurring events (at least with Nextcloud)
                events[str(calendar.url)] = calendar.date_search(start=start_date)

            self.ready.emit(events)
        except:
            traceback.print_exc()


class DBusHandler(dbus.service.Object):
    def __init__(self, view_instance: "View", session_bus: dbus.Bus):
        dbus.service.Object.__init__(self, session_bus, "/calendar")

        self.view_instance = view_instance

    @dbus.service.method("com.selfcoders.Dashboard", in_signature="", out_signature="")
    def show_create_dialog(self):
        self.view_instance.show_add_event_dialog(QtGui.QCursor.pos())


class CalendarManager:
    def __init__(self, url, username, password):
        client = caldav.DAVClient(url, username=username, password=password)

        self.unfiltered_calendars = sorted(client.principal().calendars(), key=lambda calendar_item: calendar_item.name)

        for calendar in self.unfiltered_calendars:
            calendar.__class__ = Calendar

        self.calendars = self.filter_calendars_with_component(self.unfiltered_calendars, "VEVENT")

    @staticmethod
    def filter_calendars_with_component(calendars: List[Calendar], component: str):
        return [calendar for calendar in calendars if calendar.supports_component(component)]


class View(QtWidgets.QWidget, AbstractView):
    def __init__(self, url, username, password, default_calendar=None, upcoming_days=365, past_days=0, highlight_color="#FFD800"):
        super().__init__()

        self.default_calendar = default_calendar
        self.upcoming_days = upcoming_days
        self.past_days = past_days
        self.highlight_color = highlight_color

        DBusHandler(self, get_dashboard_instance().session_dbus)

        calendar_manager = CalendarManager(url, username, password)

        self.events = {}
        self.search_filter = ""

        self.updater = Updater(calendar_manager.unfiltered_calendars, upcoming_days, past_days)
        self.updater.ready.connect(self.update_events)

        self.calendars = {str(calendar.url): calendar for calendar in calendar_manager.calendars}

        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)

        self.calendar_widget = QtWidgets.QCalendarWidget()
        self.calendar_widget.setFirstDayOfWeek(QtCore.Qt.Monday)
        self.calendar_widget.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)
        self.calendar_widget.selectionChanged.connect(self.scroll_to_selected_date)
        layout.addWidget(self.calendar_widget, 0)

        self.add_event_action = QtWidgets.QAction("Create event", self)
        self.add_event_action.triggered.connect(lambda: self.show_add_event_dialog(None))
        self.calendar_widget.addAction(self.add_event_action)

        self.jump_to_today_action = QtWidgets.QAction("Jump to today", self)
        self.jump_to_today_action.triggered.connect(self.jump_to_today)
        self.calendar_widget.addAction(self.jump_to_today_action)

        self.event_list_widget = CalendarEventList()
        self.event_list_widget.currentItemChanged.connect(self.event_list_item_changed)
        layout.addWidget(self.event_list_widget, 1)

        self.search_bar = SearchBar()
        self.search_bar.search_triggered.connect(self.set_search_filter)
        self.search_bar.deactivate()
        layout.addWidget(self.search_bar, 0)

        search_action = QtWidgets.QShortcut(self)
        search_action.setKey(QtCore.Qt.Modifier.CTRL | QtCore.Qt.Key.Key_F)
        search_action.setContext(QtCore.Qt.WidgetWithChildrenShortcut)
        search_action.activated.connect(self.search_bar.activate)

        timer = Timer(self, 300000, self)
        timer.timeout.connect(self.updater.start)

    def show_add_event_dialog(self, position: QtCore.QPoint = None):
        dialog = CalendarEventDialog(self, self.calendars, self.calendar_widget.selectedDate(), self.default_calendar, self.updater)

        if position is not None:
            dialog.move(position)

    def jump_to_today(self):
        self.calendar_widget.setSelectedDate(QtCore.QDate.currentDate())

    def update_events(self, events_per_calendar: Dict[str, List[caldav.Event]]):
        today = datetime.date.today()
        start_date = today - datetime.timedelta(days=self.past_days)
        end_date = today + datetime.timedelta(days=self.upcoming_days)

        self.calendar_widget.setMinimumDate(QtCore.QDate(start_date.year, start_date.month, start_date.day))
        self.calendar_widget.setMaximumDate(QtCore.QDate(end_date.year, end_date.month, end_date.day))

        for date in self.calendar_widget.dateTextFormat().keys():
            self.calendar_widget.setDateTextFormat(date, QtGui.QTextCharFormat())

        self.calendar_widget.setWeekdayTextFormat(QtCore.Qt.Saturday, QtGui.QTextCharFormat())
        self.calendar_widget.setWeekdayTextFormat(QtCore.Qt.Sunday, QtGui.QTextCharFormat())

        today_format = QtGui.QTextCharFormat()
        today_format.setFontWeight(QtGui.QFont.Bold)
        self.calendar_widget.setDateTextFormat(QtCore.QDate(today.year, today.month, today.day), today_format)

        highlight_format = QtGui.QTextCharFormat()
        highlight_format.setFontUnderline(True)
        highlight_format.setForeground(QtGui.QBrush(QtGui.QColor(self.highlight_color)))

        self.events = {}

        for calendar_url, events in events_per_calendar.items():
            for event in events:
                event = Event(event.vobject_instance.vevent, self.calendars[calendar_url], self.upcoming_days, self.past_days)

                for date in event.get_dates():
                    date_object = QtCore.QDate(date.year, date.month, date.day)
                    self.calendar_widget.setDateTextFormat(date_object, highlight_format)

                    if date.date() == today:
                        text_format: QtGui.QTextCharFormat = self.calendar_widget.dateTextFormat(date_object)
                        text_format.setFontWeight(QtGui.QFont.Bold)
                        self.calendar_widget.setDateTextFormat(date_object, text_format)

                    date_string = date.strftime("%Y-%m-%d")
                    if date_string not in self.events:
                        self.events[date_string] = []

                    self.events[date_string].append((date, event))

        self.events = OrderedDict(sorted(self.events.items()))

        self.event_list_widget.update_list(self.events, self.search_filter)
        self.scroll_to_selected_date()

    def scroll_to_selected_date(self):
        self.event_list_widget.scroll_to_date(self.calendar_widget.selectedDate())

    def event_list_item_changed(self, item: QtWidgets.QListWidgetItem):
        if item is None:
            return

        item_data = item.data(QtCore.Qt.UserRole)

        if item_data is None:
            return

        if item_data[0] != "event":
            return

        _, date, event = item_data

        block_signals = self.calendar_widget.blockSignals(True)
        self.calendar_widget.setSelectedDate(QtCore.QDate(date))
        self.calendar_widget.blockSignals(block_signals)

    def set_search_filter(self, search_string):
        self.search_filter = search_string

        self.event_list_widget.update_list(self.events, self.search_filter)
