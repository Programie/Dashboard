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
from dateutil.tz import tzlocal
from pytz import timezone
from vobject import icalendar

from lib.common import Timer, AbstractView, get_dashboard_instance


def escape_ical_string(string):
    characters_to_escape = '\\;,"'

    escaped_string = []

    for character in string:
        if character in characters_to_escape:
            character = "\\" + character

        escaped_string.append(character)

    return "".join(escaped_string)


class TodoItem:
    def __init__(self, todo: caldav.Todo):
        self.parent: "TodoItem" = None
        self.children: Dict[str, "TodoItem"] = {}
        self.todo = todo
        self.vtodo = todo.vobject_instance.vtodo

        if hasattr(self.vtodo, "due"):
            due_datetime = self.vtodo.due.value

            # due datetime might be a date instead of datetime object, therefore convert it to a datetime object
            if not isinstance(due_datetime, datetime.datetime):
                due_datetime = datetime.datetime.combine(due_datetime, datetime.datetime.min.time())

            self.due_datetime: datetime.datetime = due_datetime.astimezone(timezone("UTC"))
        else:
            self.due_datetime = None

    def add_child(self, item: "TodoItem"):
        self.children[item.get_id()] = item
        item.parent = self

    def get_id(self):
        return self.vtodo.uid.value

    def get_parent_id(self):
        if hasattr(self.vtodo, "related_to"):
            return self.vtodo.related_to.value
        else:
            return None

    def is_overdue(self):
        if self.due_datetime is None:
            return False

        return self.due_datetime < datetime.datetime.now(tz=timezone("UTC"))

    def complete(self):
        self.todo.complete()

    @staticmethod
    def create(calendar: caldav.Calendar, summary: str, description: str = ""):
        ics = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Dashboard//CalDAV Client//EN",
            "BEGIN:VTODO",
            "UID:{}@dashboard.selfcoders.com".format(uuid.uuid4()),
            "DTSTAMP:{}".format(datetime.datetime.now().astimezone(tz=timezone("UTC")).strftime("%Y%m%dT%H%M%SZ")),
            "SUMMARY:{}".format(escape_ical_string(summary)),
            "DESCRIPTION:{}".format(escape_ical_string(description)),
            "END:VTODO",
            "END:VCALENDAR"
        ]

        calendar.add_todo("\n".join(ics))


class TodoDialog(QtWidgets.QDialog):
    def __init__(self, parent, calendars: List["Calendar"], default_todo_list=None, todo_item: TodoItem = None, updater_thread: "Updater" = None):
        super().__init__(parent)

        self.todo_item = todo_item
        self.updater_thread = updater_thread

        self.setModal(True)

        if todo_item is None:
            self.setWindowTitle("New todo")
        else:
            self.setWindowTitle("Edit todo")

        layout = QtWidgets.QGridLayout()
        self.setLayout(layout)

        layout.addWidget(QtWidgets.QLabel("Calendar"), 0, 0)

        self.calendar_dropdown = QtWidgets.QComboBox()

        for calendar in calendars:
            self.calendar_dropdown.addItem(calendar.get_icon(), calendar.name, calendar)

        if default_todo_list is not None:
            self.calendar_dropdown.setCurrentText(default_todo_list)

        if self.todo_item is not None:
            self.calendar_dropdown.setDisabled(True)

        layout.addWidget(self.calendar_dropdown, 0, 1, 1, -1)

        layout.addWidget(QtWidgets.QLabel("Title"), 1, 0)

        self.title_widget = QtWidgets.QLineEdit()

        if todo_item is not None and hasattr(todo_item.vtodo, "summary"):
            self.title_widget.setText(todo_item.vtodo.summary.value)

        layout.addWidget(self.title_widget, 1, 1)

        layout.addWidget(QtWidgets.QLabel("Notes"), 2, 0)

        self.notes_widget = QtWidgets.QTextEdit()

        if todo_item is not None and hasattr(todo_item.vtodo, "description"):
            self.notes_widget.setPlainText(todo_item.vtodo.description.value)

        layout.addWidget(self.notes_widget, 2, 1)

        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        layout.addWidget(button_box, 4, 0, 1, -1)

        button_box.accepted.connect(self.save)
        button_box.rejected.connect(self.close)

        self.show()
        self.setFixedSize(self.size())

    def save(self):
        calendar: caldav.Calendar = self.calendar_dropdown.currentData(QtCore.Qt.UserRole)
        title = self.title_widget.text().strip()
        notes = self.notes_widget.toPlainText().strip()

        if not title:
            QtWidgets.QMessageBox.critical(self, self.windowTitle(), "No title given!")
            return

        if self.todo_item is None:
            TodoItem.create(calendar, title, notes)
        else:
            if hasattr(self.todo_item.vtodo, "summary"):
                self.todo_item.vtodo.summary.value = title
            else:
                self.todo_item.vtodo.add("summary").value = title

            if hasattr(self.todo_item.vtodo, "description"):
                self.todo_item.vtodo.description.value = notes
            else:
                self.todo_item.vtodo.add("description").value = notes

            self.todo_item.todo.save()

        if self.updater_thread:
            self.updater_thread.start()

        self.accept()


