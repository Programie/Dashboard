# VLC

Play any stream or video supported by [VLC media player](https://www.videolan.org/vlc/).

## Configuration options

* `url` (string): The URL to play (i.e. video stream or local file)
* `width` (integer): The width in pixels of the widget
* `height` (integer): The height in pixels of the widget
* `open_url` (string): The URL to open in VLC once the widget is double clicked (default: same as `url`)
* `stop_on_inactive` (boolean): Whether to stop the playback when the widget is inactive (i.e. minimized or tab not visible) (default: true)
* `allow_screensaver` (boolean): Whether to allow the screensaver to be started while playback (default: true)