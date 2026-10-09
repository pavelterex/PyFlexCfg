import base64
import hashlib
import logging
import os

import pytest
from conftest import TEST_CBC_CIPHERTEXT, TEST_ENCRYPTED_STRING, TEST_KEY, TEST_STRING
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from pytest_assume.plugin import assume

from pyflexcfg.components.encryption import AESCipher


@pytest.fixture(scope='module')
def cipher() -> AESCipher:
    return AESCipher(TEST_KEY)


def test_decrypt_accepts_bytes(cipher):
    assert cipher.decrypt(TEST_ENCRYPTED_STRING.encode('ascii')) == TEST_STRING


def test_decrypt_accepts_str(cipher):
    assert cipher.decrypt(TEST_ENCRYPTED_STRING) == TEST_STRING


def test_decrypt_unknown_version_raises(cipher):
    ct = base64.b64encode(b'PFLX\x09' + os.urandom(40))

    with pytest.raises(RuntimeError, match='Unknown ciphertext version'):
        cipher.decrypt(ct)


def test_decrypt_unrecognized_format_raises(cipher):
    with pytest.raises(RuntimeError, match='Unrecognized ciphertext format'):
        cipher.decrypt(base64.b64encode(b'neither-format'))


def test_encr_kdf_roundtrip(cipher):
    ct = cipher.encrypt_kdf(TEST_STRING)
    assert cipher.decrypt(ct) == TEST_STRING


def test_encr_kdf_salts_unique(cipher):
    assert cipher.encrypt_kdf(TEST_STRING) != cipher.encrypt_kdf(TEST_STRING)


def test_encr_kdf_tag_in_yaml_decrypts(tmp_path):
    import os

    import yaml

    from pyflexcfg.components.encryption import AESCipher
    from pyflexcfg.components.misc import Secret
    from pyflexcfg.components.yaml_loader import YamlLoader

    os.environ['PYFLEX_CFG_KEY'] = TEST_KEY
    ct = AESCipher(TEST_KEY).encrypt_kdf(TEST_STRING)
    yaml_text = f'secret: !encr_kdf {ct}\n'
    data = yaml.load(yaml_text, YamlLoader)
    assert isinstance(data['secret'], Secret)
    assert str.__eq__(data['secret'], TEST_STRING)


def test_encr_kdf_tamper_raises(cipher):
    raw = bytearray(base64.b64decode(cipher.encrypt_kdf(TEST_STRING)))
    raw[-1] ^= 0xFF
    with pytest.raises(ValueError, match='Decryption failed'):
        cipher.decrypt(base64.b64encode(bytes(raw)))


def test_encr_kdf_version_byte_is_kdf(cipher):
    raw = base64.b64decode(cipher.encrypt_kdf(TEST_STRING))
    assert raw[:5] == b'PFLX\x02', f'unexpected header {raw[:5]!r}'


def test_encr_nonces_unique(cipher):
    assert cipher.encrypt(TEST_STRING) != cipher.encrypt(TEST_STRING)


def test_encr_roundtrip(cipher):
    ct = cipher.encrypt(TEST_STRING)
    assert cipher.decrypt(ct) == TEST_STRING


def test_encr_tag_in_yaml_decrypts(tmp_path):
    import os

    import yaml

    from pyflexcfg.components.misc import Secret
    from pyflexcfg.components.yaml_loader import YamlLoader

    os.environ['PYFLEX_CFG_KEY'] = TEST_KEY
    yaml_text = f'secret: !encr {TEST_ENCRYPTED_STRING}\n'
    data = yaml.load(yaml_text, YamlLoader)
    assert isinstance(data['secret'], Secret)
    assert str.__eq__(data['secret'], TEST_STRING)


def test_encr_tamper_raises(cipher):
    raw = bytearray(base64.b64decode(cipher.encrypt(TEST_STRING)))
    raw[-1] ^= 0xFF
    with pytest.raises(ValueError, match='Decryption failed'):
        cipher.decrypt(base64.b64encode(bytes(raw)))


def test_encr_version_byte_is_fast(cipher):
    raw = base64.b64decode(cipher.encrypt(TEST_STRING))
    assert raw[:5] == b'PFLX\x01', f'unexpected header {raw[:5]!r}'


def test_encrypt_returns_str(cipher):
    ct = cipher.encrypt(TEST_STRING)
    assume(bool(ct))
    assume(isinstance(ct, str))


