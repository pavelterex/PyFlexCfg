from pathlib import Path, PureWindowsPath, PurePosixPath

import pytest
import yaml

from pyflexcfg.components.yaml_loader import YamlLoader

TEST_DATA_DIR = Path(__file__).parent / 'test_data'
TEST_CONSTRUCTOR_FILE = TEST_DATA_DIR / 'constructor_config.yaml'
TEST_APP_FILE = TEST_DATA_DIR / 'app.yaml'


@pytest.fixture(scope='module')
def load_constructor():
    with TEST_CONSTRUCTOR_FILE.open() as fl:
        return yaml.load(fl, YamlLoader)


@pytest.fixture(scope='module')
def load_config():
    with TEST_APP_FILE.open() as fl:
        return yaml.load(fl, YamlLoader)


class TestLoader:
    def test_simple_yaml(self, load_config):
        expected = {
            'namespace_1': {
                'string_value': 'test string',
                'integer_value': 12345678,
                'boolean_value': True,
                'empty_value': None,
                'list_value': ['item1', 'item2'],
                'dict_value': {'key1': 'value1', 'key2': 'value2'}
            }
        }
        assert load_config == expected, f'Loaded data {load_config} is not equal {expected}!'

    def test_string_yaml_loader(self, test_config, load_constructor):
        assert load_constructor['string_result'] == 'This is a test string'

    def test_path_win_loader(self, load_constructor):
        assert load_constructor['path_win_result'] == PureWindowsPath('C:/Test/files/test_file.txt')

    def test_path_posix_loader(self, load_constructor):
        assert load_constructor['path_posix_result'] == PurePosixPath('/var/log/test.log')
