"""Verify that secret values never surface in logs, repr, or error messages."""

import copy
import logging
import pickle
import traceback

import pytest
from conftest import TEST_CBC_CIPHERTEXT, TEST_KEY, TEST_STRING

from pyflexcfg import Cfg
from pyflexcfg.components.encryption import AESCipher
from pyflexcfg.components.misc import AttrDict, Required, Secret

NEEDLE = 'hunter2'


def test_cfg_str_masks_secrets_in_nested_collections():
    secret = Secret(NEEDLE)
    Cfg.leaktest = AttrDict({'items': [secret, {'inner': secret}], 'pair': (secret,), secret: 'secret as a key'})
    try:
        dumped = str(Cfg)
    finally:
        del Cfg.leaktest

    assert 'leaktest' in dumped, f'the section must be rendered, got {dumped!r}'
    assert NEEDLE not in dumped, 'a Secret nested in a list, dict, tuple or used as a key leaked into str(Cfg)'


def test_decrypt_failure_omits_key_and_plaintext():
    passphrase = 'wrong-passphrase-xyz'
    ciphertext = AESCipher(TEST_KEY).encrypt(TEST_STRING)

    with pytest.raises(ValueError, match='Decryption failed') as exc_info:
        AESCipher(passphrase).decrypt(ciphertext)
    rendered = ''.join(traceback.format_exception(exc_info.value))

    assert passphrase not in rendered, 'the passphrase leaked into the decryption error'
    assert TEST_STRING not in rendered, 'the plaintext leaked into the decryption error'


def test_legacy_cbc_warning_omits_plaintext(caplog):
    cipher = AESCipher(TEST_KEY)
    with caplog.at_level(logging.WARNING, logger='pyflexcfg'):
        result = cipher.decrypt(TEST_CBC_CIPHERTEXT)
    assert TEST_STRING not in caplog.text
    assert result == TEST_STRING


@pytest.mark.parametrize(
    'content',
    [
        pytest.param(f'password: "{NEEDLE}\n', id='unterminated quote'),
        pytest.param(f'password: !nosuchtag {NEEDLE}\n', id='unknown tag'),
        pytest.param(f'a:\n  b: 1\n c: {NEEDLE}\n', id='bad indentation'),
        pytest.param(f'password: !encr {NEEDLE}\n', id='plaintext under !encr'),
        pytest.param(f'password: !encr {NEEDLE}x\n', id='base64-looking plaintext under !encr'),
    ],
)
def test_load_error_omits_file_content(tmp_path, caplog, content):
    (tmp_path / 'app.yaml').write_text(content, encoding='utf-8')

    with caplog.at_level(logging.DEBUG, logger='pyflexcfg'), pytest.raises(Exception) as exc_info:  # noqa: PT011
        Cfg.reload_config(config_path=tmp_path)
    rendered = ''.join(traceback.format_exception(exc_info.value)) + caplog.text

    assert NEEDLE not in rendered, 'config file content leaked into a load error or log'


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


@pytest.mark.parametrize('convert', [int, float], ids=['int', 'float'])
def test_secret_masked_in_conversion_errors(convert):
    with pytest.raises(ValueError, match='invalid literal|could not convert') as exc_info:
        convert(Secret(NEEDLE))

    assert NEEDLE not in str(exc_info.value), f'{convert.__name__}() quoted the secret in its error'


@pytest.mark.parametrize(
    'render',
    [
        pytest.param(lambda s: '%r' % s, id='percent r'),  # noqa: UP031
        pytest.param(lambda s: '%s' % s, id='percent s'),  # noqa: UP031
        pytest.param('{}'.format, id='str.format'),
        pytest.param('{!s:>12}'.format, id='str.format with conversion and spec'),
        pytest.param(lambda s: f'{s!r}', id='f-string repr'),
        pytest.param(lambda s: format(s, '^20'), id='format builtin'),
        pytest.param(lambda s: str(ValueError('bad value', s)), id='exception argument'),
    ],
)
def test_secret_masked_in_format_variants(render):
    assert NEEDLE not in render(Secret(NEEDLE)), 'a formatting path revealed the secret'


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


