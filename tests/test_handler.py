import shutil
from pathlib import Path

import pytest
import yaml
from pytest import param
from pytest_assume.plugin import assume

from conftest import TEST_STRING
from pyflexcfg import Cfg, AttrDict

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
        'CFG__APP__GENERAL__VAR_INT': 'overridden_type_and_value',
    }
    for k, v in env_vars.items():
        monkeypatch.setenv(k, v)
    Cfg.update_from_env()
    yield
    Cfg.reload_config()


@pytest.fixture(scope='module')
def temp_config_dir():
    temp_dir = Path('.\\tests\\test_data\\temp_config')
    temp_dir.mkdir(exist_ok=True)
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def tmp_config_file(temp_config_dir, valuename):
    file = temp_config_dir / f'tmp_cfg.yaml'
    file.touch()
    data = {valuename: 'test'}
    with file.open(mode='w') as fl:
        yaml.dump(data, fl)
    yield file.name
    file.unlink()


class TestHandler:
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

    def test_collections_config(self):
        data = Cfg.app.collections
        assume(data.var_list == ['value1', 'value2', 'value3'])
        assume(data.var_dict == {'key1': 'value1', 'key2': 'value2', 'key3': 'value3'})
        assume(isinstance(data.var_dict, AttrDict))
        assume(data.var_dict.key1 == 'value1')

    def test_nested_list_config(self):
        data = Cfg.app.nested
        nested_list = [['subvalue1', 'subvalue2'], ['subvalue1', 'subvalue2']]
        assume(data.var_nested_list1 == nested_list)
        assume(data.var_nested_list2 == nested_list)

    def test_nested_dict_config(self):
        data = Cfg.app.nested
        nested_dict = {
            'subdict1': {
                'key1': 'value1',
                'key2': 'value2',
            },
            'subdict2': {
                'key1': 'value1',
                'key2': 'value2',
            },
        }
        assume(data.var_nested_dict1 == nested_dict)
        assume(data.var_nested_dict2 == nested_dict)

    def test_anchor_config(self):
        data = Cfg.app.anchor
        assert data.var_value == ['base', 'value']

    def test_merge_config(self):
        data = Cfg.app.merge
        assert data.var_merge == {'key1': 'value1', 'key2': 'value2'}

    def test_env_var_override(self, overridden_config):
        assume(Cfg.app.general.var_str == 'overridden_value')
        assume(Cfg.app.general.var_int == 'overridden_type_and_value')

    def test_reload_config(self):
        Cfg.app.general.var_int = 1000
        Cfg.reload_config()
        assert Cfg.app.general.var_int == 500

    @pytest.mark.parametrize('filename', IMPROPER_NAMES_PARAM_SET)
    def test_improper_name_file_not_loaded(self, temp_config_dir, filename):
        Cfg.reload_config(config_path=temp_config_dir, reset=False)
        assert not hasattr(Cfg, str(filename))

    @pytest.mark.parametrize('valuename', IMPROPER_NAMES_PARAM_SET)
    def test_improper_name_value_not_loaded(self, temp_config_dir, tmp_config_file, valuename):
        Cfg.reload_config(config_path=temp_config_dir, reset=False)
        assert not hasattr(Cfg[tmp_config_file], str(valuename))
