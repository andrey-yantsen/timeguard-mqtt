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
        self._device_state = {}

    def prepare_argparse(parser: argparse._ActionsContainer):
        parser.add_argument('--mqtt-host')
        parser.add_argument('--mqtt-port', type=int, default=1883)
        parser.add_argument('--mqtt-clientid', default='timeguard')
        parser.add_argument('--mqtt-root-topic', default='timeguard')
        parser.add_argument('--mqtt-username')
        parser.add_argument('--mqtt-password')
        parser.add_argument('--homeassistant-discovery', const='homeassistant',
                            action='store', default=None, nargs='?')
        parser.add_argument('--homeassistant-status-topic', default='homeassistant/status')
        parser.add_argument('--device-online-timeout', default=120, type=int)

    def run(self):
        self._stop = False
        self._device_state = {}

        if not self.args.mqtt_host:
            return

        self.client = mqtt.Client(self.args.mqtt_clientid)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

        if self.args.mqtt_username:
            self.client.username_pw_set(self.args.mqtt_username, self.args.mqtt_password)

        self.client.will_set(self.topic('lwt'), payload='offline', retain=True)

        self.client.connect_async(self.args.mqtt_host, self.args.mqtt_port)
        self.client.loop_start()
        while not self._stop:
            devices_to_delete = []
            for device_id, state in self._device_state.items():
                if time() - state['last_command'] > self.args.device_online_timeout:
                    self.report_offline(self.device_topic(device_id, 'lwt'))
                    devices_to_delete.append(device_id)

            for device_id in devices_to_delete:
                del self._device_state[device_id]

            try:
                tg_data: protocol.Timeguard = self.network_events_queue.get_nowait()
                self.handle_protocol_data(tg_data)
            except QueueEmptyError:
                sleep(0.1)

        self.report_offline(self.topic('lwt'))

        for device_id in self._device_state.keys():
            self.report_offline(self.device_topic(device_id, 'lwt'))

        self.client.disconnect()
        self.client.loop_stop()

    def report_offline(self, topic: str):
        self.client.publish(topic, payload='offline', retain=True)

    def handle_protocol_data(self, data: protocol.Timeguard):
        device_id = data.payload.device_id
        if data.payload.message_flags & protocol.MessageFlags.IS_FROM_SERVER == 0:
            if device_id not in self._device_state:
                self._device_state[device_id] = {
                    'parameters': {},
                }
                self.setup_device(device_id)
                if self.args.homeassistant_discovery:
                    self.setup_hass(device_id)

            self._device_state[device_id]['last_command'] = time()

        if data.payload.message_type == protocol.MessageType.PING:
            if data.payload.message_flags & protocol.MessageFlags.IS_FROM_SERVER != protocol.MessageFlags.IS_FROM_SERVER:
                self.update_device_state(device_id, 'uptime', data.payload.params.uptime)
                self.update_device_state(
                    device_id,
                    'switch_state',
                    'ON' if data.payload.params.state.switch_state == protocol.SwitchState.ON else 'OFF'
                )
                self.update_device_state(
                    device_id,
                    'load_detected',
                    'ON' if data.payload.params.state.load_detected else 'OFF'
                )
                self.update_device_state(
                    device_id,
                    'advance_mode_state',
                    'ON' if data.payload.params.state.advance_mode_state == protocol.AdvanceState.ON else 'OFF'
                )
                self.update_device_state(
                    device_id,
                    'load_was_detected_previously',
                    'ON' if data.payload.params.state.load_was_detected_previously else 'OFF'
                )
                self.report_state(device_id)

    def report_state(self, device_id: int):
        self.client.publish(self.device_topic(device_id, 'lwt'), payload='online')
        for key, value in self._device_state[device_id]['parameters'].items():
            self.client.publish(self.device_topic(device_id, key), payload=value)

    def update_device_state(self, device_id: int, parameter: str, value: str):
        self._device_state[device_id]['parameters'][parameter] = value

    def topic(self, topic: str) -> str:
        return '{}/{}'.format(self.args.mqtt_root_topic, topic)

    def setup_device(self, device_id: int):
        self.client.subscribe(self.device_topic(device_id, 'send_raw_command'))

    def setup_hass(self, device_id: int):
        self.configure_hass_sensor(device_id, 'sensor', 'uptime', 'Uptime', unit_of_measurement='s')
        self.configure_hass_sensor(device_id, 'binary_sensor', 'switch_state', 'Switch state')
        self.configure_hass_sensor(device_id, 'binary_sensor', 'load_detected', 'Load detected')
        self.configure_hass_sensor(device_id, 'binary_sensor', 'load_was_detected_previously',
                                   'Load was detected prevously')
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
                            # TODO: seems like topics with ~ aren't working here, need to double-check and report to HA
                            'topic': self.device_topic(device_id, 'lwt'),
                            'payload_available': 'online',
                            'payload_not_available': 'offline',
                        },
                        {
                            'topic': self.topic('lwt'),
                            'payload_available': 'online',
                            'payload_not_available': 'offline',
                        },
                    ],
                    'availability_mode': 'all',
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
        if self.args.homeassistant_discovery:
            return '{}/{}'.format(self.args.homeassistant_discovery, topic)

        return None

    def format_device(self, device_id: int) -> str:
        return '{:08x}'.format(device_id)

    def device_topic(self, device_id: int, topic: str) -> str:
        if topic:
            return self.topic('{}/{}'.format(self.format_device(device_id), topic))

        return self.topic('{}'.format(self.format_device(device_id)))

    def on_connect(self, client: mqtt.Client, userdata, flags, rc):
        if self.args.homeassistant_discovery:
            client.subscribe(self.args.homeassistant_status_topic)
        client.publish(self.topic('lwt'), payload='online')

    def on_message(self, client: mqtt.Client, userdata, msg: mqtt.MQTTMessage):
        if msg.topic.endswith('/send_raw_command'):
            try:
                self.mqtt_events_queue.put(protocol.format.parse(bytes.fromhex(msg.payload.decode('ascii'))))
            except:
                pass
        elif msg.topic == self.args.homeassistant_status_topic and msg.payload == b'online':
            # We need to repeat non-retainable topics when HASS restarted
            client.publish(self.topic('lwt'), payload='online')
            for device_id in self._device_state.keys():
                self.report_state(device_id)

    def stop(self):
        self._stop = True