class TodoListWidget(QtWidgets.QTreeWidget):
    def __init__(self, view_widget: "View", calendar: "Calendar", calendar_manager: "CalendarManager"):
        super().__init__()

        self.view_widget = view_widget
        self.calendar = calendar
        self.calendar_manager = calendar_manager
        self.overdue_todo_item = None

        self.setHeaderHidden(True)
        self.itemChanged.connect(self.update_todo)
        self.itemDoubleClicked.connect(self.show_todo)

    def update_items(self, todos):
        todo_items = {}

        for item in todos:
            todo_item = TodoItem(item)

            todo_items[todo_item.get_id()] = todo_item

        todo_item: TodoItem
        for todo_item in todo_items.values():
            parent_id = todo_item.get_parent_id()

            if parent_id is not None and parent_id in todo_items:
                todo_items[parent_id].add_child(todo_item)

        root_items = []
        for todo_item in todo_items.values():
            parent_id = todo_item.get_parent_id()

            if parent_id is not None and parent_id in todo_items:
                continue

            root_items.append(todo_item)

        self.overdue_todo_item = None
        self.clear()
        self.add_from_list(self, root_items)

    def add_from_list(self, parent_item, todo_items: List[TodoItem]):
        for todo_item in todo_items:
            summary = todo_item.vtodo.summary.value

            text = summary

            if todo_item.due_datetime is not None:
                text = "{} ({})".format(summary, todo_item.due_datetime.astimezone(tzlocal()).strftime("%d.%m.%Y %H:%M"))

            list_item = QtWidgets.QTreeWidgetItem(parent_item)

            list_item.setText(0, text)
            list_item.setToolTip(0, text)
            list_item.setFlags(list_item.flags() | QtCore.Qt.ItemIsTristate | QtCore.Qt.ItemIsUserCheckable)
            list_item.setCheckState(0, QtCore.Qt.Unchecked)
            list_item.setExpanded(True)
            list_item.setData(0, QtCore.Qt.UserRole, todo_item)

            if todo_item.due_datetime is not None:
                if todo_item.is_overdue():
                    self.overdue_todo_item = todo_item
                    list_item.setForeground(0, QtGui.QBrush(QtGui.QColor("red")))
                else:
                    list_item.setForeground(0, QtGui.QBrush(QtGui.QColor("#FFD800")))

            self.add_from_list(list_item, [child_item for child_item in todo_item.children.values()])

    def show_todo(self, list_item: QtWidgets.QListWidgetItem):
        if list_item is None:
            return

        todo_item: TodoItem = list_item.data(0, QtCore.Qt.UserRole)

        TodoDialog(self, self.calendar_manager.todo_lists, self.calendar.name, todo_item, self.view_widget.updater)

    def update_todo(self, list_item: QtWidgets.QListWidgetItem):
        todo_item: TodoItem = list_item.data(0, QtCore.Qt.UserRole)

        if list_item.checkState(0) == QtCore.Qt.Checked:
            todo_item.complete()


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
            start_date = datetime.datetime(year, month, day, start_time.hour(), start_time.minute(), start_time.second()).astimezone(tz=timezone("UTC"))
            end_date = datetime.datetime(year, month, day, end_time.hour(), end_time.minute(), end_time.second()).astimezone(tz=timezone("UTC"))
            date_format = "%Y%m%dT%H%M%SZ"
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
            "DTSTAMP:{}".format(datetime.datetime.now().astimezone(tz=timezone("UTC")).strftime("%Y%m%dT%H%M%SZ")),
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
        today_date = datetime.date.today()
        today = datetime.datetime(today_date.year, today_date.month, today_date.day)
        start_date = today - datetime.timedelta(days=self.past_days)
        end_date = today + datetime.timedelta(days=self.upcoming_days)

        rrule = self.vevent.getChildValue("rrule")
        if rrule:
            start_datetime = self.vevent.getChildValue("dtstart")
            if isinstance(start_datetime, datetime.datetime):
                start_datetime = start_datetime.astimezone().replace(tzinfo=None)

            exdate_list = self.vevent.getChildValue("exdate")

            if not exdate_list:
                exdate_list = []

            for index, exdate in enumerate(exdate_list):
                if isinstance(exdate, datetime.date):
                    exdate = datetime.datetime(exdate.year, exdate.month, exdate.day)

                exdate_list[index] = exdate.astimezone().replace(tzinfo=None)

            rules = dateutil.rrule.rruleset()
            rules.rrule(dateutil.rrule.rrulestr(rrule, dtstart=start_datetime))

            for exdate in exdate_list:
                rules.exdate(exdate)

            return rules.between(start_date, end_date, True)

        datetime_start = self.vevent.getChildValue("dtstart")
        datetime_end = self.vevent.getChildValue("dtend")

        if isinstance(datetime_start, datetime.datetime):
            datetime_start = datetime_start.astimezone()
            all_day_event = False
        else:
            all_day_event = True

        if isinstance(datetime_end, datetime.datetime):
            datetime_end = datetime_end.astimezone()

        return pandas.date_range(start=datetime_start, end=datetime_end, closed="left" if all_day_event else None).tolist()

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
    def update_list(self, events):
        self.clear()

        for date_string, date_events in events.items():
            header_item = QtWidgets.QListWidgetItem(date_string)
            header_item.setFlags(QtCore.Qt.NoItemFlags)

            font = header_item.font()
            font.setPointSize(font.pointSize() + 5)
            header_item.setFont(font)
            self.addItem(header_item)

            for date, event in date_events:
                list_item = QtWidgets.QListWidgetItem(event.calendar.get_icon(), event.get_summary_with_time())
                list_item.setData(QtCore.Qt.UserRole, (date, event))
                self.addItem(list_item)

    def scroll_to_date(self, date: QtCore.QDate):
        items = self.findItems(date.toString("yyyy-MM-dd"), QtCore.Qt.MatchExactly)
        if items:
            self.scrollToItem(items[0], QtWidgets.QListWidget.PositionAtTop)


