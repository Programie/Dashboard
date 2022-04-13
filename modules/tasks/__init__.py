import datetime
import traceback
import uuid
from functools import cmp_to_key
from typing import List, Dict

import caldav
import dbus
import pytz
from PyQt5 import QtCore, QtWidgets, QtGui
from dateutil.tz import tzlocal
from pytz import timezone

from lib.common import Timer, AbstractView, get_dashboard_instance
from modules.calendar import escape_ical_string, Calendar


class TodoListConfig:
    def __init__(self, name: str, config: dict, sort: dict, default_priority_order_number: int):
        self.name = name
        self.sort = config.get("sort", sort)
        self.default_priority_order_number = config.get("default_priority_order_number", default_priority_order_number)


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

        if hasattr(self.vtodo, "priority"):
            self.priority = int(self.vtodo.priority.value)
        else:
            self.priority = 0

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

    def is_high_priority(self):
        return 1 <= self.priority <= 4

    def is_medium_priority(self):
        return self.priority == 5

    def is_low_priority(self):
        return 6 <= self.priority <= 9

    def get_summary(self):
        if hasattr(self.vtodo, "summary"):
            return self.vtodo.summary.value
        else:
            return None

    def complete(self):
        self.todo.complete()

    def remove(self):
        self.todo.delete()

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

        self.use_due_date_checkbox = QtWidgets.QCheckBox("Due Date")
        self.use_due_date_checkbox.stateChanged.connect(self.update_due_date_widget)
        layout.addWidget(self.use_due_date_checkbox, 3, 0)

        current_date_time = QtCore.QDateTime.currentDateTime()
        current_time = current_date_time.time()
        current_time.setHMS(current_time.hour() + 1, 0, 0, 0)
        current_date_time.setTime(current_time)

        self.due_date_widget = QtWidgets.QDateTimeEdit(current_date_time)
        layout.addWidget(self.due_date_widget, 3, 1)

        if todo_item is not None and todo_item.due_datetime is not None:
            due_date = todo_item.due_datetime.astimezone(tzlocal())

            self.use_due_date_checkbox.setChecked(True)
            self.due_date_widget.setDateTime(QtCore.QDateTime(due_date.year, due_date.month, due_date.day, due_date.hour, due_date.minute, due_date.second))

        self.update_due_date_widget()

        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        layout.addWidget(button_box, 4, 0, 1, -1)

        button_box.accepted.connect(self.save)
        button_box.rejected.connect(self.close)

        self.show()
        self.setFixedSize(self.size())

    def update_due_date_widget(self):
        self.due_date_widget.setEnabled(self.use_due_date_checkbox.isChecked())

    def save(self):
        calendar: caldav.Calendar = self.calendar_dropdown.currentData(QtCore.Qt.UserRole)
        title = self.title_widget.text().strip()
        notes = self.notes_widget.toPlainText().strip()

        if self.use_due_date_checkbox.isChecked():
            due_datetime = self.due_date_widget.dateTime().toUTC()

            due_date = due_datetime.date()
            due_time = due_datetime.time()

            due_date = datetime.datetime(due_date.year(), due_date.month(), due_date.day(), due_time.hour(), due_time.minute(), due_time.second(), tzinfo=pytz.UTC).astimezone(tzlocal())
        else:
            due_date = None

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

            if due_date:
                if hasattr(self.todo_item.vtodo, "due"):
                    self.todo_item.vtodo.due.value = due_date
                else:
                    self.todo_item.vtodo.add("due").value = due_date

                if hasattr(self.todo_item.vtodo, "dtstart"):
                    self.todo_item.vtodo.dtstart.value = due_date
                else:
                    self.todo_item.vtodo.add("dtstart").value = due_date
            else:
                if hasattr(self.todo_item.vtodo, "due"):
                    del self.todo_item.vtodo.due

                if hasattr(self.todo_item.vtodo, "dtstart"):
                    del self.todo_item.vtodo.dtstart

            self.todo_item.todo.save()

        if self.updater_thread:
            self.updater_thread.start()

        self.accept()


