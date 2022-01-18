# Calendar

Show events from calendars retrieved via CalDAV.

## Configuration options

* `url` (string): URL to your CalDAV server (required)
* `username` (string): Username for your CalDAV server (required)
* `password` (string): Password for your CalDAV server (required)
* `default_calendar` (string): The default calendar which should be used for creating new events (default: `none`)
* `upcoming_days` (integer): How many upcoming days to show in calendar (default: `365`)
* `past_days` (integer): How many past days to show in calendar (default: `0`)
* `highlight_color` (string): Which color to use for highlighting events in calendar (default: `#FFD800`)