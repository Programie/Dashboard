import distutils.util
import json
import logging
import time

import paho.mqtt.client as mqtt
from PyQt5 import QtCore, QtDBus
from lib.common import AbstractPlugin, get_dashboard_instance


class ConnectWithRetry(QtCore.QThread):
    def __init__(self, parent, client: mqtt.Client, host, username):
        super().__init__(parent)

        self.client = client
        self.host = host
        self.username = username
        self.do_run = True

    def start(self, priority: QtCore.QThread.Priority = QtCore.QThread.Priority.InheritPriority):
        self.do_run = True

        super().start(priority)

    def stop(self):
        self.do_run = False

    def run(self):
        while self.do_run:
            try:
                logging.info("Connecting to MQTT server {} using username {}".format(self.host, self.username))

                self.client.connect(self.host)
                self.client.loop_start()

                break
            except:
                logging.exception("MQTT connection failed")
                time.sleep(1)


class Plugin(QtCore.QObject, AbstractPlugin):
    message_received = QtCore.pyqtSignal(str, str)

    def __init__(self, dashboard_instance, host, username=None, password=None, fake_screensaver_topic=None):
        super().__init__(dashboard_instance)

        self.topic_callbacks_map = {}

        logging.basicConfig(level=logging.INFO)

        self.client = mqtt.Client()
        self.client.reconnect_delay_set(1, 2)
        self.client.username_pw_set(username, password)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

        self.message_received.connect(self.dispatch_message)

        if fake_screensaver_topic is not None:
            self.subscribe(fake_screensaver_topic, lambda payload: dashboard_instance.screensaver_active_changed(distutils.util.strtobool(payload)))

        self.connect_thread = ConnectWithRetry(self, self.client, host, username)

        QtDBus.QDBusConnection.systemBus().connect("org.freedesktop.login1", "/org/freedesktop/login1", "org.freedesktop.login1.Manager", "PrepareForSleep", self.prepare_for_sleep_changed)

    @QtCore.pyqtSlot(bool)
    def prepare_for_sleep_changed(self, state):
        if not state:  # Resume from suspend
            logging.info("Resuming from suspend, reconnecting MQTT connection")
            self.disconnect_client()
            self.connect_client()

    def start_plugin(self):
        self.connect_client()

    def stop_plugin(self):
        self.disconnect_client()

    def connect_client(self):
        self.connect_thread.start()

    def disconnect_client(self):
        logging.info("Disconnecting from MQTT server")

        self.connect_thread.stop()
        self.connect_thread.wait()

        self.client.disconnect()
        self.client.loop_stop()

    def subscribe(self, topic: str, callback: callable):
        self.topic_callbacks_map[topic] = callback

        if self.client.is_connected():
            logging.info("Subscribing to topic {}".format(topic))
            self.client.subscribe(topic)

    def publish(self, topic: str, payload: str, retain=False):
        self.client.publish(topic, payload, retain=retain)

    def on_connect(self, client, userdata, flags, rc):
        for topic in self.topic_callbacks_map:
            logging.info("Subscribing to topic {}".format(topic))
            client.subscribe(topic)

    def on_message(self, client, userdata, message: mqtt.MQTTMessage):
        self.message_received.emit(message.topic, message.payload.decode("utf-8"))

    def dispatch_message(self, topic, payload):
        if topic not in self.topic_callbacks_map:
            return

        self.topic_callbacks_map[topic](payload)


def get_plugin_instance():
    return get_dashboard_instance().get_plugin_instance("mqtt_listener")


def mqtt_subscribe(topic, callback: callable):
    get_plugin_instance().subscribe(topic, callback)


def mqtt_publish(topic, payload, retain=False):
    get_plugin_instance().publish(topic, payload, retain)


def mqtt_publish_json(topic, payload, retain=False):
    mqtt_publish(topic, json.dumps(payload), retain)