class CalendarContainerWidget(QtWidgets.QStackedWidget):
    def __init__(self, calendar_manager: "CalendarManager", default_calendar, updater_thread: "Updater", upcoming_days: int, past_days: int, highlight_color: str):
        super().__init__()

        self.default_calendar = default_calendar
        self.updater_thread = updater_thread
        self.upcoming_days = upcoming_days
        self.past_days = past_days
        self.highlight_color = highlight_color
        self.calendars = {str(calendar.url): calendar for calendar in calendar_manager.calendars}
        self.events = {}

        self.calendar_page_widget = QtWidgets.QWidget()
        self.addWidget(self.calendar_page_widget)

        layout = QtWidgets.QVBoxLayout()
        self.calendar_page_widget.setLayout(layout)

        self.calendar_widget = QtWidgets.QCalendarWidget()
        self.calendar_widget.setFirstDayOfWeek(QtCore.Qt.Monday)
        self.calendar_widget.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)
        self.calendar_widget.selectionChanged.connect(self.scroll_to_selected_date)
        layout.addWidget(self.calendar_widget, 0)

        self.add_event_action = QtWidgets.QAction("Create event", self)
        self.add_event_action.triggered.connect(lambda: self.show_add_event_dialog(None))
        self.calendar_widget.addAction(self.add_event_action)

        self.event_list_widget = CalendarEventList()
        self.event_list_widget.currentItemChanged.connect(self.event_list_item_changed)
        layout.addWidget(self.event_list_widget, 1)

    def show_add_event_dialog(self, position: QtCore.QPoint = None):
        dialog = CalendarEventDialog(self, self.calendars, self.calendar_widget.selectedDate(), self.default_calendar, self.updater_thread)

        if position is not None:
            dialog.move(position)

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

        self.event_list_widget.update_list(self.events)
        self.scroll_to_selected_date()

    def scroll_to_selected_date(self):
        self.event_list_widget.scroll_to_date(self.calendar_widget.selectedDate())

    def event_list_item_changed(self, item: QtWidgets.QListWidgetItem):
        if item is None:
            return

        item_data = item.data(QtCore.Qt.UserRole)

        if item_data is None:
            return

        date, event = item_data

        block_signals = self.calendar_widget.blockSignals(True)
        self.calendar_widget.setSelectedDate(QtCore.QDate(date))
        self.calendar_widget.blockSignals(block_signals)


