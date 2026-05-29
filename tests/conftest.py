"""
Sets `PYFLEX_CFG_ROOT_PATH` and `PYFLEX_CFG_KEY` *before* any `pyflexcfg`
import so the metaclass loads cleanly and `!encr` values can be decrypted.
"""

import os
from pathlib import Path

TEST_KEY = '1234'
TEST_STRING = 'some-secret-string'
TEST_ENCRYPTED_BYTES = b'u8euuCiFlgzpI2aY6/vYtJbQ4ApNbqtnwTjYVJ/APs2aRVD8XbC6tiEsmrcKjqXd'
TEST_ENCRYPTED_STRING = 'u8euuCiFlgzpI2aY6/vYtJbQ4ApNbqtnwTjYVJ/APs2aRVD8XbC6tiEsmrcKjqXd'

_TEST_CONFIG_DIR = Path(__file__).parent / 'test_data' / 'test_config'

os.environ.setdefault('PYFLEX_CFG_ROOT_PATH', str(_TEST_CONFIG_DIR))
os.environ.setdefault('PYFLEX_CFG_KEY', TEST_KEY)

import pytest  # noqa: E402

from pyflexcfg import Cfg  # noqa: E402
from pyflexcfg.components.constants import ENCRYPTION_KEY_ENV_VAR  # noqa: E402


@pytest.fixture(autouse=True)
def _restore_cfg_after_test():
    """Reload Cfg from the main test config after every test that mutated its state."""
    yield

    if Cfg.config_root != _TEST_CONFIG_DIR:
        Cfg.reload_config(config_path=_TEST_CONFIG_DIR)


@pytest.fixture
def env_key(monkeypatch):
    monkeypatch.setenv(ENCRYPTION_KEY_ENV_VAR, TEST_KEY)
