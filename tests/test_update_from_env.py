import logging
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath
from textwrap import dedent

import pytest

from pyflexcfg import Cfg
from pyflexcfg.components.misc import Secret

_DICT_METHOD_KEYS_YAML = 'items:\n  size: 1\nkeys:\n  copy:\n    size: 1\nvalues: 3\n'


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
        """).strip(),
    )
    (tmp_path / 'env').mkdir()
    (tmp_path / 'env' / 'dev.yaml').write_text('region: us-east-1\n')
    Cfg.reload_config(config_path=tmp_path)

    return Cfg


def test_bool_auto_coercion(loaded_cfg, monkeypatch):
    monkeypatch.setenv('CFG__GENERAL__DEBUG', 'true')
    loaded_cfg.update_from_env()

    assert loaded_cfg.general.debug is True, f'expected True, got {loaded_cfg.general.debug!r}'


@pytest.mark.parametrize(
    'raw, expected',
    [
        pytest.param('cache/app::home_dir', Path(Path.home(), 'cache', 'app'), id='home_dir'),
        pytest.param('/var/log/app.log::path', Path('/var/log/app.log'), id='path'),
        pytest.param('/var/log/app.log::path_posix', PurePosixPath('/var/log/app.log'), id='path_posix'),
        pytest.param(r'C:\logs\app.log::path_win', PureWindowsPath(r'C:\logs\app.log'), id='path_win'),
        pytest.param('logs/app.log::pure_path', PurePath('logs', 'app.log'), id='pure_path'),
        pytest.param('/var/log/app.log::pure_path_posix', PurePosixPath('/var/log/app.log'), id='pure_path_posix'),
        pytest.param(r'C:\logs\app.log::pure_path_win', PureWindowsPath(r'C:\logs\app.log'), id='pure_path_win'),
    ],
)
def test_explicit_path_casts(loaded_cfg, monkeypatch, raw, expected):
    monkeypatch.setenv('CFG__GENERAL__HOST', raw)
    loaded_cfg.update_from_env()
    result = loaded_cfg.general.host

    assert type(result) is type(expected), f'expected {type(expected).__name__}, got {type(result).__name__}'
    assert result == expected, f'got {result!r}'
    assert str(loaded_cfg), 'a path override must still render in str(Cfg)'


def test_explicit_proj_root_cast(tmp_path, monkeypatch):
    (tmp_path / 'general.yaml').write_text('log_file: placeholder\n', encoding='utf-8')
    monkeypatch.setenv('CFG__GENERAL__LOG_FILE', 'logs/app.log::proj_root')

    Cfg.reload_config(config_path=tmp_path, project_root=tmp_path.parent)

    assert Cfg.general.log_file == Path(tmp_path.parent, 'logs', 'app.log'), f'got {Cfg.general.log_file!r}'
    assert isinstance(Cfg.general.log_file, Path), f'expected a Path, got {type(Cfg.general.log_file).__name__}'


def test_explicit_proj_root_cast_without_project_root_raises(tmp_path, monkeypatch):
    (tmp_path / 'general.yaml').write_text('log_file: placeholder\n', encoding='utf-8')
    monkeypatch.setenv('PYFLEX_CFG_ROOT_PATH', str(tmp_path))
    monkeypatch.delenv('PYFLEX_PROJECT_ROOT_PATH', raising=False)
    monkeypatch.setenv('CFG__GENERAL__LOG_FILE', 'logs/app.log::proj_root')

    with pytest.raises(RuntimeError, match='PYFLEX_PROJECT_ROOT_PATH') as exc_info:
        Cfg.reload_config(config_path=tmp_path)

    assert 'CFG__GENERAL__LOG_FILE' in str(exc_info.value), f'the error must name the variable, got {exc_info.value}'


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
    """
    Regression: the original implementation used `exec()` on env values.

    Any string with shell-like metacharacters must be stored verbatim as a value,
    never evaluated. If the new impl ever regresses to using `exec`/`eval`,
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


