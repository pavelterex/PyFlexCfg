"""Tests for ``Cfg.update_from_env`` — type coercion, dotted-path walk, safety."""

import logging
from pathlib import Path
from textwrap import dedent

import pytest

from pyflexcfg import Cfg
from pyflexcfg.components.misc import Secret


@pytest.fixture
def loaded_cfg(tmp_path: Path):
    """Build a small config tree in tmp_path and load it into Cfg."""
    (tmp_path / 'general.yaml').write_text(
        dedent("""
            host: localhost
            port: 5432
            debug: false
            nested:
              a: 1
              b: 2
        """).strip()
    )
    (tmp_path / 'env').mkdir()
    (tmp_path / 'env' / 'dev.yaml').write_text('region: us-east-1\n')
    Cfg.reload_config(tmp_path)

    yield Cfg


def test_bool_auto_coercion(loaded_cfg, monkeypatch):
    monkeypatch.setenv('CFG__GENERAL__DEBUG', 'true')
    loaded_cfg.update_from_env()

    assert loaded_cfg.general.debug is True, f'expected True, got {loaded_cfg.general.debug!r}'


def test_explicit_secret_cast(loaded_cfg, monkeypatch):
    monkeypatch.setenv('CFG__GENERAL__HOST', 'mypassword::Secret')
    loaded_cfg.update_from_env()

    assert isinstance(loaded_cfg.general.host, Secret), 'host must be wrapped as Secret'
    assert str(loaded_cfg.general.host) == '********', 'Secret must mask on str()'


def test_explicit_str_cast(loaded_cfg, monkeypatch):
    monkeypatch.setenv('CFG__GENERAL__PORT', '8080::str')
    loaded_cfg.update_from_env()

    assert loaded_cfg.general.port == '8080', f'expected str, got {loaded_cfg.general.port!r}'
    assert isinstance(loaded_cfg.general.port, str), f'expected str, got {type(loaded_cfg.general.port).__name__}'


def test_injection_attempt_stored_as_literal_string(loaded_cfg, monkeypatch):
    """Regression: the original implementation used ``exec()`` on env values.

    Any string with shell-like metacharacters must be stored verbatim as a value,
    never evaluated. If the new impl ever regresses to using ``exec``/``eval``,
    this test will fail (either with crash or by storing a coerced object).
    """
    payload = '"; __import__("os").system("echo OWNED"); "'
    monkeypatch.setenv('CFG__GENERAL__HOST', payload)
    loaded_cfg.update_from_env()

    assert loaded_cfg.general.host == payload, f'value must be stored verbatim, got {loaded_cfg.general.host!r}'


def test_int_auto_coercion(loaded_cfg, monkeypatch):
    monkeypatch.setenv('CFG__GENERAL__PORT', '9999')
    loaded_cfg.update_from_env()

    assert loaded_cfg.general.port == 9999, f'expected int 9999, got {loaded_cfg.general.port!r}'
    assert isinstance(loaded_cfg.general.port, int), f'expected int, got {type(loaded_cfg.general.port).__name__}'


def test_missing_intermediate_path_logs_and_skips(loaded_cfg, monkeypatch, caplog):
    monkeypatch.setenv('CFG__NOSUCH__SECTION__KEY', 'value')

    with caplog.at_level(logging.DEBUG, logger='pyflexcfg'):
        loaded_cfg.update_from_env()

    assert any('NOSUCH' in r.message.upper() for r in caplog.records), 'missing-path event must be logged'


def test_non_cfg_env_vars_ignored(loaded_cfg, monkeypatch):
    original = loaded_cfg.general.port
    monkeypatch.setenv('OTHER_VAR', 'should be ignored')
    monkeypatch.setenv('PATH_LIKE_THING', 'no')
    loaded_cfg.update_from_env()

    assert loaded_cfg.general.port == original, 'non-CFG env vars must not touch config'


def test_quotes_in_value_do_not_break_parsing(loaded_cfg, monkeypatch):
    monkeypatch.setenv('CFG__GENERAL__HOST', 'it\'s "fine" now')
    loaded_cfg.update_from_env()

    assert loaded_cfg.general.host == 'it\'s "fine" now', f'got {loaded_cfg.general.host!r}'


def test_string_override(loaded_cfg, monkeypatch):
    monkeypatch.setenv('CFG__GENERAL__HOST', 'remote.example.com')
    loaded_cfg.update_from_env()

    assert loaded_cfg.general.host == 'remote.example.com', f'got {loaded_cfg.general.host!r}'


def test_unknown_yaml_suffix_falls_back_to_auto_coercion(loaded_cfg, monkeypatch):
    """A bare ``::yaml`` (no _m/_r) is no longer a known suffix; the value falls through to autodetect."""
    monkeypatch.setenv('CFG__GENERAL__HOST', '42::yaml')
    loaded_cfg.update_from_env()

    assert loaded_cfg.general.host == 42, f'unknown suffix should drop and auto-coerce, got {loaded_cfg.general.host!r}'


def test_yaml_m_cast_merges_dict_into_existing(loaded_cfg, monkeypatch):
    monkeypatch.setenv('CFG__GENERAL__NESTED', '{c: 3, a: 99}::yaml_m')
    loaded_cfg.update_from_env()

    # Existing keys (a, b) preserved unless overridden; new keys (c) added.
    assert loaded_cfg.general.nested.a == 99, f'a must be overridden, got {loaded_cfg.general.nested.a!r}'
    assert loaded_cfg.general.nested.b == 2, f'b must persist, got {loaded_cfg.general.nested.b!r}'
    assert loaded_cfg.general.nested.c == 3, f'c must be added, got {loaded_cfg.general.nested.c!r}'


def test_yaml_r_cast_produces_list(loaded_cfg, monkeypatch):
    monkeypatch.setenv('CFG__GENERAL__HOST', '[a, b, c]::yaml_r')
    loaded_cfg.update_from_env()

    assert loaded_cfg.general.host == ['a', 'b', 'c'], f'expected list, got {loaded_cfg.general.host!r}'


def test_yaml_r_cast_replaces_dict_wholesale(loaded_cfg, monkeypatch):
    monkeypatch.setenv('CFG__GENERAL__NESTED', '{only: here}::yaml_r')
    loaded_cfg.update_from_env()
    # Pre-existing keys (a, b) must be gone because yaml_r replaces wholesale.
    nested = dict(loaded_cfg.general.nested)

    assert nested == {'only': 'here'}, f'expected full replace, got {nested!r}'
