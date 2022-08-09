.. py:currentmodule:: lsst.ts.atwhitelight

.. _lsst.ts.atwhitelight.developer_guide:

###############
Developer Guide
###############

The ATWhiteLight CSC is implemented using `ts_salobj <https://github.com/lsst-ts/ts_salobj>`_.

The white light system consists of three components:

* A KiloArc lamp controller that controls a mercury-vapor lamp with a range 800-1200W.
  This controller has a very primitive interface:
  
  * One analog input controls lamp power.

  * Several binary outputs indicate status.
    One of these is a "blinking" error signal, which uses the number of 1Hz blinks to indicate the error.

* A shutter controlled by a linear actuator.

* A ThermoTek T257P chiller.

The CSC controls the lamp controller and linear actuator using a LabJack T4 I/O module via the `LabJack ljm library <https://labjack.com/ljm>`_.

The CSC controls the ThermoTek chiller via a TCP/IP to RS-232 adapter connected to the chiller's RS-232 interface.
The communication protocol is described in detail in :download:`TTK Serial Communication Protocol.<TTK Serial Communication Protocol.pdf>`.
The chiller will ignore new commands until it has responded to the currently executing command.
There are a few quirks that I did not find described in the manuals:

* The T247P can only use the source coolant temperature sensor as the control sensor.
  The user manual says you can buy an option to use other sensors (such as the return sensor), but David R. Grey of ThermoTek says that is incorrect.
* The communication interface manual claims the chiller only accepts one command per second, but that is incorrect.
  The only rule that limits the rate of commands (based on direct communication from Barry Houtchen of ThermoTek) is that you must wait for each reply before sending the next command.
* A response of "#23\r" is possible, though it does not match the standard reply format.
  Barry Houtchen says "it is usually seen when a command is sent to the chiller with a parameter that is out of bounds (for example, trying to set the temperature a number greater than 45C)".
  This is surprising because there is also a documented error code (3) for parameter out of bounds, which can be returned using a normally formatted response.
  In any case we see "#23\r" in response to 16sCtrlSen.
* Command 18 "Read Alarm State Level 1" also resets level 1 alarms (even if they are latched).
  (Command 19 "Read Alarm State Level 2" does not reset alarms).
  Resetting an alarm while leaving the chiller in standby can cause a serious problem, due to a Chiller bug:

  * The user interface code checks alarms every 1.5 seconds.
  * If an alarm occurs that puts the chiller in standby and the alarm is reset by command 18 during this 1.5 seconds, the user interface code will display a "mode mismatch alarm" which requires power cycling the chiller.

  We have worked around this by explicitly commanding the chiller standby as soon as the watchdog reports that there is an alarm.
  This avoids the mode mismatch alarm because the user interface will see that the chiller has been commanded to be in standby.
  Note that the chiller should already be in standby due to the alarm, so this should not reduce chilling.

* The value reported for the return coolant temeperature sensor is not correct (far too low).
  We don't know why.

.. _lsst.ts.atwhitelight.api:

API
===

.. automodapi:: lsst.ts.atwhitelight
    :no-main-docstr:

.. _lsst.ts.atwhitelight.build:

Build and Test
==============

This is a pure python package.
There is nothing to build except the documentation.

.. code-block:: bash

    make_idl_files.py atwhitelight
    setup -r .
    pytest -v  # to run tests
    package-docs clean; package-docs build  # to build the documentation

.. _lsst.ts.atwhitelight.contributing:

Contributing
============

``lsst.ts.atwhitelight`` is developed at https://github.com/lsst-ts/ts_atwhitelight.
Bug reports and feature requests use `Jira with labels=ts_atwhitelight <https://jira.lsstcorp.org/issues/?jql=project%20%3D%20DM%20AND%20labels%20%20%3D%20ts_atwhitelight>`_.
