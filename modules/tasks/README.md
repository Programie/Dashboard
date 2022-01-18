# Tasks

Show tasks from task lists retrieved via CalDAV.

## Configuration options

* `url` (string): URL to your CalDAV server (required)
* `username` (string): Username for your CalDAV server (required)
* `password` (string): Password for your CalDAV server (required)
* `todo_lists` (list): Task lists to show (and the sorting of the tabs) instead of all lists sorted alphabetically (default: `none`)
* `default_todo_list` (string): The default task list which should be used for creating new tasks (default: `none`)
* `sort_todos` (list): Sort tasks using those properties (default: `[due, priority]`)
* `todos_reversed` (boolean): Whether to sort tasks in reverse order, e.g. the newest first (default: `false`)