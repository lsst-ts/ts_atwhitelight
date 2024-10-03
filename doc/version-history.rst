ts_atwhitelight v0.5.1 (2024-10-03)
===================================

Bugfixes
--------

- Set power to zero before retrying to light bulb. (`DM-45227 <https://rubinobs.atlassian.net/DM-45227>`_)


ts_atwhitelight v0.5.0 (2024-05-31)
===================================

Features
--------

- Add max_retries and retry_sleep to configuration schema and update schema to v4. (`DM-44227 <https://jira.lsstcorp.org/DM-44227>`_)


Bugfixes
--------

- Add a retry_sleep attribute and add it to the boolean check for the unexpectedly off condition so that the CSC will not go to fault too early. (`DM-44227 <https://jira.lsstcorp.org/DM-44227>`_)
- Fix self.retry_sleep to self.config.retry_sleep. (`DM-44423 <https://jira.lsstcorp.org/DM-44423>`_)


ts_atwhitelight v0.4.0 (2024-05-09)
===================================

Features
--------

- Add a retry loop for turning the lamp on. (`DM-42485 <https://jira.lsstcorp.org/DM-42485>`_)


Bugfixes
--------

- Update to ts-conda-build 0.4. (`DM-43481 <https://jira.lsstcorp.org/DM-43481>`_)


Improved Documentation
----------------------

- Add towncrier.toml. (`DM-42485 <https://jira.lsstcorp.org/DM-42485>`_)


ts_atwhitelight 0.4.0 (2024-05-09)
==================================

Features
--------

- Add a retry loop for turning the lamp on. (`DM-42485 <https://jira.lsstcorp.org/DM-42485>`_)


Bugfixes
--------

- Update to ts-conda-build 0.4. (`DM-43481 <https://jira.lsstcorp.org/DM-43481>`_)


Improved Documentation
----------------------

- Add towncrier.toml. (`DM-42485 <https://jira.lsstcorp.org/DM-42485>`_)
