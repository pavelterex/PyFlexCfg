import os
import shutil
from pathlib import Path
from textwrap import dedent

import pytest
from conftest import TEST_STRING
from pytest import param
from pytest_assume.plugin import assume

from pyflexcfg import Cfg
from pyflexcfg.components.encryption import AESCipher
from pyflexcfg.components.misc import AttrDict, Secret

IMPROPER_NAMES_PARAM_SET = [
    param('_testname_', id='private like'),
    param('__testname__', id='protected like'),
    param('test-name', id='hyphen in name'),
    param('1testname', id='starts with digit'),
    param('test.name', id='dot in name'),
    param('t' * 50, id='long name'),
    param('1111111', id='only numbers'),
]


@pytest.fixture
def improper_filename_config(temp_config_dir, filename):
    file = temp_config_dir / f'{filename}.yaml'
    file.touch()

    yield file

    file.unlink()


@pytest.fixture
def overridden_config(monkeypatch):
    env_vars = {
        'CFG__APP__GENERAL__VAR_STR': 'overridden_value',
        'CFG__APP__GENERAL__VAR_INT': '777::int',
    }

    for k, v in env_vars.items():
        monkeypatch.setenv(k, v)

    Cfg.update_from_env()


@pytest.fixture(scope='module')
def temp_config_dir():
    temp_dir = Path(__file__).parent / 'test_data' / 'temp_config'
    temp_dir.mkdir(exist_ok=True)

    yield temp_dir

    shutil.rmtree(temp_dir, ignore_errors=True)


class TestHandler:
    def test_anchor_config(self):
        data = Cfg.app.anchor

        assert data.var_value == ['base', 'value']

    def test_collections_config(self):
        data = Cfg.app.collections

        assume(data.var_list == ['value1', 'value2', 'value3'])
        assume(data.var_dict == {'key1': 'value1', 'key2': 'value2', 'key3': 'value3'})
        assume(isinstance(data.var_dict, AttrDict))
        assume(data.var_dict.key1 == 'value1')

    def test_env_var_override(self, overridden_config):
        assume(Cfg.app.general.var_str == 'overridden_value')
        assume(Cfg.app.general.var_int == 777)

    @pytest.mark.parametrize('filename', IMPROPER_NAMES_PARAM_SET)
    def test_improper_name_file_not_loaded(self, temp_config_dir, improper_filename_config, filename):
        Cfg.reload_config(config_path=temp_config_dir, reset=False)

        assert not hasattr(Cfg, str(filename)), f'file {filename!r} should not be loaded as an attribute'

    def test_merge_config(self):
        data = Cfg.app.merge

        assert data.var_merge == {'key1': 'value1', 'key2': 'value2'}

    def test_nested_dict_config(self):
        data = Cfg.app.nested
        nested_dict = {
            'subdict1': {'key1': 'value1', 'key2': 'value2'},
            'subdict2': {'key1': 'value1', 'key2': 'value2'},
        }

        assume(data.var_nested_dict1 == nested_dict)
        assume(data.var_nested_dict2 == nested_dict)

    def test_nested_list_config(self):
        data = Cfg.app.nested
        nested_list = [['subvalue1', 'subvalue2'], ['subvalue1', 'subvalue2']]

        assume(data.var_nested_list1 == nested_list)
        assume(data.var_nested_list2 == nested_list)

    def test_reload_config(self):
        Cfg.app.general.var_int = 1000
        Cfg.reload_config()

        assert Cfg.app.general.var_int == 500, f'reload should restore loaded value, got {Cfg.app.general.var_int!r}'

    def test_simple_config(self):
        data = Cfg.app.general

        assume(data.var_str == 'test')
        assume(data.var_empty_str == '')
        assume(data.var_secret_str == TEST_STRING)
        assume(data.var_int == 500)
        assume(data.var_float == 10.5)
        assume(data.var_bool_true is True)
        assume(data.var_bool_false is False)
        assume(data.var_null is None)

    def test_str_lists_only_config_after_reload(self):
        Cfg.reload_config()
        dumped = str(Cfg)

        assert 'app:' in dumped, f'config must still be rendered, got {dumped!r}'
        for handler_attr in ('config_root', 'project_root'):
            assert handler_attr not in dumped, f'{handler_attr!r} is not a config value but was rendered'