def test_full_length_key_no_warning(caplog):
    with caplog.at_level(logging.WARNING, logger='pyflexcfg'):
        AESCipher('a' * 32)
    assert not caplog.records


def test_is_encrypted_recognizes_only_current_format(cipher):
    assert AESCipher.is_encrypted(cipher.encrypt(TEST_STRING)), 'fast ciphertext must be recognized'
    assert AESCipher.is_encrypted(cipher.encrypt_kdf(TEST_STRING)), 'KDF ciphertext must be recognized'
    assert not AESCipher.is_encrypted(TEST_CBC_CIPHERTEXT), 'legacy ciphertext is not the current format'
    assert not AESCipher.is_encrypted('plain-text!'), 'non-base64 text is not a ciphertext'


def test_is_kdf_recognizes_only_kdf_ciphertext(cipher):
    assert AESCipher.is_kdf(cipher.encrypt_kdf(TEST_STRING)), 'KDF ciphertext must be recognized'
    assert not AESCipher.is_kdf(cipher.encrypt(TEST_STRING)), 'fast ciphertext is not KDF-encrypted'
    assert not AESCipher.is_kdf(TEST_CBC_CIPHERTEXT), 'legacy ciphertext is not KDF-encrypted'
    assert not AESCipher.is_kdf('plain-text!'), 'non-base64 text is not a ciphertext'


def test_is_legacy_recognizes_only_cbc_shape(cipher):
    assert AESCipher.is_legacy(TEST_CBC_CIPHERTEXT), 'v2 ciphertext must be recognized'
    assert not AESCipher.is_legacy(cipher.encrypt('abc')), 'a 48-byte current-format ciphertext is not legacy'
    assert not AESCipher.is_legacy('plain-text!'), 'non-base64 text is not a ciphertext'


def test_legacy_cbc_decrypts_transparently(cipher):
    assert cipher.decrypt(TEST_CBC_CIPHERTEXT) == TEST_STRING


@pytest.mark.parametrize('first_iv_byte', [b'\x01', b'\x02', b'P'])
def test_legacy_cbc_iv_resembling_a_version_byte_decrypts(cipher, first_iv_byte):
    ct = _cbc_encrypt(TEST_STRING, first_iv_byte + os.urandom(15))

    assert cipher.decrypt(ct) == TEST_STRING, f'IV starting with {first_iv_byte!r} was misrouted'


def test_legacy_cbc_warns_to_migrate(cipher, caplog):
    with caplog.at_level(logging.WARNING, logger='pyflexcfg'):
        cipher.decrypt(TEST_CBC_CIPHERTEXT)
    assert any('pyflexcfg encrypt' in r.message for r in caplog.records)


def test_legacy_cbc_wrong_key_does_not_warn_of_success(caplog):
    with caplog.at_level(logging.WARNING, logger='pyflexcfg'), pytest.raises(ValueError, match='Decryption failed'):
        AESCipher('not-the-key').decrypt(TEST_CBC_CIPHERTEXT)

    assert not any('decrypted successfully' in r.message for r in caplog.records), (
        'a failed legacy decrypt must not log a success warning'
    )


def test_legacy_cbc_wrong_key_raises():
    with pytest.raises(ValueError, match='Decryption failed'):
        AESCipher('not-the-key').decrypt(TEST_CBC_CIPHERTEXT)


def test_missing_key_env_var_raises(monkeypatch):
    import yaml

    from pyflexcfg.components.yaml_loader import YamlLoader

    monkeypatch.delenv('PYFLEX_CFG_KEY', raising=False)
    # cipher is per-instance, so a fresh yaml.load() call triggers the missing-key check
    with pytest.raises(RuntimeError, match='PYFLEX_CFG_KEY'):
        yaml.load('secret: !encr somevalue\n', YamlLoader)


def test_short_key_logs_warning(caplog):
    with caplog.at_level(logging.WARNING, logger='pyflexcfg'):
        AESCipher('short')
    assert any('shorter than' in r.message for r in caplog.records)


def _cbc_encrypt(plaintext: str, iv: bytes) -> str:
    """Build a v2-style ciphertext: base64 of iv + AES-CBC(PKCS7(plaintext))."""
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext.encode('utf-8')) + padder.finalize()
    encryptor = Cipher(algorithms.AES(hashlib.sha256(TEST_KEY.encode('utf-8')).digest()), modes.CBC(iv)).encryptor()
    return base64.b64encode(iv + encryptor.update(padded) + encryptor.finalize()).decode('ascii')
