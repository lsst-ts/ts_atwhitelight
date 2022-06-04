.. py:currentmodule:: lsst.ts.atwhitelight

.. _lsst.ts.atwhitelight:

####################
lsst.ts.atwhitelight
####################

.. image:: https://img.shields.io/badge/SAL\ Interface-gray.svg
    :target: https://ts-xml.lsst.io/sal_interfaces/ATWhiteLight.html
.. image:: https://img.shields.io/badge/GitHub-gray.svg
    :target: https://github.com/lsst-ts/ts_atwhitelight
.. image:: https://img.shields.io/badge/Jira-gray.svg
    :target: https://jira.lsstcorp.org/issues/?jql=labels+%3D+ts_atwhitelight

.. _lsst.ts.atwhitelight.overview:

Overview
========

ts_atwhitelight controls the Vera C. Rubin Observatory Auxiliary Telescope white light calibration source.

This light source feeds a monochromator (ATMonochromator), which in turns illuminates the flat field screen.

The white light system is comprised of the following components:

* A KiloArc lamp controller that controls a mercury-vapor lamp with a range 800-1200W. We have two manuals for this: a :download:`user guide <KiloArc Lamp with optional computer control manual rev N.pdf>` and a supplement describing the :download:`remote control option <Remote control option for the KiloArc.pdf>`.

* A ThermoTek T257P chiller. We have two manuals for this: A :download:`user guide <T257P User Manual_Rev X1_02.pdf>` and a detailed description of the :download:`serial communication protocol <TTK Serial Communication Protocol.pdf>`.

* A shutter controlled by a linear actuator.

* A `LabJack T4 <https://labjack.com/products/t4>`_ I/O module to control the lamp controller and linear actuator.

.. _lsst.ts.atwhitelight.preserving_bulb_life:

Preserving Bulb Life
--------------------

The CSC enforces the following rules, in order to extend the life of these expensive bulbs:

* You may not turn on the lamp unless the chiller is running.

* Warmup phase: the lamp must remain on for at least config.lamp.warmup_duration=900 seconds before you can turn it off without forcing it.
  This gives the mercury time to fully evaporate.
  If absolutely necessary you can force the lamp off sooner by issuing the turnLampOff command with force=True.
  The CSC will force the lamp off and go to fault state if it detects a problem with the chiller or lamp controller.

* Cooldown phase: the lamp must remain off for least config.lamp.cooldown_duration=900 seconds before you can turn it on again.
  This gives the mercury time to fully recondense.

* You may not turn off the chiller while the lamp is on or cooling down.

In addition, the Operating Parameters section of the manual says the following for the He-Xe bulbs:

* Average bulb lifetime is 1500 hours when operated at 1000 W.

* Operating the lamp at 800 W can increase the bulb lifetime by approximately 5%.

* Operating the lamp at 1200 W can decrease the bulb lifetime by approximately 10%.

* Bulb lifetime will decrease 10 to 20 minutes for each ignition.

.. _lsst.ts.atwhitelight.user_guide:

User Guide
==========

Start the ATWhiteLight CSC as follows:

.. prompt:: bash

    run_atwhitelight

Stop the CSC by sending it to the OFFLINE state.

Turn the lamp on as follows (after you enable the CSC):

* Set a chiller temperature with ``setChillerTemperature``.
  You may omit this step if the configured ``chiller.initial_temperature`` is appropriate.

* Turn the chiller on with ``startChiller``.

* Wait for the temperature to roughly stabilize, as reported by the ``chillerTemperatures`` telemetry topic.

* Turn the lamp on with ``turnLampOn``.
  You may specify ``power=0`` to use the configured ``lamp.default_power``.

* Wait for the lamp state to change from WARMUP to ON, as reported in the ``basicState`` field of the ``lampState`` event.
  This should take 15 minutes (but is specified by configuration parameter ``bulb.warmup_duration``).

Turn the lamp off, use this sequence:

* Turn the lamp off with ``turnLampOff``.
  Specify ``force=True`` only if in an emergency, as it can greatly shorten bulb life and these bulbs are expensive.

* Wait for the lamp state to change from COOLDOWN to OFF, as reported in the ``basicState`` field of the ``lampState`` event.
  This should take 15 minutes (but is specified by configuration parameter ``bulb.cooldown_duration``).

* When you are done using the lamp, turn the chiller off with ``stopChiller``.

See ATWhiteLight `SAL communication interface <https://ts-xml.lsst.io/sal_interfaces/ATWhiteLight.html>`_ for full information on commands, events and telemetry.

.. _lsst.ts.atwhitelight.configuration:

Configuration
-------------

Configuration is defined by `this schema <https://github.com/lsst-ts/ts_atwhitelight/blob/develop/schema/atwhitelight.yaml>`_.

Configuration files live in `ts_config_atcalsys/ATWhiteLight <https://github.com/lsst-ts/ts_config_atcalsys/tree/develop/ATWhiteLight>`_.

.. _lsst.ts.atwhitelight.simulation:

Simulator
---------

The CSC includes a simulation mode. To run using simulation:

.. prompt:: bash

    run_atwhitelight --simulate

Developer Guide
===============

.. toctree::
    developer_guide
    :maxdepth: 1

Version History
===============

.. toctree::
    version_history
    :maxdepth: 1