class TodoListWidget(QtWidgets.QTreeWidget):
    def __init__(self, view_widget: "View", calendar: "Calendar", calendar_manager: "CalendarManager", updater_thread: "Updater"):
        super().__init__()

        self.view_widget = view_widget
        self.calendar = calendar
        self.calendar_manager = calendar_manager
        self.updater_thread = updater_thread
        self.overdue_todo_item = None

        self.setHeaderHidden(True)
        self.itemChanged.connect(self.update_todo)
        self.itemDoubleClicked.connect(self.show_todo)

        self.context_menu = QtWidgets.QMenu()
        self.context_menu.addAction("Edit", self.menu_edit_todo)
        self.context_menu.addSeparator()
        self.context_menu.addAction("Delete", self.menu_remove_todo)

        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

    def show_context_menu(self, position):
        if not self.itemAt(position):
            return

        self.context_menu.exec(self.mapToGlobal(position))

    def menu_edit_todo(self):
        selected_items = self.selectedItems()

        if len(selected_items) == 0:
            return

        self.show_todo(selected_items[0])

    def menu_remove_todo(self):
        selected_items = self.selectedItems()

        if len(selected_items) == 0:
            return

        todo_item: TodoItem = selected_items[0].data(0, QtCore.Qt.UserRole)

        if QtWidgets.QMessageBox.question(self, "Remove todo", "Are you sure to remove the selected todo '{}'?".format(todo_item.get_summary())) == QtWidgets.QMessageBox.Yes:
            todo_item.remove()
            self.updater_thread.start()

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

            font = list_item.font(0)

            if todo_item.due_datetime is not None:
                if todo_item.is_overdue():
                    self.overdue_todo_item = todo_item
                    list_item.setForeground(0, QtGui.QBrush(QtGui.QColor("red")))
                else:
                    list_item.setForeground(0, QtGui.QBrush(QtGui.QColor("#FFD800")))

            if todo_item.is_high_priority():
                font.setBold(True)

            list_item.setFont(0, font)

            self.add_from_list(list_item, [child_item for child_item in todo_item.children.values()])

    def show_todo(self, list_item: QtWidgets.QTreeWidgetItem):
        if list_item is None:
            return

        todo_item: TodoItem = list_item.data(0, QtCore.Qt.UserRole)

        TodoDialog(self, self.calendar_manager.todo_lists, self.calendar.name, todo_item, self.view_widget.updater)

    def update_todo(self, list_item: QtWidgets.QTreeWidgetItem):
        todo_item: TodoItem = list_item.data(0, QtCore.Qt.UserRole)

        if list_item.checkState(0) == QtCore.Qt.Checked:
            todo_item.complete()
            self.updater_thread.start()


class DBusHandler(dbus.service.Object):
    def __init__(self, view_instance: "View", session_bus: dbus.Bus):
        dbus.service.Object.__init__(self, session_bus, "/tasks")

        self.view_instance = view_instance

    @dbus.service.method("com.selfcoders.Dashboard", in_signature="", out_signature="")
    def show_create_dialog(self):
        self.view_instance.show_todo_dialog(QtGui.QCursor.pos())


class CalendarManager:
    def __init__(self, url, username, password, calendars):
        client = caldav.DAVClient(url, username=username, password=password)

        unfiltered_calendars = sorted(client.principal().calendars(), key=lambda calendar_item: calendar_item.name)

        if calendars:
            if isinstance(calendars, dict):
                calendars = calendars.keys()

            unfiltered_calendars = [calendar for calendar in unfiltered_calendars if calendar.name in calendars]

        for calendar in unfiltered_calendars:
            calendar.__class__ = Calendar

        self.todo_lists = self.filter_calendars_with_component(unfiltered_calendars, "VTODO")

    @staticmethod
    def filter_calendars_with_component(calendars: List[Calendar], component: str):
        return [calendar for calendar in calendars if calendar.supports_component(component)]


class Updater(QtCore.QThread):
    ready = QtCore.pyqtSignal(dict)

    def __init__(self, calendars: List[caldav.Calendar], todo_configs: Dict[str, TodoListConfig]):
        QtCore.QThread.__init__(self)

        self.calendars = calendars
        self.todo_configs = todo_configs

    def get_sort_value(self, todo_entry, sort_key):
        vtodo = todo_entry.instance.vtodo

        defaults = {
            "due": "2050-01-01",
            "dtstart": "1970-01-01",
            "priority": "0",
            "isnt_overdue": not (hasattr(vtodo, "due") and vtodo.due.value.strftime("%F%H%M%S") < datetime.datetime.now().strftime("%F%H%M%S")),
            "hasnt_started": (hasattr(vtodo, "dtstart") and vtodo.dtstart.value.strftime("%F%H%M%S") > datetime.datetime.now().strftime("%F%H%M%S"))
        }

        value = getattr(vtodo, sort_key, None)
        if value is None:
            return defaults.get(sort_key, "0")

        value = value.value
        if hasattr(value, "strftime"):
            return value.strftime("%F%H%M%S")

        return value

    def compare_todos(self, todo1, todo2, sort_key, asc=True, default_priority_order_number=0):
        value1 = self.get_sort_value(todo1, sort_key).lower()
        value2 = self.get_sort_value(todo2, sort_key).lower()

        # Map priority value to default priority number in case it's zero (undefined)
        if sort_key == "priority" and value1 == "0":
            value1 = str(default_priority_order_number)
        if sort_key == "priority" and value2 == "0":
            value2 = str(default_priority_order_number)

        if value1 > value2:
            return 1 if asc else -1
        elif value1 < value2:
            return -1 if asc else 1
        else:
            return 0

    def sort_function(self, todo1, todo2, todo_config: TodoListConfig):
        for sort_key, sort_direction in todo_config.sort.items():
            compare_value = self.compare_todos(todo1, todo2, sort_key, sort_direction.lower() == "asc", todo_config.default_priority_order_number)

            if compare_value != 0:
                return compare_value

        return 0

    def run(self):
        try:
            todos = {}

            for calendar in self.calendars:
                todo_config = self.todo_configs[calendar.name]
                calendar_todos = calendar.todos(sort_keys=[])

                calendar_todos.sort(key=cmp_to_key(lambda todo1, todo2: self.sort_function(todo1, todo2, todo_config)))

                todos[str(calendar.url)] = calendar_todos

            self.ready.emit(todos)
        except:
            traceback.print_exc()


