import argparse
from queue import Queue, Empty as QueueEmptyError
from time import sleep, time
import paho.mqtt.client as mqtt
import struct
from typing import Optional
from . import protocol
import json


class Mqtt:
    def __init__(self, args, network_events_queue: Queue, mqtt_events_queue: Queue):
        self.args = args
        self.network_events_queue = network_events_queue
        self.mqtt_events_queue = mqtt_events_queue
        self.client = None

    def prepare_argparse(parser: argparse._ActionsContainer):
        parser.add_argument('--mqtt-host')
        parser.add_argument('--mqtt-port', type=int, default=1883)
        parser.add_argument('--mqtt-clientid', default='timeguard')
        parser.add_argument('--mqtt-root-topic', default='timeguard')
        parser.add_argument('--mqtt-username')
        parser.add_argument('--mqtt-password')
        parser.add_argument('--mqtt-homeassistant-discovery', const='homeassistant',
                            action='store', default=None, nargs='?')
        parser.add_argument('--mqtt-homeassistant-status-topic', default='homeassistant/status')
        parser.add_argument('--mqtt-device-online-timeout', default=120, type=int)

    def run(self):
        self._stop = False
        self._known_devices = {}

        if not self.args.mqtt_host:
            return

        self.client = mqtt.Client(self.args.mqtt_clientid)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

        if self.args.mqtt_username:
            self.client.username_pw_set(self.args.mqtt_username, self.args.mqtt_password)

        self.client.will_set(self.topic('lwt'), payload='offline', retain=True)

        self.client.connect(self.args.mqtt_host, self.args.mqtt_port)
        while not self._stop:
            try:
                tg_data: protocol.Timeguard = self.network_events_queue.get_nowait()
                self.handle_protocol_data(tg_data)
            except QueueEmptyError:
                pass
            self.client.loop()

            for device_id, last_command in self._known_devices.items():
                if time() - last_command > self.args.mqtt_device_online_timeout:
                    self.client.publish(self.device_topic(device_id, 'status'), payload='offline', retain=True)

        self.client.publish(self.topic('lwt'), payload='offline', retain=True)

        for device_id in self._known_devices.keys():
            self.client.publish(self.device_topic(device_id, 'status'), payload='offline', retain=True)

        self.client.disconnect()

    def handle_protocol_data(self, data: protocol.Timeguard):
        device_id = data.payload.device_id
        if data.payload.message_flags & protocol.MessageFlags.IS_FROM_SERVER == 0:
            self.client.publish(self.device_topic(device_id, 'status'), payload='online')
            if device_id not in self._known_devices:
                if self.args.mqtt_homeassistant_discovery:
                    self.setup_hass(device_id)

            self._known_devices[device_id] = time()

        if data.payload.message_type == protocol.MessageType.PING:
            if data.payload.message_flags & protocol.MessageFlags.IS_FROM_SERVER != protocol.MessageFlags.IS_FROM_SERVER:
                self.client.publish(
                    self.device_topic(device_id, 'uptime'),
                    data.payload.params.uptime
                )
                self.client.publish(
                    self.device_topic(device_id, 'switch_state'),
                    'ON' if data.payload.params.state.switch_state == protocol.SwitchState.ON else 'OFF'
                )
                self.client.publish(
                    self.device_topic(device_id, 'load_detected'),
                    'ON' if data.payload.params.state.load_detected else 'OFF'
                )
                self.client.publish(
                    self.device_topic(device_id, 'advance_mode_state'),
                    'ON' if data.payload.params.state.advance_mode_state == protocol.AdvanceState.ON else 'OFF'
                )
                self.client.publish(
                    self.device_topic(device_id, 'load_was_detected_previously'),
                    'ON' if data.payload.params.state.load_was_detected_previously else 'OFF'
                )

    def topic(self, topic: str) -> str:
        return '{}/{}'.format(self.args.mqtt_root_topic, topic)

    def setup_hass(self, device_id: int):
        self.configure_hass_sensor(device_id, 'sensor', 'uptime', 'Uptime', unit_of_measurement='s')
        self.configure_hass_sensor(device_id, 'binary_sensor', 'switch_state', 'Switch state')
        self.configure_hass_sensor(device_id, 'binary_sensor', 'load_detected', 'Load detected')
        self.configure_hass_sensor(device_id, 'binary_sensor', 'load_was_detected_previously', 'Load was detected prevously')
        self.configure_hass_sensor(device_id, 'binary_sensor', 'advance_mode_state', 'Advance mode')

    def configure_hass_sensor(self, device_id: int, sensor_type: str, sensor_id: str, name: str, **kwargs):
        device = {
            'identifiers': ['tg:{}'.format(device_id)],
            'manufacturer': 'Timeguard',
            'name': 'Timeguard Timeswitch {}'.format(self.format_device(device_id))
        }
        self.client.publish(
            self.hass_topic('{}/{}/config'.format(sensor_type, self.discovery_unique_id(device_id, sensor_id))),
            payload=json.dumps(
                {
                    '~': self.device_topic(device_id, ''),
                    'unique_id': self.discovery_unique_id(device_id, sensor_id),
                    'availability': [
                        {
                            'topic': '~/status',
                            'payload_available': 'online',
                            'payload_not_available': 'offline',
                        },
                        {
                            'topic': self.topic('lwt'),
                            'payload_available': 'online',
                            'payload_not_available': 'offline',
                        },
                    ],
                    'availability_mode': 'latest',
                    'name': name,
                    'state_topic': '~/{}'.format(sensor_id),
                    'device': device,
                } | kwargs
            ),
            retain=True
        )

    def discovery_unique_id(self, device_id: int, sensor: str) -> str:
        return '{}_{}'.format(self.format_device(device_id), sensor)

    def hass_topic(self, topic: str) -> Optional[str]:
        if self.args.mqtt_homeassistant_discovery:
            return '{}/{}'.format(self.args.mqtt_homeassistant_discovery, topic)

        return None

    def format_device(self, device_id: int) -> str:
        return '{:08x}'.format(device_id)

    def device_topic(self, device_id: int, topic: str) -> str:
        if topic:
            return self.topic('{}/{}'.format(self.format_device(device_id), topic))

        return self.topic('{}'.format(self.format_device(device_id)))

    def on_connect(self, client: mqtt.Client, userdata, flags, rc):
        client.subscribe(self.topic('#'))
        if self.args.mqtt_homeassistant_discovery:
            client.subscribe(self.args.mqtt_homeassistant_status_topic)
        client.publish(self.topic('lwt'), payload='online')

    def on_message(self, client: mqtt.Client, userdata, msg):
        pass

    def stop(self):
        self._stop = True
