"""Sphinx configuration file for an LSST stack package.

This configuration only affects single-package Sphinx documenation builds.
"""

from documenteer.sphinxconfig.stackconf import build_package_configs
import lsst.ts.ATWhiteLightSource


_g = globals()
_g.update(
    build_package_configs(
        project_name="ts_ATWhiteLightSource",
        version=lsst.ts.ATWhiteLightSource.version.__version__,
    )
)