class View(QtWidgets.QWidget, AbstractView):
    def __init__(self, url, username, password, todo_lists=None, default_todo_list=None, sort_todos=None, todos_reversed=False, default_priority_order_number=0):
        super().__init__()

        if isinstance(sort_todos, list):
            sort_todos = {
                key: ("desc" if todos_reversed else "asc")
                for key in sort_todos
            }
        elif not isinstance(sort_todos, dict):
            sort_todos = {
                "due": "asc",
                "priority": "asc"
            }

        DBusHandler(self, get_dashboard_instance().session_dbus)

        self.default_todo_list = default_todo_list
        self.todo_lists = {}
        self.last_overdue_todo = (None, None)

        self.important_icon = QtGui.QIcon.fromTheme("error-app-symbolic")

        self.calendar_manager = CalendarManager(url, username, password, todo_lists)

        if todo_lists is None:
            todo_lists = [calendar.name for calendar in self.calendar_manager.todo_lists]

        todo_configs = {}
        todo_lists_list: list[str] = todo_lists

        if isinstance(todo_lists, dict):
            for name, config in todo_lists.items():
                todo_configs[name] = TodoListConfig(name, config, sort_todos, default_priority_order_number)

            todo_lists_list = list(todo_lists.keys())
        elif isinstance(todo_lists, list):
            for name in todo_lists:
                todo_configs[name] = TodoListConfig(name, {}, sort_todos, default_priority_order_number)

        self.updater = Updater(self.calendar_manager.todo_lists, todo_configs)
        self.updater.ready.connect(self.update_calendars)

        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)

        self.tab_widget = QtWidgets.QTabWidget()
        layout.addWidget(self.tab_widget, 1)

        self.overdue_todo_button = QtWidgets.QPushButton("Found overdue todo!")
        self.overdue_todo_button.clicked.connect(self.show_overdue_todo)
        self.overdue_todo_button.setVisible(False)
        layout.addWidget(self.overdue_todo_button, 0)

        add_todo_layout = QtWidgets.QHBoxLayout()
        layout.addLayout(add_todo_layout, 0)

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

        default_page = None

        todo_tabs = []

        calendar: Calendar
        for calendar in self.calendar_manager.todo_lists:
            if calendar.name not in todo_lists_list:
                continue

            todo_list_widget = TodoListWidget(self, calendar, self.calendar_manager, self.updater)

            self.todo_lists[str(calendar.url)] = todo_list_widget
            todo_tabs.append((todo_list_widget, calendar.name))

            if default_todo_list is not None and calendar.name == default_todo_list:
                default_page = todo_list_widget

        todo_tabs = sorted(todo_tabs, key=lambda item: todo_lists_list.index(item[1]))

        for todo_list_widget, calendar_name in todo_tabs:
            self.tab_widget.addTab(todo_list_widget, calendar_name)

        if default_page is not None:
            self.tab_widget.setCurrentWidget(default_page)

        timer = Timer(self, 300000, self)
        timer.timeout.connect(self.updater.start)

    def update_calendars(self, todos_per_calendar: Dict[str, List[caldav.Todo]]):
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

        tab_index = self.tab_widget.indexOf(todo_list_widget)

        self.tab_widget.setTabText(tab_index, "{} ({})".format(calendar.name, len(todos)))
        self.tab_widget.setTabIcon(tab_index, self.important_icon if found_overdue_todo else calendar.get_icon())

    def show_overdue_todo(self):
        tab_page_widget: QtWidgets.QListWidget
        todo_item: caldav.Todo

        tab_page_widget, todo_item = self.last_overdue_todo

        if tab_page_widget is None or todo_item is None:
            return

        self.tab_widget.setCurrentWidget(tab_page_widget)

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

        calendar: caldav.Calendar = self.tab_widget.currentWidget().calendar

        TodoItem.create(calendar, text)
        self.updater.start()
        self.add_todo_field.clear()

    def update_add_todo_button(self):
        self.add_todo_button.setEnabled(self.add_todo_field.text().strip() != "")
