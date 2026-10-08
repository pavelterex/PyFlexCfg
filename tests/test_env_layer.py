"""Tests for PYFLEX_ENV environment layering (Feature 1)."""

from pathlib import Path

import pytest

from pyflexcfg import Cfg

_DEV_LAYER_YAML = 'app:\n  host: dev\nlog_level: debug\nreplicas: [a, b]\nextras:\n  flag: true\n'
_ENV_LAYER_CONFIG = Path(__file__).parent / 'test_data' / 'env_layer_config'


@pytest.fixture
def env_config(monkeypatch):
    """Load the env-layer test config and restore afterwards."""
    monkeypatch.delenv('PYFLEX_ENV', raising=False)
    Cfg.reload_config(config_path=_ENV_LAYER_CONFIG)
    return Cfg


def test_apply_env_layer_called_in_reload(monkeypatch, env_config):
    monkeypatch.setenv('PYFLEX_ENV', 'staging')
    Cfg.reload_config(config_path=_ENV_LAYER_CONFIG)
    assert Cfg.database.host == 'staging-host'
    assert Cfg.service.name == 'myapp-staging'


def test_env_layer_case_insensitive(monkeypatch, env_config):
    monkeypatch.setenv('PYFLEX_ENV', 'DEV')
    Cfg.reload_config(config_path=_ENV_LAYER_CONFIG)
    assert Cfg.database.host == 'dev-host'


def test_env_layer_deep_merge_preserves_siblings(monkeypatch, env_config):
    monkeypatch.setenv('PYFLEX_ENV', 'dev')
    Cfg.reload_config(config_path=_ENV_LAYER_CONFIG)
    # host overridden by dev layer; port and name must survive
    assert Cfg.database.host == 'dev-host'
    assert Cfg.database.port == 5432
    assert Cfg.database.name == 'mydb'


def test_env_layer_merges_into_root(monkeypatch, env_config):
    monkeypatch.setenv('PYFLEX_ENV', 'dev')
    Cfg.reload_config(config_path=_ENV_LAYER_CONFIG)
    assert Cfg.database.host == 'dev-host'


def test_env_layer_missing_env_no_crash(monkeypatch, env_config, caplog):
    import logging

    monkeypatch.setenv('PYFLEX_ENV', 'nonexistent')
    with caplog.at_level(logging.DEBUG, logger='pyflexcfg'):
        Cfg.reload_config(config_path=_ENV_LAYER_CONFIG)
    assert Cfg.database.host == 'base-host'
    assert any('nonexistent' in r.message for r in caplog.records)


def test_env_layer_non_attrdict_scalar_replaced(monkeypatch, env_config):
    monkeypatch.setenv('PYFLEX_ENV', 'dev')
    Cfg.reload_config(config_path=_ENV_LAYER_CONFIG)
    assert Cfg.service.debug is True
    assert Cfg.service.timeout == 60


def test_env_layer_not_set_is_noop(monkeypatch, env_config):
    monkeypatch.delenv('PYFLEX_ENV', raising=False)
    Cfg.reload_config(config_path=_ENV_LAYER_CONFIG)
    assert Cfg.database.host == 'base-host'
    assert Cfg.service.debug is False


def test_env_layer_overridden_by_cfg_env_var(monkeypatch, env_config):
    monkeypatch.setenv('PYFLEX_ENV', 'dev')
    monkeypatch.setenv('CFG__DATABASE__HOST', 'override-host')
    Cfg.reload_config(config_path=_ENV_LAYER_CONFIG)
    assert Cfg.database.host == 'override-host'


@pytest.mark.parametrize('next_env', ['prd', None], ids=['switch to prd', 'unset'])
def test_env_layer_values_dropped_on_reload_after_switch(monkeypatch, tmp_path, next_env):
    (tmp_path / 'env').mkdir()
    (tmp_path / 'app.yaml').write_text('host: base\n', encoding='utf-8')
    (tmp_path / 'env' / 'dev.yaml').write_text(_DEV_LAYER_YAML, encoding='utf-8')
    (tmp_path / 'env' / 'prd.yaml').write_text('app:\n  host: prd\n', encoding='utf-8')
    monkeypatch.setenv('PYFLEX_ENV', 'dev')
    Cfg.reload_config(config_path=tmp_path)
    assert Cfg.log_level == 'debug', 'dev layer must be applied before the switch'

    if next_env:
        monkeypatch.setenv('PYFLEX_ENV', next_env)
    else:
        monkeypatch.delenv('PYFLEX_ENV')
    Cfg.reload_config()

    assert Cfg.app.host == (next_env or 'base'), f'got {Cfg.app.host!r}'
    for stale in ('log_level', 'replicas', 'extras'):
        assert not hasattr(Cfg, stale), f'{stale!r} from the dev layer survived the reload'
