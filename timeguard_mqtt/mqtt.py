import argparse
from queue import Queue, Empty as QueueEmptyError
from time import sleep, time
import paho.mqtt.client as mqtt
from typing import Optional, List
from . import protocol
import json
from datetime import datetime
from dateutil.relativedelta import relativedelta, SU


class Mqtt:
    BOOST_MAP = {
        protocol.BoostState.OFF: 'Off',
        protocol.BoostState.ONE_HOUR: '1 hour',
        protocol.BoostState.TWO_HOURS: '2 hours',
    }

    BOOST_MAP_REVERSE = dict(zip(BOOST_MAP.values(), BOOST_MAP.keys()))

    WORK_MODE_MAP = {
        protocol.WorkMode.ALWAYS_OFF: 'Always off',
        protocol.WorkMode.ALWAYS_ON: 'Always on',
        protocol.WorkMode.AUTO: 'Auto',
        protocol.WorkMode.HOLIDAY: 'Holiday',
    }

    WORK_MODE_MAP_REVERSE = dict(zip(WORK_MODE_MAP.values(), WORK_MODE_MAP.keys()))

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
        parser.add_argument('--device-online-timeout', default=50, type=int)

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
            except:
                import traceback
                traceback.print_exc()

        self.report_offline(self.topic('lwt'))

        for device_id in self._device_state.keys():
            self.report_offline(self.device_topic(device_id, 'lwt'))

        self.client.disconnect()
        self.client.loop_stop()

    def report_offline(self, topic: str):
        self.client.publish(topic, payload='offline', retain=True)

    def handle_client_ping(self, payload: protocol.Payload):
        device_id = payload.device_id
        payload_params: protocol.PingRequest = payload.params
        self.update_device_state(device_id, 'uptime', payload_params.uptime)
        self.update_device_state(
            device_id,
            'switch_state',
            'ON' if payload_params.state.switch_state == protocol.SwitchState.ON else 'OFF'
        )
        self.update_device_state(
            device_id,
            'load_detected',
            'ON' if payload_params.state.load_detected else 'OFF'
        )
        self.update_device_state(
            device_id,
            'advance_mode',
            'ON' if payload_params.state.advance_mode_state == protocol.AdvanceState.ON else 'OFF'
        )
        self.update_device_state(
            device_id,
            'load_was_detected_previously',
            'ON' if payload_params.state.load_was_detected_previously else 'OFF'
        )
        self.update_device_state(
            device_id,
            'boost',
            self.BOOST_MAP.get(payload_params.boost.boost_type, 'Unknown')
        )
        self.update_device_state(
            device_id,
            'work_mode',
            self.WORK_MODE_MAP.get(payload_params.work_mode, 'Unknown')
        )

        boost_duration_left = '00:00'
        if payload_params.boost.minutes_from_sunday:
            now = datetime.now()
            sunday_midnight = now.replace(hour=0, minute=0, second=0,
                                          microsecond=0) + relativedelta(weekday=SU(-1))
            boost_off_time = sunday_midnight + \
                relativedelta(minutes=payload_params.boost.expected_finish_time)
            boost_duration_left = ':'.join(str(boost_off_time - now).split(':')[0:2])
        self.update_device_state(device_id, 'boost_duration_left', boost_duration_left)

        self.report_state(device_id, 'uptime', 'switch_state', 'load_detected', 'advance_mode',
                          'load_was_detected_previously', 'boost', 'work_mode', 'boost_duration_left')

    def handle_client_code_version(self, payload: protocol.Payload):
        if payload.message_flags & protocol.MessageFlags.IS_UPDATE_REQUEST == 0:
            payload_params: protocol.GetCodeVersionResponse = payload.params
            code_version: str = payload_params.code_version
        else:
            payload_params: protocol.ReportCodeVersionRequest = payload.params
            code_version: str = payload_params.code_version

        device_id = payload.device_id

        self.update_device_state(device_id, 'code_version', code_version)
        self.report_state(device_id, 'code_version')

    def handle_protocol_data(self, data: protocol.Timeguard):
        payload = data.payload
        device_id = payload.device_id
        if payload.message_flags & protocol.MessageFlags.IS_FROM_SERVER == 0:
            if device_id not in self._device_state:
                self._device_state[device_id] = {
                    'parameters': {},
                }
                self.setup_device(device_id)
                if self.args.homeassistant_discovery:
                    self.setup_hass(device_id)

            self._device_state[device_id]['last_command'] = time()

        callback_name = 'handle_{}_{}'.format(
            'client' if payload.message_flags & protocol.MessageFlags.IS_FROM_SERVER == 0 else 'server',
            payload.message_type.name.lower()
        )

        if hasattr(self, callback_name):
            getattr(self, callback_name)(payload)

    def report_state(self, device_id: int, *params_to_report):
        for key, value in self._device_state[device_id]['parameters'].items():
            if params_to_report and key not in params_to_report:
                continue
            self.client.publish(self.device_topic(device_id, key), payload=value, qos=1)

    def update_device_state(self, device_id: int, parameter: str, value: str):
        self._device_state[device_id]['parameters'][parameter] = value

    def topic(self, topic: str) -> str:
        return '{}/{}'.format(self.args.mqtt_root_topic, topic)

    def setup_device(self, device_id: int):
        self.client.subscribe(self.device_topic(device_id, '+/set'))

    def setup_hass(self, device_id: int):
        self.configure_hass_sensor(device_id, 'sensor', 'uptime', 'Uptime', unit_of_measurement='s')
        self.configure_hass_sensor(device_id, 'sensor', 'boost_duration_left', 'Boost left')
        self.configure_hass_sensor(device_id, 'sensor', 'code_version', 'Code version')
        self.configure_hass_sensor(device_id, 'binary_sensor', 'switch_state', 'Switch state')
        self.configure_hass_sensor(device_id, 'binary_sensor', 'load_detected', 'Load detected')
        self.configure_hass_sensor(device_id, 'binary_sensor', 'load_was_detected_previously',
                                   'Load was detected prevously')
        self.configure_hass_sensor(device_id, 'switch', 'advance_mode',
                                   'Advance mode', command_topic='~/advance_mode/set')
        self.configure_hass_sensor(device_id, 'select', 'boost', 'Boost',
                                   command_topic='~/boost/set', options=list(self.BOOST_MAP.values()))
        self.configure_hass_sensor(device_id, 'select', 'work_mode', 'Work mode',
                                   command_topic='~/work_mode/set', options=list(self.WORK_MODE_MAP.values()))

        self.client.publish(self.topic('lwt'), payload='online', qos=1)
        self.client.publish(self.device_topic(device_id, 'lwt'), payload='online', qos=1)

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
            qos=1,
            retain=True
        )

    def discovery_unique_id(self, device_id: int, sensor: str) -> str:
        return 'timeguard_{}_{}'.format(self.format_device(device_id), sensor)

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
        client.publish(self.topic('lwt'), payload='online', qos=1)

    def on_message_set_raw_command(self, client: mqtt.Client, userdata, msg: mqtt.MQTTMessage, device_id: int):
        self.mqtt_events_queue.put(protocol.format.parse(bytes.fromhex(msg.payload.decode('ascii'))))

    def on_message_set_boost(self, client: mqtt.Client, userdata, msg: mqtt.MQTTMessage, device_id: int):
        boost = self.BOOST_MAP_REVERSE.get(msg.payload.decode('utf-8'))

        if boost is None:
            raise Exception('Unknown boost mode requested: {}'.format(msg.payload))

        data = protocol.Timeguard.prepare(
            protocol.MessageType.BOOST,
            protocol.MessageFlags.server(True),
            device_id,
            boost_type=boost
        )
        self.mqtt_events_queue.put(data)

    def on_message_set_advance_mode(self, client: mqtt.Client, userdata, msg: mqtt.MQTTMessage, device_id: int):
        advance = protocol.AdvanceState.ON if msg.payload == b'ON' else protocol.AdvanceState.OFF
        data = protocol.Timeguard.prepare(
            protocol.MessageType.ADVANCE,
            protocol.MessageFlags.server(True),
            device_id,
            mode=advance
        )
        self.mqtt_events_queue.put(data)

    def on_message_set_work_mode(self, client: mqtt.Client, userdata, msg: mqtt.MQTTMessage, device_id: int):
        work_mode = self.WORK_MODE_MAP_REVERSE.get(msg.payload.decode('utf-8'))

        if work_mode is None:
            raise Exception('Unknown work mode mode requested: {}'.format(msg.payload))

        data = protocol.Timeguard.prepare(
            protocol.MessageType.WORK_MODE,
            protocol.MessageFlags.server(True),
            device_id,
            work_mode=work_mode
        )
        self.mqtt_events_queue.put(data)

    def on_message(self, client: mqtt.Client, userdata, msg: mqtt.MQTTMessage):
        last_3_parts = msg.topic.split('/')[-3:]
        device_id = last_3_parts[0]
        on_message_callback_name = 'on_message_' + '_'.join(last_3_parts[-2:][::-1])
        if len(last_3_parts) == 3 and hasattr(self, on_message_callback_name):
            try:
                getattr(self, on_message_callback_name)(client, userdata, msg, int(device_id, 16))
            except:
                import traceback
                traceback.print_exc()
        elif msg.topic == self.args.homeassistant_status_topic and msg.payload == b'online':
            # We need to repeat non-retainable topics when HASS restarted
            client.publish(self.topic('lwt'), payload='online', qos=1)
            for device_id in self._device_state.keys():
                client.publish(self.device_topic(device_id, 'lwt'), payload='online', qos=1)
                self.report_state(device_id)

    def stop(self):
        self._stop = True
