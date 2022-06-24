.. py:currentmodule:: lsst.ts.atwhitelight

.. _lsst.ts.atwhitelight.version_history:

###############
Version History
###############

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
