"""Sphinx configuration file for an LSST stack package.

This configuration only affects single-package Sphinx documenation builds.
"""

import lsst.ts.atwhitelight  # noqa: F401
from documenteer.conf.pipelinespkg import *  # type: ignore # noqa: 403

project = "ts_atwhitelight"
html_theme_options["logotext"] = project  # type: ignore # noqa: 405
html_title = project
html_short_title = project
# Avoid warning: Could not find tag file _doxygen/doxygen.tag
doxylink = {}  # type: ignore

intersphinx_mapping["ts_idl"] = ("https://ts-idl.lsst.io", None)  # type: ignore # noqa: 405
intersphinx_mapping["ts_salobj"] = ("https://ts-salobj.lsst.io", None)  # type: ignore # noqa: 405
intersphinx_mapping["ts_tcpip"] = ("https://ts-tcpip.lsst.io", None)  # type: ignore # noqa: 405
intersphinx_mapping["ts_utils"] = ("https://ts-utils.lsst.io", None)  # type: ignore # noqa: 405
