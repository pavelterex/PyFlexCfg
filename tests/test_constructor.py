from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath

import pytest
import yaml

from pyflexcfg.components.yaml_loader import YamlLoader

TEST_DATA_DIR = Path(__file__).parent / 'test_data'
TEST_CONSTRUCTOR_FILE = TEST_DATA_DIR / 'constructors.yaml'


@pytest.fixture(scope='module')
def constructor_config():
    with TEST_CONSTRUCTOR_FILE.open() as fl:
        return yaml.load(fl, YamlLoader)


class TestConstructors:
    def test_construct_home_dir(self, constructor_config):
        assert constructor_config['home_dir'] == Path.home() / 'subdir' / 'file.txt'

    def test_construct_path(self, constructor_config):
        result = constructor_config['path']

        assert isinstance(result, Path), f'expected Path, got {type(result).__name__}'
        assert result == Path('tmp', 'app', 'data'), f'got {result!r}'

    def test_construct_path_posix(self, constructor_config):
        result = constructor_config['path_posix']

        assert result == PurePosixPath('/var/log/test.log')
        assert isinstance(result, PurePosixPath), f'expected PurePosixPath, got {type(result).__name__}'

    def test_construct_path_win(self, constructor_config):
        result = constructor_config['path_win']

        assert result == PureWindowsPath('C:/Test/files/test_file.txt')
        assert isinstance(result, PureWindowsPath), f'expected PureWindowsPath, got {type(result).__name__}'

    def test_construct_pure_path(self, constructor_config):
        result = constructor_config['pure_path']

        assert isinstance(result, PurePath), f'expected PurePath, got {type(result).__name__}'

    def test_construct_pure_path_posix(self, constructor_config):
        result = constructor_config['pure_path_posix']

        assert isinstance(result, PurePosixPath), f'expected PurePosixPath, got {type(result).__name__}'
        assert result == PurePosixPath('/var/log/app.log'), f'got {result!r}'

    def test_construct_pure_path_win(self, constructor_config):
        result = constructor_config['pure_path_win']

        assert isinstance(result, PureWindowsPath), f'expected PureWindowsPath, got {type(result).__name__}'
        assert result == PureWindowsPath('C:/Program Files/App/run.exe'), f'got {result!r}'

    def test_construct_string(self, constructor_config):
        assert constructor_config['string'] == 'This is a test string'
