import os

from pyflexcfg.components.constants import ENCRYPTION_KEY_ENV_VAR

TEST_KEY = os.getenv(ENCRYPTION_KEY_ENV_VAR)
TEST_STRING = 'some-secret-string'
TEST_ENCRYPTED_BYTES = b'u8euuCiFlgzpI2aY6/vYtJbQ4ApNbqtnwTjYVJ/APs2aRVD8XbC6tiEsmrcKjqXd'
TEST_ENCRYPTED_STRING = 'u8euuCiFlgzpI2aY6/vYtJbQ4ApNbqtnwTjYVJ/APs2aRVD8XbC6tiEsmrcKjqXd'
