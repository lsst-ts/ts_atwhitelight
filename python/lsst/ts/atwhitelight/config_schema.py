# This file is part of ts_atwhitelight.
#
# Developed for the Vera C. Rubin Observatory Telescope and Site Systems.
# This product includes software developed by the LSST Project
# (https://www.lsst.org).
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

__all__ = ["CONFIG_SCHEMA"]

import yaml


CONFIG_SCHEMA = yaml.safe_load(
    """
$schema: http://json-schema.org/draft-07/schema#
$id: https://github.com/lsst-ts/ts_atwhitelight/blob/develop/python/lsst/ts/atwhitelight/config_schema.py
# title must end with one or more spaces followed by the schema version, which must begin with "v"
title: Whitelight v2
description: Schema for AT White Light configuration files
type: object
properties:
  chiller:
    description: Configuration for the ThermoTek T257P chiller
    type: object
    properties:
      host:
        description: IP address of the ethernet interface to the chiller.
        type: string
      port:
        description: Port of of the ethernet interface to the chiller.
        type: number
      initial_temperature:
        description: >-
          The control temperature to specify when the CSC first connects to the chiller (C).
          (If the CSC later reconnects to the chiller, it will command the
          most recently specified control temperature, rather than this value.)
          Must be in range [low_supply_temperature_warning, high_supply_temperature_warning], inclusive.
        type: number
      low_ambient_temperature_warning:
        description: Threshold for publishing a warning for low ambient temperature (C)
        type: number
        minimum: 0
        maximum: 50
      high_ambient_temperature_warning:
        description: Threshold for publishing a warning for high ambient temperature (C)
        type: number
        minimum: 0
        maximum: 50
      low_supply_temperature_warning:
        description: Threshold for publishing a warning for low supply temperature (C)
        type: number
        minimum: -7
        maximum: 50
      high_supply_temperature_warning:
        description: Threshold for publishing a warning for high supply temperature (C)
        type: number
        minimum: -7
        maximum: 50
      low_coolant_flow_rate_warning:
        description: Threshold for publishing a warning for low coolant flow rate (liters/min)
        type: number
        minimum: 0
      low_ambient_temperature_alarm:
        description: >-
          Threshold for turning off the lamp and going to fault state
          due to low ambient temperature (C)
        type: number
        minimum: 0
        maximum: 50
      high_ambient_temperature_alarm:
        description: >-
          Threshold for turning off the lamp and going to fault state
          due to high ambient temperature (C)
        type: number
        minimum: 0
        maximum: 50
      low_supply_temperature_alarm:
        description: >-
          Threshold for turning off the lamp and going to fault state
          due to low supply temperature (C)
        type: number
        minimum: -7
        maximum: 50
      high_supply_temperature_alarm:
        description: >-
          Threshold for turning off the lamp and going to fault state
          due to high supply temperature (C)
        type: number
        minimum: -7
        maximum: 50
      low_coolant_flow_rate_alarm:
        description: >-
          Threshold for turning off the lamp and going to fault state
          due to low coolant flow (liters/min)
        type: number
        minimum: 0
      connect_timeout:
        description: >-
          Maximum time to connect to the chiller's TCP/IP port (seconds).
        type: number
        exclusiveMinimum: 0
      command_timeout:
        description: >-
          Maximum time for the chiller to reply to a command (seconds).
        type: number
        exclusiveMinimum: 0
      telemetry_interval:
        description: >-
          Interval (seconds) after one set of telemetry commands
          finishes before queuing the next set. These commands are run
          at low priority, so the actual interval before the next command
          runs may be longer.
        type: number
        exclusiveMinimum: 0
      watchdog_interval:
        description: >-
          Minimum interval (seconds) between watchdog commands.
          Watchdog data is more important than telemetry data;
          it includes whether the chiller is running and whether
          there are any alarms or warnings.
        type: number
        exclusiveMinimum: 0
    required:
      - host
      - port
      - initial_temperature
      - low_ambient_temperature_warning
      - high_ambient_temperature_warning
      - low_supply_temperature_warning
      - high_supply_temperature_warning
      - low_coolant_flow_rate_warning
      - low_ambient_temperature_alarm
      - high_ambient_temperature_alarm
      - low_supply_temperature_alarm
      - high_supply_temperature_alarm
      - low_coolant_flow_rate_alarm
      - connect_timeout
      - command_timeout
      - telemetry_interval
      - watchdog_interval
    additionalProperties: false
  lamp:
    description: Configuration for the lamp controller and the LabJack that controls it
    type: object
    properties:
      device_type:
        description: LabJack device type, e.g. T4
        type: string
        enum: [T4, T7]
      connection_type:
        description: Type of LabJack connection, e.g. TCP
        type: string
      identifier:
        description: >-
            LabJack indentifier:
            * A host name or IP address if connection_type = TCP or WIFI
            * A serial number if connection_type = USB
            * For testing in an environment with only one LabJack you may use ANY
        type: string
      default_power:
        description: >-
          Default lamp power (W). This is the value used if the user issues
          the turnLampOn command with power=0.
        type: number
        minimum: 800
        maximum: 1200
      connect_timeout:
        description: Maximum time to connect and read state (seconds)
        type: number
        exclusiveMinimum: 0
      cooldown_period:
        description: >-
          How long after turning off the lamp before you can turn the lamp
          back on or turn off the chiller (seconds).
          The lamp controller documentation recommendeds 900 seconds, to preserve bulb life.
        type: number
        exclusiveMinimum: 0
      warmup_period:
        description: >-
          How long after turning on the lamp before you can turn the lamp off
          without forcing it (seconds).
          The lamp controller documentation recommendeds 900 seconds, to preserve bulb life.
        type: number
        exclusiveMinimum: 0
      shutter_timeout:
        description: Maximum time for a shutter move before giving up (seconds). Be generous.
        type: number
        exclusiveMinimum: 0
    required:
      - device_type
      - connection_type
      - identifier
      - connect_timeout
      - cooldown_period
      - warmup_period
      - default_power
      - shutter_timeout
    additionalProperties: false
required:
  - chiller
  - lamp
additionalProperties: false
"""
)
