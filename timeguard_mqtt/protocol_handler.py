import argparse
from datetime import datetime
from binascii import hexlify
from typing import List, Tuple, Optional

from construct import debug
from .protocol import timeguard
import socket
from queue import Queue
from time import sleep
from copy import deepcopy


class ProtocolHandler:
    CLOUDWARM_IP = '31.193.128.139'  # www.cloudwarm.net

    def __init__(self, args, network_events_queue: Queue, mqtt_events_queue: Queue):
        self.args = args
        self.network_events_queue = network_events_queue
        self.mqtt_events_queue = mqtt_events_queue
        self.device_to_ip_map = dict()

    def prepare_argparse(parser: argparse._ActionsContainer):
        parser.add_argument('--mode', '-m', choices=['relay', 'fallback', 'local'],
                            help='Desired behaviour of the program. Relay — simply forward requests between the '
                            + 'server and the device (default). Fallback — send responses to some of the commands, '
                            + 'like PING and INIT. Local — do not anything to the remote server.', default='relay')
        parser.add_argument('--debug', '-d', help='Display communication data and other debug info.',
                            action='store_true')
        parser.add_argument('--print-parsed-data', '-p',
                            help='Print the internal sturctures to stdout.', action='store_true')
        parser.add_argument('--mask', '-s', help='Mask device ID and CRC32 in the debug output.', action='store_true')

    def run(self):
        self._stop = False
        self.relay()

    def stop(self):
        self._stop = True

    def print_bytes(source_ip: str, source_port: int, destination_ip: Optional[str], destination_port: Optional[int],
                    parsing_result: str, data: bytes):
        print("[{}] [{}:{} -> {}:{}] [parsing:{}] {}".format(
            datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f'),
            source_ip,
            source_port,
            destination_ip,
            destination_port,
            parsing_result,
            hexlify(data, ' ', 1).decode('ascii'))
        )

    def print_debug(self, source_ip: str, source_port: int, destination_ip: Optional[str],
                    destination_port: Optional[int], data: bytes, parsed_data: Optional[timeguard.Timeguard]):
        if not self.args.debug and not self.args.print_parsed_data:
            return

        parsing_result: str = 'success'
        if parsed_data is None:
            parsing_result = 'failed'
        if isinstance(parsed_data.payload.params, bytes):
            parsing_result = 'unknown'

        try:
            if self.args.debug or self.args.print_parsed_data:
                debug_data = deepcopy(data)
                if parsed_data:
                    debug_obj = deepcopy(parsed_data)
                    if self.args.mask:
                        debug_obj.payload.device_id = 0x12345678

                        # Hiding the device id is not enough — it's relatively easy to restore it when you know the
                        # checksum.
                        # The easiest way to replace the checksum and keep the packet valid is to build it and parse
                        # again, `construct` would take care of the rest.
                        debug_obj = timeguard.format.parse(timeguard.format.build(debug_obj))
                        debug_data = timeguard.format.build(debug_obj)

                if self.args.debug:
                    ProtocolHandler.print_bytes(source_ip, source_port, destination_ip,
                                                destination_port, parsing_result, debug_data)

                if self.args.print_parsed_data and debug_obj:
                    print(debug_obj)
        except:
            parsing_result = 'failed_debug'
            import traceback
            traceback.print_exc()

        if self.args.debug and not self.args.mask:
            ProtocolHandler.print_bytes(source_ip, source_port, destination_ip, destination_port, parsing_result, data)

    def relay_callback(self, source_ip: str, source_port: int, data: bytes) -> List[Tuple[bool, bytes]]:
        is_from_client = source_ip != self.CLOUDWARM_IP
        parsed_data = None
        try:
            parsed_data = timeguard.format.parse(data)
        except:
            import traceback
            traceback.print_exc()

        destination_ip, destination_port = None, None
        if parsed_data:
            if is_from_client:
                destination_ip, destination_port = self.CLOUDWARM_IP, 9997
                self.store_client(parsed_data.payload.device_id, source_ip, source_port)
            else:
                destination_ip, destination_port = self.get_client(parsed_data.payload.device_id)

        self.print_debug(source_ip, source_port, destination_ip, destination_port, data, parsed_data)

        if destination_ip is None:
            return []

        if parsed_data:
            self.network_events_queue.put(parsed_data)

        method = 'process_request_{}'.format(self.args.mode)
        return getattr(self, method)(destination_ip, destination_port, parsed_data)

    def process_request_relay(self, destination_ip: str, destination_port: int, data: timeguard.Timeguard) -> List[Tuple[str, int, bytes]]:
        return [(destination_ip, destination_port, timeguard.format.build(data))]

    def process_request_fallback(self, destination_ip: str, destination_port: int, data: timeguard.Timeguard) -> List[Tuple[str, int, bytes]]:
        return [(destination_ip, destination_port, timeguard.format.build(data))]

    def process_request_local(self, destination_ip: str, destination_port: int, data: timeguard.Timeguard) -> List[Tuple[str, int, bytes]]:
        return []

    def store_client(self, device_id: int, ip: str, port: int):
        if device_id not in self.device_to_ip_map:
            self.device_to_ip_map[device_id] = ip, port

    def get_client(self, device_id) -> Tuple[Optional[str], Optional[int]]:
        return self.device_to_ip_map.get(device_id, (None, None))


    def relay(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        sock.setblocking(False)
        sock.bind(("0.0.0.0", 9997))

        while True:
            if self._stop:
                break

            try:
                data, fromaddr = sock.recvfrom(1024)
            except BlockingIOError:
                sleep(0.1)
                continue
            except Exception:
                import traceback
                traceback.print_exc()
                sleep(0.1)
                continue

            rewritten_data = self.relay_callback(fromaddr[0], fromaddr[1], data)

            for (destination_ip, destination_port, data) in rewritten_data:
                sock.sendto(data, (destination_ip, destination_port))
