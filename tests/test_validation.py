# This file is part of ts_atwhitelight.
#
# Developed for the LSST Telescope and Site Systems.
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

import copy
import pathlib
import unittest

import jsonschema
import pytest
import yaml

from lsst.ts import atwhitelight
from lsst.ts import salobj

TEST_CONFIG_DIR = pathlib.Path(__file__).parent / "data" / "config"


class ValidationTestCase(unittest.TestCase):
    """Test validation of the config schema."""

    def setUp(self):
        self.schema = atwhitelight.CONFIG_SCHEMA
        self.validator = salobj.StandardValidator(schema=self.schema)
        with open(TEST_CONFIG_DIR / "_init.yaml", "r") as f:
            raw_config = f.read()
        self.init_config = yaml.safe_load(raw_config)
        self.validator.validate(self.init_config)

    def test_added_fields(self):
        bad_config = self.init_config.copy()
        bad_config["no_such_field"] = 5
        with pytest.raises(jsonschema.exceptions.ValidationError):
            self.validator.validate(bad_config)

    def test_added_sub_fields(self):
        bad_config = copy.deepcopy(self.init_config)
        for category in ("chiller", "lamp"):
            bad_config[category]["no_such_field"] = 5
            with pytest.raises(jsonschema.exceptions.ValidationError):
                self.validator.validate(bad_config)

    def test_missing_fields(self):
        for field in self.init_config:
            with self.subTest(field=field):
                bad_config = self.init_config.copy()
                del bad_config[field]
                with pytest.raises(jsonschema.exceptions.ValidationError):
                    self.validator.validate(bad_config)

    def test_missing_sub_fields(self):
        for category in ("chiller", "lamp"):
            for field in self.init_config[category]:
                with self.subTest(category=category, field=field):
                    bad_config = copy.deepcopy(self.init_config)
                    del bad_config[category][field]
                    with pytest.raises(jsonschema.exceptions.ValidationError):
                        self.validator.validate(bad_config)
