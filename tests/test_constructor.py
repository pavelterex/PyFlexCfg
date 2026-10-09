import datetime
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath

import pytest
import yaml
from conftest import TEST_ENCRYPTED_STRING, TEST_STRING

from pyflexcfg.components.misc import Required, Secret
from pyflexcfg.components.yaml_dumper import YamlDumper
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

    @pytest.mark.parametrize(
        'tag',
        ['home_dir', 'path', 'path_posix', 'path_win', 'proj_root', 'pure_path', 'pure_path_posix', 'pure_path_win'],
    )
    @pytest.mark.parametrize('layout', ['[logs, !required , app.log]', '\n  - logs\n  - !required\n  - app.log\n'])
    def test_construct_path_like_with_required_part_stays_required(self, tag, layout):
        result = yaml.load(f'target: !{tag} {layout}', YamlLoader)['target']

        assert isinstance(result, Required), f'!{tag} with a required part must stay required, got {result!r}'

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

    def test_construct_string_with_encrypted_part(self):
        text = f"dsn: !string ['postgres://app:', !encr {TEST_ENCRYPTED_STRING}, '@db.example.com:', 5432, '/main']"
        data = yaml.load(text, YamlLoader)
        dsn = data['dsn']

        assert isinstance(dsn, Secret), f'a string built from a secret must be a Secret, got {type(dsn).__name__}'
        assert dsn == f'postgres://app:{TEST_STRING}@db.example.com:5432/main', 'the real secret must be composed in'
        assert repr(dsn) == '********', 'the composed string must be masked'
        assert TEST_STRING not in yaml.dump(data, Dumper=YamlDumper), 'the secret leaked into the YAML dump'

    @pytest.mark.parametrize(
        'text',
        [
            pytest.param("url: !string\n  - 'https://'\n  - !required\n  - '/api'\n", id='block list'),
            pytest.param("url: !string ['https://', !required , '/api']", id='flow list'),
            pytest.param(f"url: !string ['https://', !encr {TEST_ENCRYPTED_STRING}, !required ]", id='with a secret'),
        ],
    )
    def test_construct_string_with_required_part_stays_required(self, text):
        result = yaml.load(text, YamlLoader)['url']

        assert isinstance(result, Required), f'a string with a required part must stay required, got {result!r}'

    def test_construct_string_without_secret_stays_plain_str(self):
        result = yaml.load("url: !string ['http://', host, ':', 8080]", YamlLoader)['url']

        assert type(result) is str, f'a string with no secret part must stay a plain str, got {type(result).__name__}'
        assert result == 'http://host:8080', f'got {result!r}'

    def test_python_object_tag_cannot_run_code(self, tmp_path):
        target = tmp_path / 'created-by-yaml'
        text = f'probe: !!python/object/apply:os.mkdir ["{target.as_posix()}"]'

        with pytest.raises(yaml.YAMLError):
            yaml.load(text, YamlLoader)

        assert not target.exists(), 'loading a config file executed Python code'

    @pytest.mark.parametrize(
        'value',
        [
            pytest.param('!!python/object/apply:os.getcwd []', id='object/apply'),
            pytest.param('!!python/name:os.getcwd', id='name'),
            pytest.param('!!python/module:os', id='module'),
            pytest.param('!!python/tuple [1, 2]', id='tuple'),
        ],
    )
    def test_python_specific_tags_rejected(self, value):
        with pytest.raises(yaml.YAMLError):
            yaml.load(f'probe: {value}', YamlLoader)

    def test_standard_yaml_types_still_load(self):
        text = (
            'text: hello\nnumber: 42\nratio: 1.5\nflag: true\nnothing: null\n'
            'day: 2026-10-06\nitems: [a, b]\nmapping: {key: value}\nblob: !!binary aGVsbG8=\n'
        )
        data = yaml.load(text, YamlLoader)

        assert data['number'] == 42, f'got {data["number"]!r}'
        assert data['ratio'] == 1.5, f'got {data["ratio"]!r}'
        assert data['flag'] is True, f'got {data["flag"]!r}'
        assert data['nothing'] is None, f'got {data["nothing"]!r}'
        assert data['day'] == datetime.date(2026, 10, 6), f'got {data["day"]!r}'
        assert data['items'] == ['a', 'b'], f'got {data["items"]!r}'
        assert data['mapping'] == {'key': 'value'}, f'got {data["mapping"]!r}'
        assert data['blob'] == b'hello', f'got {data["blob"]!r}'
