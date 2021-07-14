from .mqtt import Mqtt
from .protocol_handler import ProtocolHandler
import argparse
import threading
from queue import Queue
import signal


def run():
    parser = argparse.ArgumentParser(description='Process some integers.')
    protocol_params_parser = parser.add_argument_group('Protocol', 'Protocol-related parameters')
    ProtocolHandler.prepare_argparse(protocol_params_parser)
    mqtt_params_parser = parser.add_argument_group('MQTT', 'MQTT-related parameters')
    Mqtt.prepare_argparse(mqtt_params_parser)
    args = parser.parse_args()

    network_events_queue = Queue(maxsize=0)
    mqtt_events_queue = Queue(maxsize=0)

    p = ProtocolHandler(args, network_events_queue, mqtt_events_queue)
    mqtt = Mqtt(args, network_events_queue, mqtt_events_queue)

    protocol_thread = threading.Thread(target=p.run)
    mqtt_thread = threading.Thread(target=mqtt.run)

    def termination(*args, **kwargs):
        p.stop()
        mqtt.stop()

    signal.signal(signal.SIGINT, termination)
    signal.signal(signal.SIGTERM, termination)

    try:
        protocol_thread.start()
        mqtt_thread.start()

        mqtt_thread.join()
        protocol_thread.join()
    except KeyboardInterrupt:
        termination()


if __name__ == '__main__':
    run()
