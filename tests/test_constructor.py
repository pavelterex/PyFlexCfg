from pathlib import Path, PureWindowsPath, PurePosixPath

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
    def test_construct_string(self, constructor_config):
        assert constructor_config['string'] == 'This is a test string'

    def test_construct_path_win(self, constructor_config):
        assert constructor_config['path_win'] == PureWindowsPath('C:/Test/files/test_file.txt')

    def test_construct_path_posix(self, constructor_config):
        assert constructor_config['path_posix'] == PurePosixPath('/var/log/test.log')
