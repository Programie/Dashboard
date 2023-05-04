# Timer

Allows you to define a timer (hours, minutes and seconds) and plays a sound once it has elapsed.

## Configuration options

* `disable_screensaver_while_active` (boolean): Whether to disable screensaver while timer is active (default: `false`)
* `sync_to_mqtt_topic` (string): Set to a MQTT topic to sync the timer with other Dashboard instances (default: `null`)
* `send_mqtt_updates` (boolean): Whether to publish updates to MQTT broker while the timer is active (default: `true`)

## Sync via MQTT

The timer widget allows to synchronize multiple instances via MQTT.

Using that feature, you can start the timer on one Dashboard instance and see the remaining time on another instance which might be also running on a different machine.

**Note:** This requires the `mqtt_listener` plugin!