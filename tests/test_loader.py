from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath

import pytest
import yaml

from pyflexcfg.components.yaml_loader import YamlLoader

TEST_DATA_DIR = Path(__file__).parent / 'test_data'
TEST_CONSTRUCTOR_FILE = TEST_DATA_DIR / 'constructor_config.yaml'
TEST_SIMPLE_FILE = TEST_DATA_DIR / 'simple_config.yaml'


@pytest.fixture(scope='module')
def load_config():
    with TEST_SIMPLE_FILE.open() as fl:
        return yaml.load(fl, YamlLoader)


@pytest.fixture(scope='module')
def load_constructor():
    with TEST_CONSTRUCTOR_FILE.open() as fl:
        return yaml.load(fl, YamlLoader)


class TestLoader:
    def test_home_dir_resolves_from_home(self, load_constructor):
        result = load_constructor['home_dir_result']
        assert result == Path.home() / 'subdir' / 'file.txt', f'got {result!r}'

    def test_path_posix_returns_pure_posix(self, load_constructor):
        result = load_constructor['path_posix_result']
        assert result == PurePosixPath('/var/log/test.log'), f'got {result!r}'
        assert isinstance(result, PurePosixPath), f'expected PurePosixPath, got {type(result).__name__}'

    def test_path_returns_os_native(self, load_constructor):
        result = load_constructor['path_result']
        assert isinstance(result, Path), f'expected Path, got {type(result).__name__}'
        assert result == Path('tmp', 'app', 'data'), f'got {result!r}'

    def test_path_win_returns_pure_windows(self, load_constructor):
        result = load_constructor['path_win_result']
        assert result == PureWindowsPath('C:/Test/files/test_file.txt'), f'got {result!r}'
        assert isinstance(result, PureWindowsPath), f'expected PureWindowsPath, got {type(result).__name__}'

    def test_pure_path_posix_explicit(self, load_constructor):
        result = load_constructor['pure_path_posix_result']
        assert isinstance(result, PurePosixPath), f'expected PurePosixPath, got {type(result).__name__}'
        assert result == PurePosixPath('/var/log/app.log'), f'got {result!r}'

    def test_pure_path_returns_pure(self, load_constructor):
        result = load_constructor['pure_path_result']
        assert isinstance(result, PurePath), f'expected PurePath, got {type(result).__name__}'

    def test_pure_path_win_explicit(self, load_constructor):
        result = load_constructor['pure_path_win_result']
        assert isinstance(result, PureWindowsPath), f'expected PureWindowsPath, got {type(result).__name__}'
        assert result == PureWindowsPath('C:/Program Files/App/run.exe'), f'got {result!r}'

    def test_simple_yaml(self, load_config):
        expected = {
            'namespace_1': {
                'string_value': 'test string',
                'integer_value': 12345678,
                'boolean_value': True,
                'empty_value': None,
                'list_value': ['item1', 'item2'],
                'dict_value': {'key1': 'value1', 'key2': 'value2'},
            }
        }
        assert load_config == expected, f'Loaded data {load_config} is not equal {expected}!'

    def test_string_constructor(self, load_constructor):
        assert load_constructor['string_result'] == 'This is a test string'
