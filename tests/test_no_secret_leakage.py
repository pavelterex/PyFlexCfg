"""Verify that secret values never surface in logs, repr, or error messages."""

import logging

import pytest
from conftest import TEST_CBC_CIPHERTEXT, TEST_KEY, TEST_STRING

from pyflexcfg import Cfg
from pyflexcfg.components.encryption import AESCipher
from pyflexcfg.components.misc import AttrDict, Required, Secret


def test_legacy_cbc_warning_omits_plaintext(caplog):
    cipher = AESCipher(TEST_KEY)
    with caplog.at_level(logging.WARNING, logger='pyflexcfg'):
        result = cipher.decrypt(TEST_CBC_CIPHERTEXT)
    assert TEST_STRING not in caplog.text
    assert result == TEST_STRING


def test_secret_masked_as_log_percent_arg(caplog):
    logger = logging.getLogger('test.leakage')
    secret = Secret('my-password')
    with caplog.at_level(logging.DEBUG, logger='test.leakage'):
        logger.debug('value is %s', secret)
    assert 'my-password' not in caplog.text
    assert '********' in caplog.text


def test_secret_masked_in_attrdict_repr():
    d = AttrDict({'key': Secret('hunter2')})
    assert 'hunter2' not in repr(d)
    assert '********' in repr(d)


def test_secret_masked_in_attrdict_str():
    d = AttrDict({'key': Secret('hunter2')})
    assert 'hunter2' not in str(d)


def test_secret_masked_in_log_f_string(caplog):
    logger = logging.getLogger('test.leakage')
    secret = Secret('my-password')
    with caplog.at_level(logging.DEBUG, logger='test.leakage'):
        logger.debug(f'value is {secret}')
    assert 'my-password' not in caplog.text
    assert '********' in caplog.text


def test_secret_masked_in_nested_attrdict_repr():
    inner = AttrDict({'password': Secret('topsecret')})
    outer = AttrDict({'db': inner})
    assert 'topsecret' not in repr(outer)


def test_short_key_warning_omits_passphrase(caplog):
    passphrase = 'weakkey123'
    with caplog.at_level(logging.WARNING, logger='pyflexcfg'):
        AESCipher(passphrase)
    assert passphrase not in caplog.text


def test_update_from_env_secret_suffix_not_in_debug_log(monkeypatch, caplog):
    monkeypatch.setenv('CFG__APP__GENERAL__VAR_STR', 'hunter2::Secret')
    with caplog.at_level(logging.DEBUG, logger='pyflexcfg'):
        Cfg.update_from_env()
    assert 'hunter2' not in caplog.text


def test_update_from_env_unknown_type_does_not_log_value(monkeypatch, caplog):
    # An unknown ::type suffix must log only the type name, not the value before `::`.
    monkeypatch.setenv('CFG__APP__GENERAL__VAR_STR', 'hunter2::nosuchtype')
    with caplog.at_level(logging.DEBUG, logger='pyflexcfg'):
        Cfg.update_from_env()
    assert 'hunter2' not in caplog.text


def test_validate_required_error_lists_paths_not_sibling_values():
    section = AttrDict({'host': Required(), 'port': 5432})
    Cfg.leaktest = section
    try:
        with pytest.raises(RuntimeError) as exc_info:
            Cfg.validate_required()
        error_msg = str(exc_info.value)
        assert 'leaktest.host' in error_msg
        assert '5432' not in error_msg
    finally:
        if hasattr(Cfg, 'leaktest'):
            delattr(Cfg, 'leaktest')