def test_layer_definition_override_still_allowed(loaded_cfg, monkeypatch):
    monkeypatch.setenv('CFG__ENV__DEV__REGION', 'eu-west-1')
    loaded_cfg.update_from_env()

    assert loaded_cfg.env.dev.region == 'eu-west-1', 'paths under the env namespace must stay overridable'


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


def test_override_ambiguous_case_variants_raise(tmp_path, monkeypatch):
    (tmp_path / 'app.yaml').write_text('Host: first\nHOST: second\n', encoding='utf-8')
    monkeypatch.setenv('CFG__APP__HOST', 'new')

    with pytest.raises(RuntimeError, match='several keys') as exc_info:
        Cfg.reload_config(config_path=tmp_path)
    msg = str(exc_info.value)

    assert 'CFG__APP__HOST' in msg, f'the error must name the variable, got {msg!r}'
    assert 'Host' in msg, f'the error must list the candidate keys, got {msg!r}'
    assert 'HOST' in msg, f'the error must list the candidate keys, got {msg!r}'


def test_override_cannot_address_hyphenated_key(tmp_path, monkeypatch):
    (tmp_path / 'app.yaml').write_text('my-key: original\n', encoding='utf-8')
    monkeypatch.setenv('CFG__APP__MY_KEY', 'new')

    Cfg.reload_config(config_path=tmp_path)

    assert Cfg.app['my-key'] == 'original', 'a hyphenated key is not addressable from a variable name'


def test_override_matches_keys_case_insensitively(tmp_path, monkeypatch):
    (tmp_path / 'app.yaml').write_text('Host: orig\napiKey: orig\nDB:\n  Port: 1\nlower: orig\n', encoding='utf-8')
    monkeypatch.setenv('CFG__APP__HOST', 'new-host')
    monkeypatch.setenv('CFG__APP__APIKEY', 'new-key')
    monkeypatch.setenv('CFG__APP__DB__PORT', '5433')
    monkeypatch.setenv('CFG__APP__DB', '{Name: main}::yaml_m')

    Cfg.reload_config(config_path=tmp_path)
    expected = {'Host': 'new-host', 'apiKey': 'new-key', 'DB': {'Port': 5433, 'Name': 'main'}, 'lower': 'orig'}

    assert Cfg.app == expected, f'overrides must update the existing keys and add no stray ones: {dict(Cfg.app)!r}'


def test_override_new_leaf_created_lowercase(loaded_cfg, monkeypatch):
    monkeypatch.setenv('CFG__GENERAL__BRAND_NEW', 'added')
    loaded_cfg.update_from_env()

    assert loaded_cfg.general.brand_new == 'added', 'an override for a key that does not exist creates it, lowercase'


def test_override_prefers_exact_key_over_case_variant(tmp_path, monkeypatch):
    (tmp_path / 'app.yaml').write_text('host: lower\nHost: capitalised\n', encoding='utf-8')
    monkeypatch.setenv('CFG__APP__HOST', 'new')

    Cfg.reload_config(config_path=tmp_path)

    assert Cfg.app == {'host': 'new', 'Host': 'capitalised'}, f'the exact lowercase key must win: {dict(Cfg.app)!r}'


def test_override_root_level_key_matched_case_insensitively(tmp_path, monkeypatch):
    (tmp_path / 'env').mkdir()
    (tmp_path / 'app.yaml').write_text('host: base\n', encoding='utf-8')
    (tmp_path / 'env' / 'dev.yaml').write_text('LogLevel: debug\n', encoding='utf-8')
    monkeypatch.setenv('PYFLEX_ENV', 'dev')
    monkeypatch.setenv('CFG__LOGLEVEL', 'info')

    Cfg.reload_config(config_path=tmp_path)

    assert Cfg.LogLevel == 'info', f'the root-level key must be updated in place, got {Cfg.LogLevel!r}'
    assert not hasattr(Cfg, 'loglevel'), 'a stray lowercase key was created at the root'


