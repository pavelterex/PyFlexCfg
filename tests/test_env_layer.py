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


@pytest.mark.parametrize('key', ['reload_config', 'apply_env_layer', 'config_root', 'env', '_handler_attrs', 1])
def test_env_layer_reserved_key_rejected(monkeypatch, tmp_path, key):
    (tmp_path / 'env').mkdir()
    (tmp_path / 'database.yaml').write_text('host: base-host\n', encoding='utf-8')
    (tmp_path / 'env' / 'dev.yaml').write_text(f'database:\n  host: dev-host\n{key}:\n  x: 1\n', encoding='utf-8')
    monkeypatch.setenv('PYFLEX_ENV', 'dev')

    with pytest.raises(RuntimeError, match='reserved') as exc_info:
        Cfg.reload_config(config_path=tmp_path)

    assert repr(key) in str(exc_info.value), f'the error must name the offending key, got {exc_info.value}'
    assert Cfg.database.host == 'base-host', 'nothing from a rejected layer may be merged'
    assert callable(Cfg.reload_config), 'handler machinery must be intact'
    assert callable(Cfg.apply_env_layer), 'handler machinery must be intact'
    assert Cfg.config_root == tmp_path, 'handler attributes must be intact'


@pytest.mark.parametrize('tier', ['items', 'keys', 'copy', 'get'])
def test_env_layer_tier_named_like_dict_method_applied(monkeypatch, tmp_path, tier):
    (tmp_path / 'env').mkdir()
    (tmp_path / 'database.yaml').write_text('host: base-host\n', encoding='utf-8')
    (tmp_path / 'env' / f'{tier}.yaml').write_text(f'database:\n  host: {tier}-host\n', encoding='utf-8')
    monkeypatch.setenv('PYFLEX_ENV', tier)

    Cfg.reload_config(config_path=tmp_path)

    assert Cfg.database.host == f'{tier}-host', f'tier {tier!r} was not applied, host is {Cfg.database.host!r}'


def test_env_layer_values_copied_not_aliased(monkeypatch, tmp_path):
    (tmp_path / 'env').mkdir()
    (tmp_path / 'app.yaml').write_text('host: base\n', encoding='utf-8')
    layer = 'app:\n  nested:\n    key: from-file\nextras:\n  flag: true\nreplicas: [a, b]\n'
    (tmp_path / 'env' / 'dev.yaml').write_text(layer, encoding='utf-8')
    monkeypatch.setenv('PYFLEX_ENV', 'dev')
    monkeypatch.setenv('CFG__EXTRAS__FLAG', 'false')
    Cfg.reload_config(config_path=tmp_path)

    Cfg.replicas.append('c')
    Cfg.app.nested.key = 'changed at runtime'

    assert Cfg.extras.flag is False, 'the override must apply to the effective config'
    assert Cfg.env.dev.extras.flag is True, 'a CFG__ override changed the layer definition'
    assert Cfg.env.dev.replicas == ['a', 'b'], 'mutating an effective list changed the layer definition'
    assert Cfg.env.dev.app.nested.key == 'from-file', 'mutating an effective mapping changed the layer definition'

    monkeypatch.delenv('CFG__EXTRAS__FLAG')
    Cfg.apply_env_layer()

    assert Cfg.extras.flag is True, 're-applying the layer must restore the file-defined value'
    assert Cfg.replicas == ['a', 'b'], 're-applying the layer must restore the file-defined list'


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