class TestTmpPath:
    """
    End-to-end scenarios that build a fresh config tree per test.

    The autouse `restore_cfg_after_test` fixture in `conftest.py` puts
    `Cfg` back on the main test config after each test runs.
    """

    def test_dir_and_yaml_name_collision_raises(self, tmp_path: Path):
        _write(tmp_path / 'env.yaml', 'inline: true')
        (tmp_path / 'env').mkdir()
        _write(tmp_path / 'env' / 'dev.yaml', 'k: v')

        with pytest.raises(RuntimeError, match='Namespace conflict'):
            Cfg.reload_config(config_path=tmp_path)

    def test_encr_round_trip(self, tmp_path: Path, env_key):
        secret_value = 'super-secret-payload'
        encrypted = AESCipher('1234').encrypt(secret_value)
        _write(tmp_path / 'secrets.yaml', f'token: !encr {encrypted}')

        Cfg.reload_config(config_path=tmp_path)

        assert isinstance(Cfg.secrets.token, Secret), 'decrypted value must be Secret'
        assert Cfg.secrets.token == secret_value, 'underlying decrypted text must match'
        assert str(Cfg.secrets.token) == '********', 'Secret must mask on display'

    def test_env_file_autoload(self, tmp_path: Path, monkeypatch):
        """A .env file in config root should be loaded before YAML parsing."""
        monkeypatch.delenv('AUTOLOAD_PROBE', raising=False)
        (tmp_path / 'overrides.env').write_text('AUTOLOAD_PROBE=hello\n')
        _write(tmp_path / 'placeholder.yaml', 'x: 1')

        Cfg.reload_config(config_path=tmp_path)

        assert os.getenv('AUTOLOAD_PROBE') == 'hello', '.env file should populate environment'

    def test_loaded_yaml_dict_becomes_attrdict(self, tmp_path: Path):
        _write(tmp_path / 'general.yaml', 'nested:\n  key: value\n  inner:\n    deep: 42')
        Cfg.reload_config(config_path=tmp_path)

        assert isinstance(Cfg.general.nested, AttrDict), 'nested dicts must be wrapped'
        assert isinstance(Cfg.general.nested.inner, AttrDict), 'deeply nested dicts must be wrapped too'
        assert Cfg.general.nested.inner.deep == 42

    def test_missing_config_root_raises(self, tmp_path: Path):
        nowhere = tmp_path / 'does-not-exist'
        with pytest.raises(RuntimeError, match='not found'):
            Cfg.reload_config(config_path=nowhere)

    def test_nested_namespace_loading(self, tmp_path: Path):
        _write(tmp_path / 'general.yaml', 'key: value')
        (tmp_path / 'env').mkdir()
        _write(tmp_path / 'env' / 'dev.yaml', 'host: dev.example.com')
        _write(tmp_path / 'env' / 'prd.yaml', 'host: prd.example.com')

        Cfg.reload_config(config_path=tmp_path)

        assert Cfg.general.key == 'value'
        assert Cfg.env.dev.host == 'dev.example.com'
        assert Cfg.env.prd.host == 'prd.example.com'

    def test_proj_root_constructor_with_kwarg(self, tmp_path: Path):
        _write(tmp_path / 'paths.yaml', 'p: !proj_root [logs, app.log]')
        Cfg.reload_config(config_path=tmp_path, project_root=tmp_path.parent)

        assert Cfg.paths.p == tmp_path.parent / 'logs' / 'app.log', f'got {Cfg.paths.p!r}'

    def test_proj_root_requires_env_when_custom_config_root(self, tmp_path: Path, monkeypatch):
        """Custom CFG root with no PROJECT root env: `!proj_root` must raise."""
        monkeypatch.setenv('PYFLEX_CFG_ROOT_PATH', str(tmp_path))
        monkeypatch.delenv('PYFLEX_PROJECT_ROOT_PATH', raising=False)
        _write(tmp_path / 'paths.yaml', 'p: !proj_root [logs]')

        with pytest.raises(RuntimeError, match='PYFLEX_PROJECT_ROOT_PATH'):
            Cfg.reload_config(config_path=tmp_path)

    def test_proj_root_uses_env_var_when_set(self, tmp_path: Path, monkeypatch):
        """PYFLEX_PROJECT_ROOT_PATH wins over any other resolution path."""
        custom_root = tmp_path / 'custom_root'
        custom_root.mkdir()
        monkeypatch.setenv('PYFLEX_PROJECT_ROOT_PATH', str(custom_root))
        _write(tmp_path / 'paths.yaml', 'p: !proj_root [logs, app.log]')

        Cfg.reload_config(config_path=tmp_path)

        assert Cfg.paths.p == custom_root / 'logs' / 'app.log', f'got {Cfg.paths.p!r}'

    def test_reload_with_reset_drops_previous_attrs(self, tmp_path: Path):
        _write(tmp_path / 'old_only.yaml', 'k: 1')
        Cfg.reload_config(config_path=tmp_path)

        assert hasattr(Cfg, 'old_only'), 'first load should have populated old_only'

        fresh = tmp_path / 'fresh'
        fresh.mkdir()
        _write(fresh / 'new_only.yaml', 'k: 2')
        Cfg.reload_config(config_path=fresh, reset=True)

        assert hasattr(Cfg, 'new_only'), 'second load should populate new_only'
        assert not hasattr(Cfg, 'old_only'), 'reset=True must drop attrs from prior load'


def _write(path: Path, content: str) -> None:
    path.write_text(dedent(content).strip() + '\n')