class Updater(QtCore.QThread):
    ready = QtCore.pyqtSignal(dict, dict)

    def __init__(self, calendars: List[caldav.Calendar], sort_todos: List[str], todos_reversed: bool, upcoming_days: int, past_days: int):
        QtCore.QThread.__init__(self)

        self.calendars = calendars
        self.sort_todos = sort_todos
        self.todos_reversed = todos_reversed
        self.upcoming_days = upcoming_days
        self.past_days = past_days

    def run(self):
        try:
            events = {}
            todos = {}

            today = datetime.date.today()
            start_date = today - datetime.timedelta(days=self.past_days)
            end_date = today + datetime.timedelta(days=self.upcoming_days)

            for calendar in self.calendars:
                # TODO: Specifying end date in date_search does not return recurring events (at least with Nextcloud)
                events[str(calendar.url)] = calendar.date_search(start=start_date)

                calendar_todos = calendar.todos(sort_keys=self.sort_todos)

                if self.todos_reversed:
                    calendar_todos.reverse()

                todos[str(calendar.url)] = calendar_todos

            self.ready.emit(events, todos)
        except:
            traceback.print_exc()


class DBusHandler(dbus.service.Object):
    def __init__(self, view_instance: "View", session_bus: dbus.Bus):
        dbus.service.Object.__init__(self, session_bus, "/")

        self.view_instance = view_instance

    @dbus.service.method("com.selfcoders.Dashboard", in_signature="", out_signature="")
    def show_create_event_dialog(self):
        self.view_instance.calendar_widget.show_add_event_dialog(QtGui.QCursor.pos())

    @dbus.service.method("com.selfcoders.Dashboard", in_signature="", out_signature="")
    def show_create_todo_dialog(self):
        self.view_instance.show_todo_dialog(QtGui.QCursor.pos())


class CalendarManager:
    def __init__(self, url, username, password):
        client = caldav.DAVClient(url, username=username, password=password)

        self.unfiltered_calendars = sorted(client.principal().calendars(), key=lambda calendar_item: calendar_item.name)

        for calendar in self.unfiltered_calendars:
            calendar.__class__ = Calendar

        self.calendars = self.filter_calendars_with_component(self.unfiltered_calendars, "VEVENT")
        self.todo_lists = self.filter_calendars_with_component(self.unfiltered_calendars, "VTODO")

    @staticmethod
    def filter_calendars_with_component(calendars: List[Calendar], component: str):
        return [calendar for calendar in calendars if calendar.supports_component(component)]