@pytest.mark.parametrize(
    'duplicate',
    [
        pytest.param(copy.copy, id='copy'),
        pytest.param(copy.deepcopy, id='deepcopy'),
        pytest.param(lambda value: pickle.loads(pickle.dumps(value)), id='pickle'),
        pytest.param(lambda value: value.as_dict(), id='as_dict'),
    ],
)
def test_secret_stays_masked_after_copying(duplicate):
    duplicated = duplicate(AttrDict({'key': Secret(NEEDLE), 'nested': AttrDict({'key': Secret(NEEDLE)})}))

    assert NEEDLE not in repr(duplicated), 'the copy lost its masking'
    assert duplicated['nested']['key'] == NEEDLE, 'the copy must still hold the real value'


def test_short_key_warning_omits_passphrase(caplog):
    passphrase = 'weakkey123'
    with caplog.at_level(logging.WARNING, logger='pyflexcfg'):
        AESCipher(passphrase)
    assert passphrase not in caplog.text


@pytest.mark.parametrize(
    'raw',
    [
        pytest.param('hunter2::int', id='int'),
        pytest.param('hunter2::float', id='float'),
        pytest.param('hunter2::bool', id='bool'),
        pytest.param('hunter2: [unclosed::yaml_r', id='yaml'),
    ],
)
def test_update_from_env_cast_failure_omits_value(monkeypatch, raw):
    monkeypatch.setenv('CFG__APP__GENERAL__VAR_STR', raw)

    with pytest.raises(RuntimeError) as exc_info:
        Cfg.update_from_env()
    rendered = ''.join(traceback.format_exception(exc_info.value))

    assert 'hunter2' not in rendered, 'the raw value leaked into the error or its traceback'
    assert 'CFG__APP__GENERAL__VAR_STR' in str(exc_info.value), 'the error must name the offending variable'


def test_update_from_env_secret_suffix_not_in_debug_log(monkeypatch, caplog):
    monkeypatch.setenv('CFG__APP__GENERAL__VAR_STR', 'hunter2::Secret')
    with caplog.at_level(logging.DEBUG, logger='pyflexcfg'):
        Cfg.update_from_env()
    assert 'hunter2' not in caplog.text


@pytest.mark.parametrize('existing', [NEEDLE, f'[{NEEDLE}, other]'], ids=['scalar', 'list'])
def test_update_from_env_unassignable_path_omits_existing_value(monkeypatch, tmp_path, caplog, existing):
    # The override path runs through a value that cannot hold attributes; the skip is logged.
    (tmp_path / 'app.yaml').write_text(f'general:\n  password: {existing}\n', encoding='utf-8')
    monkeypatch.setenv('CFG__APP__GENERAL__PASSWORD__SUB', 'anything')

    with caplog.at_level(logging.DEBUG, logger='pyflexcfg'):
        Cfg.reload_config(config_path=tmp_path)

    assert 'CFG__APP__GENERAL__PASSWORD__SUB' in caplog.text, 'the skipped override must still be logged'
    assert NEEDLE not in caplog.text, 'the existing config value leaked into the skip log'


@pytest.mark.parametrize(
    'raw',
    [
        pytest.param('hunter2::nosuchtype', id='secret before the separator'),
        pytest.param('abc::hunter2', id='secret after the separator'),
        pytest.param('hunter2::hunter2', id='secret on both sides'),
    ],
)
def test_update_from_env_unknown_type_does_not_log_value(monkeypatch, caplog, raw):
    # Either side of `::` may be part of a secret, so neither may reach the log.
    monkeypatch.setenv('CFG__APP__GENERAL__VAR_STR', raw)
    with caplog.at_level(logging.DEBUG, logger='pyflexcfg'):
        Cfg.update_from_env()

    assert 'hunter2' not in caplog.text, 'part of the raw value leaked into the debug log'
    assert 'CFG__APP__GENERAL__VAR_STR' in caplog.text, 'the fallback must still be logged, naming the variable'


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
