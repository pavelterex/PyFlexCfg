import pytest
from conftest import TEST_ENCRYPTED_BYTES, TEST_ENCRYPTED_STRING, TEST_KEY, TEST_STRING
from pytest_assume.plugin import assume

from pyflexcfg.components.encryption import AESCipher


@pytest.fixture(scope='module')
def aes_cipher() -> AESCipher:
    return AESCipher(TEST_KEY)


def test_decrypt_accepts_bytes(aes_cipher):
    decrypted = aes_cipher.decrypt(TEST_ENCRYPTED_BYTES)

    assert decrypted == TEST_STRING, f'Expected {TEST_STRING!r}, got {decrypted!r}'


def test_decrypt_accepts_str(aes_cipher):
    decrypted = aes_cipher.decrypt(TEST_ENCRYPTED_STRING)

    assert decrypted == TEST_STRING, f'Expected {TEST_STRING!r}, got {decrypted!r}'


def test_encrypt_decrypt_round_trip(aes_cipher):
    encrypted = aes_cipher.encrypt(TEST_STRING)
    decrypted = aes_cipher.decrypt(encrypted)

    assert decrypted == TEST_STRING, f'Round-trip failed: {decrypted!r}'


def test_encrypt_returns_str(aes_cipher):
    encrypted = aes_cipher.encrypt(TEST_STRING)

    assume(encrypted, 'Encrypted data is empty!')
    assume(isinstance(encrypted, str), 'Encrypted data must be a str!')