class View(QtWidgets.QSplitter, AbstractView):
    def __init__(self, url, username, password, default_calendar=None, todo_lists=None, default_todo_list=None, sort_todos=("due", "priority"), todos_reversed=False, upcoming_days=365, past_days=0, highlight_color="#FFD800"):
        super().__init__()

        DBusHandler(self, get_dashboard_instance().session_dbus)

        self.calendar_manager = CalendarManager(url, username, password)

        self.setOrientation(QtCore.Qt.Vertical)

        self.default_todo_list = default_todo_list
        self.todo_lists = {}
        self.events = {}
        self.last_overdue_todo = (None, None)

        self.important_icon = QtGui.QIcon.fromTheme("error-app-symbolic")

        self.updater = Updater(self.calendar_manager.unfiltered_calendars, sort_todos, todos_reversed, upcoming_days, past_days)
        self.updater.ready.connect(self.update_calendars)

        self.calendar_widget = CalendarContainerWidget(self.calendar_manager, default_calendar, self.updater, upcoming_days, past_days, highlight_color)
        self.addWidget(self.calendar_widget)

        todo_parent_widget = QtWidgets.QWidget()

        todo_layout = QtWidgets.QVBoxLayout()
        todo_parent_widget.setLayout(todo_layout)

        self.todo_tab_widget = QtWidgets.QTabWidget()
        todo_layout.addWidget(self.todo_tab_widget, 1)

        self.overdue_todo_button = QtWidgets.QPushButton("Found overdue todo!")
        self.overdue_todo_button.clicked.connect(self.show_overdue_todo)
        self.overdue_todo_button.setVisible(False)
        todo_layout.addWidget(self.overdue_todo_button, 0)

        add_todo_layout = QtWidgets.QHBoxLayout()
        todo_layout.addLayout(add_todo_layout, 0)

        self.add_todo_field = QtWidgets.QLineEdit()
        self.add_todo_field.setPlaceholderText("Add new todo")
        self.add_todo_field.textChanged.connect(self.update_add_todo_button)
        self.add_todo_field.returnPressed.connect(self.add_todo)
        add_todo_layout.addWidget(self.add_todo_field, 1)

        self.add_todo_button = QtWidgets.QPushButton()
        self.add_todo_button.setIcon(QtGui.QIcon.fromTheme("add"))
        self.add_todo_button.clicked.connect(self.add_todo)
        add_todo_layout.addWidget(self.add_todo_button, 0)

        self.update_add_todo_button()

        self.addWidget(todo_parent_widget)

        self.setSizes([1, self.height()])

        default_page = None

        if todo_lists is None:
            todo_lists = [calendar.name for calendar in self.calendar_manager.todo_lists]

        todo_tabs = []

        calendar: Calendar
        for calendar in self.calendar_manager.todo_lists:
            if calendar.name not in todo_lists:
                continue

            todo_list_widget = TodoListWidget(self, calendar, self.calendar_manager)

            self.todo_lists[str(calendar.url)] = todo_list_widget
            todo_tabs.append((todo_list_widget, calendar.name))

            if default_todo_list is not None and calendar.name == default_todo_list:
                default_page = todo_list_widget

        todo_tabs = sorted(todo_tabs, key=lambda item: todo_lists.index(item[1]))

        for todo_list_widget, calendar_name in todo_tabs:
            self.todo_tab_widget.addTab(todo_list_widget, calendar_name)

        if default_page is not None:
            self.todo_tab_widget.setCurrentWidget(default_page)

        timer = Timer(self, 300000, self)
        timer.timeout.connect(self.updater.start)

    def update_calendars(self, events_per_calendar: Dict[str, List[caldav.Event]], todos_per_calendar: Dict[str, List[caldav.Todo]]):
        self.calendar_widget.update_events(events_per_calendar)

        self.last_overdue_todo = (None, None)

        for calendar in self.calendar_manager.todo_lists:
            calendar_id = str(calendar.url)

            if calendar_id not in self.todo_lists or calendar_id not in todos_per_calendar:
                continue

            self.update_todo_list(self.todo_lists[calendar_id], todos_per_calendar[calendar_id], calendar)

        self.overdue_todo_button.setVisible(self.last_overdue_todo[0] is not None)

    def update_todo_list(self, todo_list_widget: TodoListWidget, todos: List[caldav.Todo], calendar: Calendar):
        todo_list_widget.update_items(todos)

        if todo_list_widget.overdue_todo_item is None:
            found_overdue_todo = False
        else:
            found_overdue_todo = True
            self.last_overdue_todo = (todo_list_widget, todo_list_widget.overdue_todo_item)

        tab_index = self.todo_tab_widget.indexOf(todo_list_widget)

        self.todo_tab_widget.setTabText(tab_index, "{} ({})".format(calendar.name, len(todos)))
        self.todo_tab_widget.setTabIcon(tab_index, self.important_icon if found_overdue_todo else calendar.get_icon())

    def show_overdue_todo(self):
        tab_page_widget: QtWidgets.QListWidget
        todo_item: caldav.Todo

        tab_page_widget, todo_item = self.last_overdue_todo

        if tab_page_widget is None or todo_item is None:
            return

        self.todo_tab_widget.setCurrentWidget(tab_page_widget)

    def show_todo_dialog(self, position: QtCore.QPoint = None, todo_list: str = None, title: str = None, notes: str = None):
        if todo_list is None:
            todo_list = self.default_todo_list

        dialog = TodoDialog(self, self.calendar_manager.todo_lists, todo_list, updater_thread=self.updater)

        if position is not None:
            dialog.move(position)

        if title is not None:
            dialog.title_widget.setText(title)

        if notes is not None:
            dialog.notes_widget.setText(notes)

    def add_todo(self):
        text = self.add_todo_field.text().strip()
        if not text:
            return

        calendar: caldav.Calendar = self.todo_tab_widget.currentWidget().calendar

        TodoItem.create(calendar, text)
        self.updater.start()
        self.add_todo_field.clear()

    def update_add_todo_button(self):
        self.add_todo_button.setEnabled(self.add_todo_field.text().strip() != "")
