.. py:currentmodule:: lsst.ts.atwhitelight

.. _lsst.ts.atwhitelight.version_history:

###############
Version History
###############

ledhack v0.3.beta.101
---------------------

Changes:

* Minor tweaks for clarity.

ledhack v0.3.beta.100
---------------------

Changes:

* A hacked version that controls temporarly LED lamps (and only pretends to control the chiller).

Requires:

* ts_idl
* ts_salobj 7.1
* ts_tcpip
* ts_utils
* IDL file for ATWhiteLight built from ts_xml 11.1

v0.2.2
------

Changes:

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

Changes:

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

Changes:

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

Changes:

* Add a Jenkinsfile for continuous integration testing.

Requires:

* ts_idl
* ts_salobj 7
* ts_tcpip
* ts_utils
* IDL file for ATWhiteLight built from ts_xml 11.1

v0.1.0
------

Changes:

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
