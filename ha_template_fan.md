If you want to add a Fan entity to Home Assistant which just toggles the device between on and off (using the Always On/Off modes in TimeGuard), this worked for an FSTWIFI Switch:

```yaml
- platform: template
  fans:
    kitchen_extractor:
      friendly_name: "Kitchen Extractor"
      unique_id: kitchen_extractor_timeguard
      availability_template: "{{ (states('select.timeguard_time_switch_work_mode') == 'unavailable') | iif('off', 'on') }}"
      value_template: "{{ (states('select.timeguard_time_switch_work_mode') == 'Always off') | iif('off', 'on') }}"
      turn_on:
        service: select.select_option
        data:
          option: Always on
        target:
          entity_id: select.timeguard_time_switch_work_mode
      turn_off:
        service: select.select_option
        data:
          option: Always off
        target:
          entity_id: select.timeguard_time_switch_work_mode
```

This needs to either be intented under `fans:` in your `configuration.yaml` file, or added to a `fans.yaml` file which is referenced in `configuration.yaml` (e.g. `fans: !include fans.yaml`), and `select.timeguard_time_switch_work_mode` will need replacing with the correct entity_id of your Work Mode select.
