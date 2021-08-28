# timeguard-mqtt

This Python module provides an open-source implementation of the device API used by the Timeguard's NTTWIFI and FSTWIFI
devices.

This implementation is based on the [investigation of the API](https://github.com/rjpearce/timeguard-supplymaster/issues/1).

It is currently in the early stages of development, contributions are always welcome.

**USE IT AT YOUR OWN RISK.**

## Legal Disclaimer

This software is un-official and is not endorsed or associated with Timeguard Limited in any way shape or form.

This information used has been gathered legally using the NTTWIFI device, [Wireshark](https://www.wireshark.org) and
[socat](http://www.dest-unreach.org/socat/).

This software is being developed to aid my own personal efforts to make the device work offline.

The software is provided “as is”, without warranty of any kind, express or implied, including but not limited to the
warranties of merchantability, fitness for a particular purpose and noninfringement. in no event shall the authors
or copyright holders be liable for any claim, damages or other liability, whether in an action of contract, tort or
otherwise, arising from, out of or in connection with the softwares or the use or mis-used or other dealings in the
software.

## Features

- [x] `--mode relay`: Act as a relay-proxy between the device and the server — blindly proxy data from one to another.
Device will stop functioning without internet connection
- [ ] Complete protocol awareness (**be advised** without this the program could brake your device on "write" commands)
- [x] `--mode fallback`: Act as fallback proxy: the program is able to support some "basic" level of communication
with the device and at the same time you can use the SupplyMaster application on your phone to control everything.
Device will continue to function without the internet connection
- [ ] `--mode local` Local server: app can do everything the server can (except for the support of mobile app, of
course). You don't need internet at all to work with the timeswitch
  - [x] Basic level (the program replies only to mandatory messages)
  - [ ] Full — you can controll everything using only this program, including schedules and holidays
- [ ] Reporting state to MQTT
  - [x] Basic info: switch status, load, advance mode, boost, uptime, work mode
  - [ ] Holiday info
  - [ ] Schedule-related info
	- [x] Name and the ID of currently selected schedule
	- [ ] Next on/off time
	- [ ] All the details about a schedule (time, repetitions)
- [ ] Control over MQTT (**be advised** there's no guarantee that this will not break your device, use it at own risk)
  - [x] Basic: boost, advance, work mode
  - [ ] Holiday info
  - [ ] Schedule
	- [x] Name and the ID of currently selected schedule
	- [ ] Next on/off time
	- [ ] All the details about a schedule (time, repetitions)

## How To

Start the program using docker:

```
docker run -d --name timeguard-mqtt \
  --restart unless-stopped \
  -p 9997:9997/udp \
  -e TZ=Europe/London \
  ghcr.io/andrey-yantsen/timeguard-mqtt:main \
  --mode fallback \
  --debug \
  --mask
```

The options `--debug` and `--mask` are optional, but at the current stage there's now reasons to run the program 
without them. `--mode fallback` is optional too, but it's highly recommended to run the program with it — in this case
your timeswitch will continue to function in case of unexpected issues with your internet connection.

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

The most sensitive information here is the Device ID (you can see it as `78 56 34 12`) — because the program was run
with `--mask` argument, it hides this information and you should be perfectly safe sharing the resulting logs.

## MQTT

To enable MQTT-communication use the following options:
* `--mqtt-host` the IP/domain of your MQTT-broker
* `--mqtt-port` port of the MQTT broker, if different from 1883
* `--mqtt-clientid`
* `--mqtt-root-topic`
* `--mqtt-username`
* `--mqtt-password`

If you want to enable auto-discovery for home-assistant, you also need to pass the root discovery topic using 
`--homeassistant-discovery` and home-assistant's status topic with `--homeassistant-status-topic`.

After that you will see the following set of topics, for each device:

```
timeguard/12345678/uptime 158926
timeguard/12345678/switch_state OFF
timeguard/12345678/load_detected OFF
timeguard/12345678/advance_mode OFF
timeguard/12345678/load_was_detected_previously ON
timeguard/12345678/boost Off
timeguard/12345678/work_mode Auto
timeguard/12345678/boost_duration_left 00:00
```

Where `12345678` is the device id. Three of those topics are settable:

* `boost/set`: turn on boost mode for the specified period of time. Possible values: 'Off', '1 hour' and '2 hours';
* `advance/set`: controls advance mode: it will set the switch to On (if it's currently off, and vice-versa) until the
next schedule. Possible values: `ON` and `OFF`;
* `work_mode/set`: changes the device's work mode. Possible values: `Always off`, `Always on`, `Auto` and `Holiday`.

## How to help

1. Keep the program up and running for at least 24 hours (the more — the better); note the timestamps when you do
something with the device;
2. Grab all the logs you will receive and save it as [gist](https://gist.github.com);
3. Create a new [discussion](https://github.com/andrey-yantsen/timeguard-mqtt/discussions) and share your logs.
