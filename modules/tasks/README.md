# Tasks

Show tasks from task lists retrieved via CalDAV.

## Configuration options

* `url` (string): URL to your CalDAV server (required)
* `username` (string): Username for your CalDAV server (required)
* `password` (string): Password for your CalDAV server (required)
* `todo_lists` (list or dict): Task lists to show (and the sorting of the tabs) instead of all lists sorted alphabetically (default: `none`)
* `default_todo_list` (string): The default task list which should be used for creating new tasks (default: `none`)
* `sort_todos` (dict or list): Sort tasks using those properties (default: `{due: "asc", priority: "asc"}`)
* `todos_reversed` (boolean): Whether to sort tasks in reverse order, e.g. the newest first, only used if `sort_todos` is a list (default: `false`)
* `default_priority_order_number` (integer): Priority number for tasks without priority when sorting tasks by priority (default: `0`)
* `show_add_todo` (boolean): Whether to show the field bellow the todo list to add a new todo entry (default: `true`)
* `show_before_start` (integer): How many days before a todo item with start date should be visible (default: `None` which means always show the item)
* `item_style` (dict): Specify how to style items (see bellow)

You may also specify `todo_lists` as a dict (map) to overwrite the sorting and default priority order umber for specific lists. In that case the dict should have the following structure:

```yaml
todo_lists:
  some_list:
    sort:
      due: "asc"
      priority: "asc"
  another_list:
    default_priority_order_number: 5
  list_using_defaults: {}
```

### Item style

The `item_style` option allows to specify different styles for different item states (e.g. overdue items).

The following styles are available:

* `default`: Default for all items
* `overdue`: Item has reached the due date
* `has_duedate`: Item has a due date but is not reached yet
* `not_started`: Item has a start date but has not started yet

Each style can specify the foreground color as well as the background color of the item.

Example:
```yaml
item_style:
  overdue:
    foreground_color: white
    background_color: red
  not_started:
    foreground_color: gray
```
