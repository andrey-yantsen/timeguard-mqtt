# timeguard-mqtt

This Python module provides an open-source implementation of the device API used by the Timeguard's NTTWIFI and FSTWIFI devices.

This implementation is based on the [investigation of the API](https://github.com/rjpearce/timeguard-supplymaster/issues/1).

It is currently in the early stages of development, contributions are always welcome. At the moment the program can only be used for protocol debugging.

**USE IT AT YOUR OWN RISK.**

## Legal Disclaimer

This software is un-official and is not endorsed or associated with Timeguard Limited in any way shape or form.

This information used has been gathered legally using the NTTWIFI device, [Wireshark](https://www.wireshark.org) and [socat](http://www.dest-unreach.org/socat/).

This software is being developed to aid my own personal efforts to make the device work offline.

The software is provided “as is”, without warranty of any kind, express or implied, including but not limited to the warranties of merchantability, fitness for a particular purpose and noninfringement. in no event shall the authors or copyright holders be liable for any claim, damages or other liability, whether in an action of contract, tort or otherwise, arising from, out of or in connection with the softwares or the use or mis-used or other dealings in the software.

## How To

Start the program using docker:

```
docker run -d --name timeguard-mqtt \
  --restart unless-stopped \
  -p 9997:9997/udp \
  ghcr.io/andrey-yantsen/timeguard-mqtt:main \
  --debug \
  --mask
```

The options `--debug` and `--mask` are optional, but at the current stage there's now reasons to run the program without them.

To send traffic to the relay you need to apply following rules to your router's firewall:

```
iptables -t nat -A PREROUTING -s 192.168.1.48/32 -d 31.193.128.139 -p udp -m udp --sport 9997 --dport 9997 -j DNAT --to-destination 192.168.1.213:9997
iptables -t nat -A POSTROUTING -s 192.168.1.213/32 -d 192.168.1.48/32 -p udp -m udp --sport 9997 --dport 9997 -j SNAT --to-source 31.193.128.139
```

Or here's a config for OpenWRT:

```
config redirect
	option target 'DNAT'
	option name 'Redirect binary protocol from NTTWIFI device to a relay'
	option src 'lan'
	option src_ip '192.168.1.48'
	option src_port '9997'
	option src_dip '31.193.128.139'
	option src_dport '9997'
	option dest 'lan'
	option dest_ip '192.168.1.213'
	option dest_port '9997'

config nat
	option name 'Rewrite source IP for the NTTWIFI binary protocol relay'
	option src 'lan'
	option src_ip '192.168.1.213'
	option src_port '9997'
	option dest_ip '192.168.1.48'
	option dest_port '9997'
	option target 'SNAT'
	option snat_ip '31.193.128.139'
```

Where `192.168.1.48` is the IP-address of your device, `31.193.128.139` is the IP of `www.cloudwarm.net` and `192.168.1.213` is the IP of the relay.

If everything set up correctly you will see messages like the following in when you execute `docker logs --tail 5 timeguard-mqtt`:
```
[2021-07-13 21:18:07.920480] [192.168.86.1:9997 -> 31.193.128.139:9997] [parsing:success] fa d4 1c 00 3e 02 00 00 00 06 10 00 ff 00 00 00 78 56 34 12 2a 00 64 00 00 00 00 00 5c 4d 00 00 00 00 00 00 2e 17 2d df
[2021-07-13 21:18:08.026406] [31.193.128.139:9997 -> 192.168.86.1:9997] [parsing:success] fa d4 10 00 ff ff ff ff 00 0f 04 00 ff 5f 63 6f 78 56 34 12 0f 03 ee 60 c2 c1 2d df
[2021-07-13 21:18:08.029554] [31.193.128.139:9997 -> 192.168.86.1:9997] [parsing:unknown] fa d4 0c 00 ff ff ff ff 04 0c 00 00 a1 31 37 30 78 56 34 12 12 e5 2d df
[2021-07-13 21:18:11.039816] [31.193.128.139:9997 -> 192.168.86.1:9997] [parsing:unknown] fa d4 0c 00 ff ff ff ff 04 0c 00 00 a1 73 74 61 78 56 34 12 8e 43 2d df
[2021-07-13 21:18:11.344465] [192.168.86.1:9997 -> 31.193.128.139:9997] [parsing:unknown] fa d4 10 00 40 02 00 00 04 05 04 00 a1 00 00 00 78 56 34 12 00 00 00 00 dd 03 2d df
[2021-07-13 21:18:11.449010] [31.193.128.139:9997 -> 192.168.86.1:9997] [parsing:success] fa d4 0c 00 ff ff ff ff 09 0c 00 00 a2 5f 63 6f 78 56 34 12 02 bf 2d df
[2021-07-13 21:18:11.555700] [192.168.86.1:9997 -> 31.193.128.139:9997] [parsing:success] fa d4 18 00 41 02 00 00 09 05 0c 00 a2 00 00 00 78 56 34 12 00 74 00 00 c8 73 ea 60 00 86 eb 60 1e be 2d df
```

The most sensitive information here is the Device ID (you can see it as `78 56 34 12`) — because the program was run with `--mask` argument, it hides this
information and you should be perfectly safe sharing the resulting logs.

# How to help

1. Keep the program up and running for at least 24 hours (the more — the better); note the timestamps when you do something with the device
2. Grab all the logs you will receive and save it as [gist](https://gist.github.com)
3. Create a new [discussion](https://github.com/andrey-yantsen/timeguard-mqtt/discussions) and share your logs
