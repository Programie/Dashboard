# Calendar

Show events and tasks from calendars retrieved via CalDAV.

## Configuration options

* `url` (string): URL to your CalDAV server
* `username` (string): Username for your CalDAV server
* `password` (string): Password for your CalDAV server
* `default_calendar` (string): The default calendar which should be used for creating new events (default: none)
* `default_todo_list` (string): The default calendar which should be used for creating new tasks (default: none)
* `sort_todos` (list): Sort todos using those properties (default: `[due, priority]`)
* `todos_reversed` (boolean): Whether to sort todos in reverse order, e.g. the newest first (default: `false`)