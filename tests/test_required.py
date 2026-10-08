"""Tests for !required tag and validate_required() (Feature 2)."""

from pathlib import Path

import pytest

from pyflexcfg import Cfg
from pyflexcfg.components.misc import Required

_BASE_CONFIG = Path(__file__).parent / 'test_data' / 'test_config'
_REQUIRED_CONFIG = Path(__file__).parent / 'test_data' / 'required_config'
_SEQUENCE_YAML = 'hosts:\n  - host-a\n  - !required\nservers:\n  - name: primary\n    host: !required\n'


def test_required_error_names_dotted_path(monkeypatch):
    with pytest.raises(RuntimeError) as exc_info:
        _load_required(monkeypatch)
    msg = str(exc_info.value)
    assert 'server.host' in msg or 'database.host' in msg


def test_required_in_sequence_reported_with_index(tmp_path):
    (tmp_path / 'app.yaml').write_text(_SEQUENCE_YAML, encoding='utf-8')

    with pytest.raises(RuntimeError) as exc_info:
        Cfg.reload_config(config_path=tmp_path)
    msg = str(exc_info.value)

    assert 'app.hosts[1]' in msg, f'sentinel inside a list must be reported with its index, got {msg!r}'
    assert 'app.servers[0].host' in msg, f'sentinel in a dict inside a list must be reported, got {msg!r}'
    assert 'app.hosts[0]' not in msg, f'a real list item must not be reported, got {msg!r}'


def test_required_multiple_missing_all_reported(monkeypatch):
    with pytest.raises(RuntimeError) as exc_info:
        _load_required(monkeypatch)
    msg = str(exc_info.value)
    # required_config has server.host, database.host, database.password
    assert msg.count('.host') + msg.count('password') >= 2


def test_required_nested_path_in_error(monkeypatch):
    with pytest.raises(RuntimeError) as exc_info:
        _load_required(monkeypatch)
    msg = str(exc_info.value)
    assert 'database.password' in msg


def test_required_raises_when_not_satisfied(monkeypatch):
    with pytest.raises(RuntimeError, match='Required config values are missing'):
        _load_required(monkeypatch)


def test_required_satisfied_by_cfg_env_var(monkeypatch):
    _load_required(
        monkeypatch,
        CFG__APP__SERVER__HOST='localhost',
        CFG__APP__DATABASE__HOST='db-host',
        CFG__APP__DATABASE__PASSWORD='secret',
    )
    assert Cfg.app.server.host == 'localhost'


def test_required_satisfied_by_env_layer(monkeypatch, tmp_path):
    """Env layer supplying a required value before validate_required() should satisfy it."""
    cfg_root = tmp_path / 'config'
    (cfg_root / 'env').mkdir(parents=True)
    # server.yaml → Cfg.server; env layer deep-merges Cfg.env.dev.server into Cfg.server
    (cfg_root / 'server.yaml').write_text('host: !required\nport: 8080\n')
    (cfg_root / 'env' / 'dev.yaml').write_text('server:\n  host: dev-host\n')
    monkeypatch.setenv('PYFLEX_ENV', 'dev')
    Cfg.reload_config(config_path=cfg_root)
    assert Cfg.server.host == 'dev-host'


def test_required_sequence_satisfied_by_replacing_the_list(monkeypatch, tmp_path):
    (tmp_path / 'app.yaml').write_text(_SEQUENCE_YAML, encoding='utf-8')
    monkeypatch.setenv('CFG__APP__HOSTS', '[host-a, host-b]::yaml_r')
    monkeypatch.setenv('CFG__APP__SERVERS', '[{name: primary, host: db-1}]::yaml_r')

    Cfg.reload_config(config_path=tmp_path)

    assert Cfg.app.hosts == ['host-a', 'host-b'], f'got {Cfg.app.hosts!r}'


def test_required_sibling_real_values_unchanged(monkeypatch):
    _load_required(
        monkeypatch,
        CFG__APP__SERVER__HOST='localhost',
        CFG__APP__DATABASE__HOST='db-host',
        CFG__APP__DATABASE__PASSWORD='secret',
    )
    assert Cfg.app.server.port == 8080
    assert Cfg.app.database.name == 'mydb'


def test_validate_required_explicit_call(monkeypatch):
    """validate_required() raises when called manually after clearing a key."""
    _load_required(
        monkeypatch,
        CFG__APP__SERVER__HOST='localhost',
        CFG__APP__DATABASE__HOST='db-host',
        CFG__APP__DATABASE__PASSWORD='secret',
    )
    # Manually plant a sentinel to verify the explicit call works
    Cfg.app.server.host = Required()
    with pytest.raises(RuntimeError, match='Required config values are missing'):
        Cfg.validate_required()


def _load_required(monkeypatch, **env_overrides):
    """Reload into required_config, optionally setting CFG__ env vars first."""
    for k, v in env_overrides.items():
        monkeypatch.setenv(k, v)
    Cfg.reload_config(config_path=_REQUIRED_CONFIG)
