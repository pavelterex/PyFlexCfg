import pytest
from pytest_assume.plugin import assume

from conftest import TEST_KEY, TEST_STRING, TEST_ENCRYPTED_STRING, TEST_ENCRYPTED_BYTES
from pyflexcfg.components.encryption import AESCipher


@pytest.fixture(scope='module')
def aes_cipher() -> AESCipher:
    return AESCipher(TEST_KEY)


def test_encrypt_string(aes_cipher):
    encrypted = aes_cipher.encrypt(TEST_STRING)
    assume(encrypted, 'Encrypted data is empty!')
    assume(isinstance(encrypted, bytes), 'Encrypted data is not a bytes type!')


def test_decrypt_bytes(aes_cipher):
    decrypted = aes_cipher.decrypt(TEST_ENCRYPTED_BYTES)
    assert decrypted == TEST_STRING, 'Decrypted string is invalid!'


def test_decrypt_string(aes_cipher):
    decrypted = aes_cipher.decrypt(TEST_ENCRYPTED_STRING)
    assert decrypted == TEST_STRING, 'Decrypted string is invalid!'
