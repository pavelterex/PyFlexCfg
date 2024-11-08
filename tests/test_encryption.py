import pytest
from pytest_assume.plugin import assume

from pyflexcfg.components.encryption import AESCipher

TEST_KEY = '1234'
TEST_STRING = 'some-secret-string'
TEST_ENCRYPTED_BYTES = b'u8euuCiFlgzpI2aY6/vYtJbQ4ApNbqtnwTjYVJ/APs2aRVD8XbC6tiEsmrcKjqXd'
TEST_ENCRYPTED_STRING = 'u8euuCiFlgzpI2aY6/vYtJbQ4ApNbqtnwTjYVJ/APs2aRVD8XbC6tiEsmrcKjqXd'


@pytest.fixture(scope='module')
def aes_cipher() -> AESCipher:
    return AESCipher(TEST_KEY)


def test_encrypt_string(aes_cipher):
    encrypted = aes_cipher.encrypt(TEST_STRING)
    assume(encrypted, 'Encrypted data is empty!')
    assume(isinstance(encrypted, bytes), 'Encrypted data is not bytes type!')


def test_decrypt_bytes(aes_cipher):
    decrypted = aes_cipher.decrypt(TEST_ENCRYPTED_BYTES)
    assert decrypted == TEST_STRING, 'Decrypted string is corrupted!'


def test_decrypt_string(aes_cipher):
    decrypted = aes_cipher.decrypt(TEST_ENCRYPTED_STRING)
    assert decrypted == TEST_STRING, 'Decrypted string is corrupted!'
