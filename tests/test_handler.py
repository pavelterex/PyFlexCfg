"""End-to-end tests for ConfigHandler / HandlerMeta via tmp_path config trees."""

from pathlib import Path
from textwrap import dedent

import pytest

from pyflexcfg import Cfg
from pyflexcfg.components.encryption import AESCipher
from pyflexcfg.components.misc import AttrDict, Secret


def test_dir_and_yaml_name_collision_raises(tmp_path: Path):
    _write(tmp_path / 'env.yaml', 'inline: true')
    (tmp_path / 'env').mkdir()
    _write(tmp_path / 'env' / 'dev.yaml', 'k: v')

    with pytest.raises(RuntimeError, match='Namespace conflict'):
        Cfg.reload_config(tmp_path)


def test_encr_round_trip(tmp_path: Path, env_key):
    secret_value = 'super-secret-payload'
    encrypted = AESCipher('1234').encrypt(secret_value)
    _write(tmp_path / 'secrets.yaml', f'token: !encr {encrypted}')

    Cfg.reload_config(tmp_path)

    assert isinstance(Cfg.secrets.token, Secret), 'decrypted value must be Secret'
    assert Cfg.secrets.token == secret_value, 'underlying decrypted text must match'
    assert str(Cfg.secrets.token) == '********', 'Secret must mask on display'


def test_env_file_autoload(tmp_path: Path, monkeypatch):
    """A .env file in config root should be loaded before YAML parsing."""
    monkeypatch.delenv('AUTOLOAD_PROBE', raising=False)
    (tmp_path / 'overrides.env').write_text('AUTOLOAD_PROBE=hello\n')
    _write(tmp_path / 'placeholder.yaml', 'x: 1')

    Cfg.reload_config(tmp_path)
    import os

    assert os.getenv('AUTOLOAD_PROBE') == 'hello', '.env file should populate environment'


def test_loaded_yaml_dict_becomes_attrdict(tmp_path: Path):
    _write(tmp_path / 'general.yaml', 'nested:\n  key: value\n  inner:\n    deep: 42')
    Cfg.reload_config(tmp_path)

    assert isinstance(Cfg.general.nested, AttrDict), 'nested dicts must be wrapped'
    assert isinstance(Cfg.general.nested.inner, AttrDict), 'deeply nested dicts must be wrapped too'
    assert Cfg.general.nested.inner.deep == 42, 'deep attribute access must work'


def test_missing_config_root_raises(tmp_path: Path):
    nowhere = tmp_path / 'does-not-exist'
    with pytest.raises(RuntimeError, match='not found'):
        Cfg.reload_config(nowhere)


def test_nested_namespace_loading(tmp_path: Path):
    _write(tmp_path / 'general.yaml', 'key: value')
    (tmp_path / 'env').mkdir()
    _write(tmp_path / 'env' / 'dev.yaml', 'host: dev.example.com')
    _write(tmp_path / 'env' / 'prd.yaml', 'host: prd.example.com')

    Cfg.reload_config(tmp_path)

    assert Cfg.general.key == 'value', f'got {Cfg.general.key!r}'
    assert Cfg.env.dev.host == 'dev.example.com', f'got {Cfg.env.dev.host!r}'
    assert Cfg.env.prd.host == 'prd.example.com', f'got {Cfg.env.prd.host!r}'


def test_proj_root_constructor(tmp_path: Path):
    _write(tmp_path / 'paths.yaml', 'p: !proj_root [logs, app.log]')
    Cfg.reload_config(tmp_path, project_root=tmp_path.parent)

    assert Cfg.paths.p == tmp_path.parent / 'logs' / 'app.log', f'got {Cfg.paths.p!r}'


def test_proj_root_requires_env_when_custom_config_root(tmp_path: Path, monkeypatch):
    """With PYFLEX_CFG_ROOT_PATH set but no PYFLEX_PROJECT_ROOT_PATH, !proj_root must raise."""
    monkeypatch.setenv('PYFLEX_CFG_ROOT_PATH', str(tmp_path))
    monkeypatch.delenv('PYFLEX_PROJECT_ROOT_PATH', raising=False)
    _write(tmp_path / 'paths.yaml', 'p: !proj_root [logs]')

    with pytest.raises(RuntimeError, match='PYFLEX_PROJECT_ROOT_PATH'):
        Cfg.reload_config(tmp_path)


def test_proj_root_uses_env_var_when_set(tmp_path: Path, monkeypatch):
    """PYFLEX_PROJECT_ROOT_PATH wins over any other resolution path."""
    custom_root = tmp_path / 'custom_root'
    custom_root.mkdir()
    monkeypatch.setenv('PYFLEX_PROJECT_ROOT_PATH', str(custom_root))
    _write(tmp_path / 'paths.yaml', 'p: !proj_root [logs, app.log]')

    Cfg.reload_config(tmp_path)

    assert Cfg.paths.p == custom_root / 'logs' / 'app.log', f'got {Cfg.paths.p!r}'


def test_reload_with_reset_drops_previous_attrs(tmp_path: Path):
    _write(tmp_path / 'old.yaml', 'k: 1')
    Cfg.reload_config(tmp_path)

    assert hasattr(Cfg, 'old'), 'first load should have populated old'

    fresh = tmp_path / 'fresh'
    fresh.mkdir()
    _write(fresh / 'new.yaml', 'k: 2')
    Cfg.reload_config(fresh, reset=True)

    assert hasattr(Cfg, 'new'), 'second load should populate new'
    assert not hasattr(Cfg, 'old'), 'reset=True must drop attrs from prior load'


def test_reload_without_reset_overlays_top_level(tmp_path: Path):
    _write(tmp_path / 'shared.yaml', 'k: original')
    _write(tmp_path / 'only_first.yaml', 'k: 1')
    Cfg.reload_config(tmp_path)

    fresh = tmp_path / 'fresh'
    fresh.mkdir()
    _write(fresh / 'shared.yaml', 'k: replaced')
    Cfg.reload_config(fresh, reset=False)

    assert Cfg.shared.k == 'replaced', 'overlapping key should be replaced'
    assert Cfg.only_first.k == 1, 'non-overlapping key should survive reset=False'


def _write(path: Path, content: str) -> None:
    path.write_text(dedent(content).strip() + '\n')
