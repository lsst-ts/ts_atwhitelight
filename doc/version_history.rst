.. py:currentmodule:: lsst.ts.atwhitelight

.. _lsst.ts.atwhitelight.version_history:

###############
Version History
###############

v0.3.1
------
* Remove setup.cfg.
* Remove pytest plugin calls in pyproject.toml.
* Fix conda recipe by including {{python}} and removing redundant dependencies.

v0.3.0
------

* Support the new photo sensor, including changing the turnLampOn and turnLampOff commands to wait for light to be detected/not detected.
  This requires ts_xml 16, ts_idl 4.4 and ts_config_atcalsys 0.7.
* Read lamp set voltage from the DAC; this is a more robust way to determine if the lamp has been commanded on.
  One side effect is the reported lamp power will usually differ slightly from the commanded power, due to quantization in the LabJack.
* Use ts_pre_commit_conf to manage pre-commit.
* ``Jenkinsfile``: use new shared library.

Requires:

* ts_idl 4.4
* ts_salobj 7.1
* ts_tcpip
* ts_utils
* IDL file for ATWhiteLight built from ts_xml 11.1

v0.2.4
------

* pre-commit: update black to 23.1.0, isort to 5.12.0, mypy to 1.0.0, and pre-commit-hooks to v4.4.0.
* ``Jenkinsfile``: do not run as root.

Requires:

* ts_idl
* ts_salobj 7.1
* ts_tcpip
* ts_utils
* IDL file for ATWhiteLight built from ts_xml 11.1

v0.2.3
------

* `ATWhiteLightCsc`: improve error handling for failure to connect to the chiller and lamp controller.
* ``conda/meta.yaml``: remove redundant ``entry_points`` section.

Requires:

* ts_idl
* ts_salobj 7.1
* ts_tcpip
* ts_utils
* IDL file for ATWhiteLight built from ts_xml 11.1

v0.2.2
------

* Fix LabJack channel assignments; they were scrambled.
* Developer Guide: add a link to TSTN-036.

Requires:

* ts_idl
* ts_salobj 7.1
* ts_tcpip
* ts_utils
* IDL file for ATWhiteLight built from ts_xml 11.1

v0.2.1
------

* Work around a chiller bug that causes the chiller to hang with "MODE MISMATCH ALARM" displayed on the panel, requiring power cycling.
* `ATWhiteLightCsc`: fix a bug whereby the CSC could try to fault when already in fault state.
* `ChillerModel`: fix incorrect values reported for alarms and warnings.
  Do this by reversing alarm and warning data strings before parsing them as hexadecimal values.
  See the note in `lsst.ts.idl.enums.ATWhiteLight.ChillerL1Alarms` for more information.
* `ChillerClient`: fix a log message that claimed to show a reply but actually showed the command.
* Remove the unused ``examples`` directory.

Requires:

* ts_idl
* ts_salobj 7.1
* ts_tcpip
* ts_utils
* IDL file for ATWhiteLight built from ts_xml 11.1

v0.2.0
------

* `ATWhiteLightCsc`: call ``super().start()`` at the beginning of the start method.
  This requires ts_salobj 7.1.
* Rename command-line scripts to remove ".py" suffix.
* Build with pyproject.toml.
* ``CONFIG_SCHEMA``: fix the id field to point to the actual file.
* ``setup.cfg``: set asyncio_mode = auto.
* Jenkinsfile: work around a new git issue.

Requires:

* ts_idl
* ts_salobj 7.1
* ts_tcpip
* ts_utils
* IDL file for ATWhiteLight built from ts_xml 11.1

v0.1.1
------

* Add a Jenkinsfile for continuous integration testing.

Requires:

* ts_idl
* ts_salobj 7
* ts_tcpip
* ts_utils
* IDL file for ATWhiteLight built from ts_xml 11.1

v0.1.0
------

* The first version with documentation and a version history.
* The first version to control the lamp controller using a LabJack I/O module.
   Prior versions used an Adam I/O module.
* Use with caution; this version has not been thoroughly tested with real hardware.

Requires:

* ts_idl
* ts_salobj 7
* ts_tcpip
* ts_utils
* IDL file for ATWhiteLight built from ts_xml 11.1
