import pytest

from pyflexcfg.components.constants import ENCRYPTION_KEY_ENV_VAR


@pytest.fixture()
def env_key(monkeypatch):
    monkeypatch.setenv(ENCRYPTION_KEY_ENV_VAR, '1234')
