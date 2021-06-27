import argparse
from queue import Queue


class Mqtt:
    def __init__(self, args, network_events_queue: Queue, mqtt_events_queue: Queue):
        self.args = args
        self.network_events_queue = network_events_queue
        self.mqtt_events_queue = mqtt_events_queue

    def prepare_argparse(parser: argparse._ActionsContainer):
        pass

    def run(self):
        pass

    def stop(self):
        pass
