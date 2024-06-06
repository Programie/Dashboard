# Embedded App

Embed any application window as a Dashboard widget.

Note: [python-xlib](https://pypi.org/project/python-xlib/) is required!

## Configuration options

* `command_line` (string): The command to start the application
* `window_selector` (dict): Defines how to find the window to embed (see details bellow)
* `max_window_searches` (integer): How many tries to search for the window after starting the application

### Window selector

The window selector specifies how the window of the started application can be found.

The dict must contain one or more of the following properties:

* `app` the application name (`res_name` in the `XClassHint` structure)
* `class` the window class name (`res_class` in the `XClassHint` structure)
* `title` the exact window title
* `title_contains` any string which is part of the window title

The first window matching all the specified properties will be used and embedded into the widget.

## Examples

### Embedding Firefox

Embedding Firefox is really easy as it supports specifying the window class name which can be set to something unique. Otherwise, your already open Firefox window might be used. You might also create a separate Firefox profile.

Define a new widget with the following properties:

```yaml
type: embedded_app
command_line: "/path/to/firefox -P YourFirefoxProfileName --new-instance --class SomeUniqueClassName --kiosk https://example.com"
window_selector:
  class: SomeUniqueClassName
```