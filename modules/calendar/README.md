# Calendar

Show events and tasks from calendars retrieved via CalDAV.

## Configuration options

* `url` (string): URL to your CalDAV server (required)
* `username` (string): Username for your CalDAV server (required)
* `password` (string): Password for your CalDAV server (required)
* `default_calendar` (string): The default calendar which should be used for creating new events (default: `none`)
* `todo_lists` (list): Todo lists to show instead of all lists (default: `none`)
* `default_todo_list` (string): The default calendar which should be used for creating new tasks (default: `none`)
* `sort_todos` (list): Sort todos using those properties (default: `[due, priority]`)
* `todos_reversed` (boolean): Whether to sort todos in reverse order, e.g. the newest first (default: `false`)
* `upcoming_days` (integer): How many upcoming days to show in calendar (default: `365`)
* `past_days` (integer): How many past days to show in calendar (default: `0`)
* `highlight_color` (string): Which color to use for highlighting events in calendar (default: `#FFD800`)