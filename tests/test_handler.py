import logging
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

_UNREACHABLE = 'cannot be read with dot notation'

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

    def test_reload_drops_callable_runtime_value(self):
        Cfg.callback = lambda: None
        Cfg.reload_config()

        assert not hasattr(Cfg, 'callback'), 'a callable runtime value must be dropped like any other config value'
        assert callable(Cfg.reload_config), 'handler methods must survive a reload'
        assert Cfg.config_root.is_dir(), 'handler attributes must survive a reload'

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

    def test_str_includes_callable_runtime_value(self):
        Cfg.callback = lambda: None
        try:
            dumped = str(Cfg)
        finally:
            del Cfg.callback

        assert 'callback:' in dumped, f'a callable config value must be rendered, got {dumped!r}'
        for handler_method in ('reload_config', 'update_from_env', 'validate_required'):
            assert handler_method not in dumped, f'{handler_method!r} is handler machinery but was rendered'

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

    def test_env_file_conflict_after_process_changes_credential(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv('VAULT_TOKEN', raising=False)
        (tmp_path / 'vault.env').write_text('VAULT_TOKEN=from-file\n')
        _write(tmp_path / 'general.yaml', 'key: value')
        Cfg.reload_config(config_path=tmp_path)
        assert os.environ['VAULT_TOKEN'] == 'from-file', 'the file must supply the value first'

        monkeypatch.setenv('VAULT_TOKEN', 'set-by-the-application')

        with pytest.raises(RuntimeError, match='VAULT_TOKEN'):
            Cfg.reload_config()
        assert os.environ['VAULT_TOKEN'] == 'set-by-the-application', 'the process value must be left in place'

    @pytest.mark.parametrize('name', ['PYFLEX_CFG_KEY', 'VAULT_ADDR', 'VAULT_TOKEN'])
    def test_env_file_conflicting_with_process_credential_raises(self, tmp_path: Path, monkeypatch, name):
        monkeypatch.setenv(name, 'process-value')
        monkeypatch.setenv('HARMLESS_PROBE', 'process-value')
        (tmp_path / 'settings.env').write_text(f'HARMLESS_PROBE=file-value\n{name}=file-value\n')
        _write(tmp_path / 'general.yaml', 'key: value')

        with pytest.raises(RuntimeError) as exc_info:
            Cfg.reload_config(config_path=tmp_path)
        msg = str(exc_info.value)

        assert name in msg, f'the error must name the variable, got {msg!r}'
        assert 'settings.env' in msg, f'the error must name the file, got {msg!r}'
        assert 'process-value' not in msg, 'the error must not contain the process value'
        assert 'file-value' not in msg, 'the error must not contain the file value'
        assert os.environ[name] == 'process-value', 'the process value must be left in place'
        assert os.environ['HARMLESS_PROBE'] == 'process-value', 'no file value may be applied when loading is refused'

    @pytest.mark.parametrize('name', ['PYFLEX_CFG_KEY', 'VAULT_ADDR', 'VAULT_TOKEN'])
    def test_env_file_credential_equal_to_process_value_accepted(self, tmp_path: Path, monkeypatch, name):
        monkeypatch.setenv(name, 'same-value')
        (tmp_path / 'settings.env').write_text(f'{name}=same-value\n')
        _write(tmp_path / 'general.yaml', 'key: value')

        Cfg.reload_config(config_path=tmp_path)

        assert Cfg.general.key == 'value', 'identical values in both places are not a conflict'

    def test_env_file_credential_rotated_between_reloads(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv('VAULT_TOKEN', raising=False)
        _write(tmp_path / 'general.yaml', 'key: value')
        (tmp_path / 'vault.env').write_text('VAULT_TOKEN=first-token\n')
        Cfg.reload_config(config_path=tmp_path)
        assert os.environ['VAULT_TOKEN'] == 'first-token', 'a file may supply a credential the process lacks'

        (tmp_path / 'vault.env').write_text('VAULT_TOKEN=rotated-token\n')
        Cfg.reload_config()

        assert os.environ['VAULT_TOKEN'] == 'rotated-token', 'a value that came from the file may be rotated in it'

    def test_env_file_selects_env_layer(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv('PYFLEX_ENV', raising=False)
        (tmp_path / 'settings.env').write_text('PYFLEX_ENV=dev\n')
        _write(tmp_path / 'database.yaml', 'host: base-host')
        (tmp_path / 'env').mkdir()
        _write(tmp_path / 'env' / 'dev.yaml', 'database:\n  host: dev-host')

        Cfg.reload_config(config_path=tmp_path)

        assert Cfg.database.host == 'dev-host', 'PYFLEX_ENV set in a .env file must select the layer'

    @pytest.mark.parametrize('with_env_file', [True, False], ids=['.env present', 'no .env'])
    def test_env_file_value_overrides_process_variable(self, tmp_path: Path, monkeypatch, with_env_file):
        """Documented precedence: YAML < process environment < .env file."""
        monkeypatch.setenv('PRECEDENCE_PROBE', 'from-process')
        monkeypatch.setenv('CFG__GENERAL__HOST', 'from-process')
        _write(tmp_path / 'general.yaml', 'host: from-yaml')
        if with_env_file:
            (tmp_path / 'overrides.env').write_text('PRECEDENCE_PROBE=from-file\nCFG__GENERAL__HOST=from-file\n')
        expected = 'from-file' if with_env_file else 'from-process'

        Cfg.reload_config(config_path=tmp_path)

        assert os.getenv('PRECEDENCE_PROBE') == expected, f'got {os.getenv("PRECEDENCE_PROBE")!r}'
        assert Cfg.general.host == expected, f'the override must follow the same precedence, got {Cfg.general.host!r}'

    @pytest.mark.parametrize('extra_file', [True, False], ids=['two .env files', 'one .env file'])
    def test_env_files_more_than_one_warned(self, tmp_path: Path, monkeypatch, caplog, extra_file):
        for name in ('ENV_PROBE_SHARED', 'ENV_PROBE_ONLY_A', 'ENV_PROBE_ONLY_B'):
            monkeypatch.delenv(name, raising=False)
        (tmp_path / 'app.env').write_text('ENV_PROBE_SHARED=secret-a\nENV_PROBE_ONLY_A=1\n')
        if extra_file:
            (tmp_path / 'backup.env').write_text('ENV_PROBE_SHARED=secret-b\nENV_PROBE_ONLY_B=1\n')
        _write(tmp_path / 'general.yaml', 'key: value')

        with caplog.at_level(logging.WARNING, logger='pyflexcfg'):
            Cfg.reload_config(config_path=tmp_path)
        warnings = [r.getMessage() for r in caplog.records if '.env files' in r.getMessage()]

        if not extra_file:
            assert not warnings, f'a single .env file must not be warned about, got {warnings!r}'
            return

        assert len(warnings) == 1, f'expected one warning, got {warnings!r}'
        for expected in ('app.env', 'backup.env', 'ENV_PROBE_SHARED'):
            assert expected in warnings[0], f'{expected!r} is missing from the warning: {warnings[0]!r}'
        for unexpected in ('ENV_PROBE_ONLY_A', 'ENV_PROBE_ONLY_B', 'secret-a', 'secret-b'):
            assert unexpected not in warnings[0], f'{unexpected!r} must not be in the warning: {warnings[0]!r}'

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

    def test_root_level_names_like_dict_methods_not_warned(self, tmp_path: Path, caplog):
        _write(tmp_path / 'items.yaml', 'size: 1')
        _write(tmp_path / 'general.yaml', 'host: localhost')

        with caplog.at_level(logging.WARNING, logger='pyflexcfg'):
            Cfg.reload_config(config_path=tmp_path)

        assert Cfg.items.size == 1, 'a root-level name is reachable by attribute, whatever it is called'
        assert not any(_UNREACHABLE in r.getMessage() for r in caplog.records), (
            'a reachable root-level name, or a config with only ordinary keys, must not be warned about'
        )

    @pytest.mark.parametrize(
        'stem',
        ['apply_env_layer', 'config_root', 'project_root', 'reload_config', 'update_from_env', 'validate_required'],
    )
    def test_root_name_colliding_with_handler_member_raises(self, tmp_path: Path, stem):
        _write(tmp_path / f'{stem}.yaml', 'key: value')
        _write(tmp_path / 'general.yaml', 'key: value')

        with pytest.raises(RuntimeError, match='Namespace conflict') as exc_info:
            Cfg.reload_config(config_path=tmp_path)

        assert stem in str(exc_info.value), f'the error must name the file stem, got {exc_info.value}'
        for method in ('apply_env_layer', 'reload_config', 'update_from_env', 'validate_required'):
            assert callable(getattr(Cfg, method)), f'{method} was replaced by a config file'
        assert not isinstance(Cfg.project_root, AttrDict), 'project_root was replaced by a config file'

    def test_unreachable_keys_warned(self, tmp_path: Path, caplog):
        _write(
            tmp_path / 'app.yaml',
            """
            items:
              size: 1
            nested:
              keys: [a, b]
              servers:
                - class: web
            my-key: hyphen
            1: number
            false: boolean
            __len__: dunder
            plain: fine
            print: also fine
            """,
        )
        _write(tmp_path / 'global.yaml', 'region: eu')
        (tmp_path / 'env').mkdir()
        _write(tmp_path / 'env' / 'copy.yaml', 'host: copy-host')

        with caplog.at_level(logging.WARNING, logger='pyflexcfg'):
            Cfg.reload_config(config_path=tmp_path)
        warnings = [r.getMessage() for r in caplog.records if _UNREACHABLE in r.getMessage()]
        expected = (
            'app.items (dict attribute)',
            'app.nested.keys (dict attribute)',
            'app.nested.servers[0].class (Python keyword)',
            "app['my-key'] (not an identifier)",
            'app[1] (not a string)',
            'app[False] (not a string)',
            'app.__len__ (dict attribute)',
            'env.copy (dict attribute)',
            'global (Python keyword)',
        )

        assert len(warnings) == 1, f'expected one combined warning, got {warnings!r}'
        for entry in expected:
            assert entry in warnings[0], f'{entry!r} is missing from the warning: {warnings[0]!r}'
        for ordinary in ('app.plain', 'app.print', 'app.nested (', 'env ('):
            assert ordinary not in warnings[0], f'{ordinary!r} is reachable but was reported: {warnings[0]!r}'
        assert Cfg.app['items']['size'] == 1, 'the config must still load and be readable by item access'
        assert getattr(Cfg, 'global').region == 'eu', 'a keyword-named file must still load'


def _write(path: Path, content: str) -> None:
    path.write_text(dedent(content).strip() + '\n')
