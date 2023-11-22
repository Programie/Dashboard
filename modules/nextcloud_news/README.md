# Nextcloud news

Show news from the [Nextcloud New app](https://apps.nextcloud.com/apps/news).

## Configuration options

* `nextcloud_url` (string): The base URL to your nextcloud instance
* `username` (string): The username for your Nextcloud instance
* `password` (string): The password for your Nextcloud instance
* `columns` (list): A list of columns to show (default: all, which is equal to `[feed, title, date]`)
* `item_options` (list): A list of item options (see bellow)
* `update_interval` (int): Update interval in seconds (default: `600`)
* `update_in_background` (boolean): Whether to update news in background
* `tab_id_status` (string): ID of the tab which should be updated once new items are available (requires `update_in_background` to be enabled)
* `context_menu_items` (list): A list of context menu items to add to the default ones (see bellow)

### Item options

Item options can be used to add options to specific folders, feeds or entries.

This can be used to exclude specific items or collapse them by default.

Each item option should be a map/dict containing the following items:

* `type` (string): The type of the item to match (`folder`, `feed` or `entry`)
* `value` (string): The value of the item to match (i.e. the title of the folder, feed or entry)
* `regex` (string): A regular expression to match the item
* `action` (string): The action to do (`exclude` or `collapse`)

You may use `value` or `regex` to match the item. If both are specified, `value` is used and `regex` is silently ignored.

Note: Action `colapse` does not work for `entry` items.

### Context menu items

The `context_menu_items` option allows to add additional items to the context menu.

The Option should be a list where each item should be a map/dict containing the following items:

* `title` (string): The title of the menu item (required)
* `icon` (string): The icon name from the current theme to use for the menu item
* `shortcut` (string): Define the keyboard shortcut for the item (see documentation of `QtGui.QKeySequence.fromString()` for more details)
* `command` (string): Command to execute for each selected item (You can use placeholders like `{url}`)
* `mark_as_read` (boolean): Whether to mark the selected items as read if the command was executed successfully (default: `false`)

You may also add an item specifying only `type: "separator"` to add a separator.