from pathlib import PurePosixPath, PureWindowsPath

import yaml

from pyflexcfg.components.misc import AttrDict, Secret
from pyflexcfg.components.yaml_dumper import YamlDumper


def test_attrdict_serializes_as_plain_map():
    text = _dump(AttrDict({'a': 1, 'b': 'two'}))

    assert 'a: 1' in text, f'missing a: 1\n{text}'
    assert 'b: two' in text, f'missing b: two\n{text}'


def test_nested_attrdict_round_trip():
    src = AttrDict({'outer': AttrDict({'inner': AttrDict({'k': 'v'})})})
    text = _dump(src)
    loaded = yaml.safe_load(text)

    assert loaded == {'outer': {'inner': {'k': 'v'}}}, f'round-trip mismatch: {loaded}'


def test_path_serializes_as_string():
    text = _dump({'win': PureWindowsPath('C:\\foo\\bar')})

    assert 'C:\\foo\\bar' in text, f'windows path missing:\n{text}'

    text = _dump({'posix': PurePosixPath('/var/log/app')})

    assert '/var/log/app' in text, f'posix path missing:\n{text}'


def test_secret_is_masked_in_dump():
    text = _dump({'token': Secret('super-secret')})

    assert '********' in text, f'mask not present:\n{text}'
    assert 'super-secret' not in text, f'plaintext leaked:\n{text}'


def _dump(data) -> str:
    return yaml.dump(data, Dumper=YamlDumper, default_flow_style=False, sort_keys=False)
