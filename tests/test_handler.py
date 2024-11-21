import pytest
from pytest_assume.plugin import assume

from conftest import TEST_STRING
from pyflexcfg import Cfg, AttrDict


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

    def test_env_var_override(self, overridden_config):
        assume(Cfg.app.general.var_str == 'overridden_value')
        assume(Cfg.app.general.var_int == 'overridden_type_and_value')

    def test_reload_config(self):
        Cfg.app.general.var_int = 1000
        Cfg.reload_config()
        assert Cfg.app.general.var_int == 500
