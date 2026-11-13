"""OntoFoundry 外置基础配置；现场配置写在同目录覆盖文件中。"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

LOCAL_USERS = [{"username": "admin", "password": "admin123"}]
OAUTH_PROVIDERS = []
OAUTH_USER_INFO = None

# Do not swallow import failures inside an existing override file.
if Path(__file__).with_name("ontofoundry_config_docker.py").is_file():
    from ontofoundry_config_docker import *  # noqa: F403

    logger.info("Loaded OntoFoundry configuration override")
else:
    logger.info("Using default OntoFoundry authentication configuration")
