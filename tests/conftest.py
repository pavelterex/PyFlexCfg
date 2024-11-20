from pathlib import Path

import pytest

# from pyflexcfg.components.constants import ENCRYPTION_KEY_ENV_VAR, ROOT_CONFIG_PATH_ENV


# @pytest.fixture
# def env_key(monkeypatch):
#     monkeypatch.setenv(ENCRYPTION_KEY_ENV_VAR, '1234')
#
#
# @pytest.fixture(autouse=True)
# def test_config(monkeypatch):
#     monkeypatch.setenv(ROOT_CONFIG_PATH_ENV, str(Path(Path.cwd() / 'tests' / 'test_data' / 'test_config')))
