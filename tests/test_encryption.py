import base64
import logging

import pytest
from conftest import TEST_CBC_CIPHERTEXT, TEST_ENCRYPTED_STRING, TEST_KEY, TEST_STRING
from pytest_assume.plugin import assume

from pyflexcfg.components.encryption import AESCipher


@pytest.fixture(scope='module')
def cipher() -> AESCipher:
    return AESCipher(TEST_KEY)


def test_decrypt_accepts_bytes(cipher):
    assert cipher.decrypt(TEST_ENCRYPTED_STRING.encode('ascii')) == TEST_STRING


def test_decrypt_accepts_str(cipher):
    assert cipher.decrypt(TEST_ENCRYPTED_STRING) == TEST_STRING


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
    assert raw[0] == 0x02


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
    assert raw[0] == 0x01


def test_encrypt_returns_str(cipher):
    ct = cipher.encrypt(TEST_STRING)
    assume(bool(ct))
    assume(isinstance(ct, str))


def test_full_length_key_no_warning(caplog):
    with caplog.at_level(logging.WARNING, logger='pyflexcfg'):
        AESCipher('a' * 32)
    assert not caplog.records


def test_legacy_cbc_decrypts_transparently(cipher):
    assert cipher.decrypt(TEST_CBC_CIPHERTEXT) == TEST_STRING


def test_legacy_cbc_warns_to_migrate(cipher, caplog):
    with caplog.at_level(logging.WARNING, logger='pyflexcfg'):
        cipher.decrypt(TEST_CBC_CIPHERTEXT)
    assert any('pyflexcfg encrypt' in r.message for r in caplog.records)


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
