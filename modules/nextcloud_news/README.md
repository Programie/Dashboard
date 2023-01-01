# Nextcloud news

Show news from the [Nextcloud New app](https://apps.nextcloud.com/apps/news).

## Configuration options

* `nextcloud_url` (string): The base URL to your nextcloud instance
* `username` (string): The username for your Nextcloud instance
* `password` (string): The password for your Nextcloud instance
* `columns` (list): A list of columns to show (default: all, which is equal to `[feed, title, date]`)
* `item_options` (list): A list of item options (see bellow)
* `update_interval` (int): Update interval in seconds (default: `600`)

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