def test_override_through_keys_named_like_dict_methods(tmp_path, monkeypatch):
    (tmp_path / 'app.yaml').write_text(_DICT_METHOD_KEYS_YAML, encoding='utf-8')
    monkeypatch.setenv('CFG__APP__ITEMS__SIZE', '5')
    monkeypatch.setenv('CFG__APP__KEYS__COPY__SIZE', '6')
    monkeypatch.setenv('CFG__APP__VALUES', '7')

    Cfg.reload_config(config_path=tmp_path)

    assert Cfg.app['items']['size'] == 5, 'an override path through a key named "items" was ignored'
    assert Cfg.app['keys']['copy']['size'] == 6, 'an override path through keys named "keys" and "copy" was ignored'
    assert Cfg.app['values'] == 7, 'an override of a leaf named "values" was ignored'


def test_quotes_in_value_do_not_break_parsing(loaded_cfg, monkeypatch):
    monkeypatch.setenv('CFG__GENERAL__HOST', 'it\'s "fine" now')
    loaded_cfg.update_from_env()

    assert loaded_cfg.general.host == 'it\'s "fine" now', f'got {loaded_cfg.general.host!r}'


@pytest.mark.parametrize(
    'name',
    [
        'CFG__VALIDATE_REQUIRED',
        'CFG__RELOAD_CONFIG',
        'CFG__UPDATE_FROM_ENV__X',
        'CFG__CONFIG_ROOT',
        'CFG___HANDLER_ATTRS',
    ],
)
def test_reserved_top_level_override_rejected(loaded_cfg, monkeypatch, name):
    monkeypatch.setenv(name, 'oops')

    with pytest.raises(RuntimeError, match='reserved') as exc_info:
        loaded_cfg.update_from_env()

    assert name in str(exc_info.value), f'the error must name the variable, got {exc_info.value}'
    for method in ('reload_config', 'update_from_env', 'validate_required'):
        assert callable(getattr(loaded_cfg, method)), f'{method} was replaced by an override'
    assert isinstance(loaded_cfg.config_root, Path), 'config_root was replaced by an override'


def test_string_override(loaded_cfg, monkeypatch):
    monkeypatch.setenv('CFG__GENERAL__HOST', 'remote.example.com')
    loaded_cfg.update_from_env()

    assert loaded_cfg.general.host == 'remote.example.com', f'got {loaded_cfg.general.host!r}'


def test_top_level_override_dropped_on_reload_after_var_removed(loaded_cfg, monkeypatch):
    monkeypatch.setenv('CFG__ADHOC', 'temporary')
    loaded_cfg.update_from_env()
    assert loaded_cfg.adhoc == 'temporary', 'top-level override must be applied first'

    monkeypatch.delenv('CFG__ADHOC')
    loaded_cfg.reload_config()

    assert not hasattr(loaded_cfg, 'adhoc'), 'top-level override survived a reload without its env var'
    assert loaded_cfg.general.host == 'localhost', 'file-backed config must be reloaded'


def test_unknown_yaml_suffix_falls_back_to_auto_coercion(loaded_cfg, monkeypatch):
    """Bare ::yaml is no longer a known suffix; value falls through to autodetect."""
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


def test_yaml_m_merges_into_key_named_like_dict_method(tmp_path, monkeypatch):
    (tmp_path / 'app.yaml').write_text(_DICT_METHOD_KEYS_YAML, encoding='utf-8')
    monkeypatch.setenv('CFG__APP__ITEMS', '{extra: 9}::yaml_m')

    Cfg.reload_config(config_path=tmp_path)

    assert Cfg.app['items'] == {'size': 1, 'extra': 9}, f'yaml_m must merge, not replace: {Cfg.app["items"]!r}'


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
