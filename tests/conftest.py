"""
Test bootstrap.

Sets ``PYFLEX_CFG_ROOT_PATH`` to ``tests/test_data`` *before* any ``pyflexcfg``
import so the metaclass has a valid directory to walk at import time.
"""

import os
from pathlib import Path

os.environ.setdefault('PYFLEX_CFG_ROOT_PATH', str(Path(__file__).parent / 'test_data'))

import pytest  # noqa: E402

from pyflexcfg.components.constants import ENCRYPTION_KEY_ENV_VAR  # noqa: E402


@pytest.fixture()
def env_key(monkeypatch):
    monkeypatch.setenv(ENCRYPTION_KEY_ENV_VAR, '1234')
