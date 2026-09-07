# Apache Ossie validation assets

The JSON Schemas under assets/vendor/apache-ossie and the baseline validation
logic in validator.py are derived from the repository-local md2ossie skill.

- Specification: Apache Ossie 0.2.0.dev0
- Source commit: 88e0011148283302c9a04cd0287e00e0b9d87354
- License: Apache License 2.0
- Local integration change: schema paths resolve from the packaged
  ontofoundry_api.ossie directory so production has no runtime dependency on
  another repository or a user home path.

The upstream LICENSE and NOTICE are retained beside the vendored schemas.

