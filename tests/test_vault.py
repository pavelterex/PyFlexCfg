"""Tests for HashiCorp Vault integration (Feature 6). All Vault calls are mocked."""

import sys
from unittest.mock import MagicMock

import pytest
import yaml

import pyflexcfg.components.providers as providers_mod
from pyflexcfg.components.misc import AttrDict, Secret
from pyflexcfg.components.providers import VaultProvider, get_vault_provider
from pyflexcfg.components.yaml_dumper import YamlDumper
from pyflexcfg.components.yaml_loader import YamlLoader

WHOLE_SECRET = {
    'host': 'db.prod',
    'nested': {'token': 'abc123'},
    'note': None,
    'port': 5432,
    'replicas': ['db-a', 'db-b'],
}
WHOLE_SECRET_LEAKS = ('db.prod', 'abc123', '5432', 'db-a', 'db-b')


@pytest.fixture(autouse=True)
def reset_vault_provider():
    """Reset the module-level singleton before and after each test."""
    providers_mod._vault_provider = None
    yield
    providers_mod._vault_provider = None


@pytest.fixture
def mock_hvac(monkeypatch):
    """Inject a fake hvac module so VaultProvider can be instantiated."""
    hvac_mock = MagicMock()
    monkeypatch.setitem(sys.modules, 'hvac', hvac_mock)
    return hvac_mock


@pytest.fixture
def vault_env(monkeypatch):
    monkeypatch.setenv('VAULT_ADDR', 'http://vault:8200')
    monkeypatch.setenv('VAULT_TOKEN', 'test-token')


def test_vault_fetch_no_field_returns_attrdict(vault_env, mock_hvac):
    kv1_response = {'data': {'host': 'db.prod', 'port': 5432}}
    mock_hvac.Client.return_value.secrets.kv.v1.read_secret.return_value = kv1_response

    provider = VaultProvider()
    result = provider.fetch('secret/myapp/db')

    assert isinstance(result, AttrDict)
    assert result.host == 'db.prod'
    assert result.port == 5432


def test_vault_hvac_not_installed_raises(monkeypatch, vault_env):
    monkeypatch.setitem(sys.modules, 'hvac', None)
    with pytest.raises(RuntimeError, match='pip install'):
        VaultProvider()


def test_vault_kv1_fetch_field(vault_env, mock_hvac):
    kv1_response = {'data': {'host': 'db.prod', 'port': '5432'}}
    mock_hvac.Client.return_value.secrets.kv.v1.read_secret.return_value = kv1_response

    provider = VaultProvider()
    result = provider.fetch('secret/myapp/db#host')

    assert result == 'db.prod'


@pytest.mark.parametrize(
    'path, mount, kv_path',
    [
        pytest.param('secret/myapp/db#host', 'secret', 'myapp/db', id='default mount name'),
        pytest.param('kv/team/app#host', 'kv', 'team/app', id='custom mount name'),
    ],
)
def test_vault_kv1_splits_mount_from_path(vault_env, mock_hvac, path, mount, kv_path):
    read_secret = mock_hvac.Client.return_value.secrets.kv.v1.read_secret
    read_secret.return_value = {'data': {'host': 'db.prod'}}

    VaultProvider().fetch(path)

    read_secret.assert_called_once_with(path=kv_path, mount_point=mount)


def test_vault_kv2_fetch_field(vault_env, mock_hvac):
    kv2_response = {'data': {'data': {'password': 'secret123', 'user': 'admin'}}}
    mock_hvac.Client.return_value.secrets.kv.v2.read_secret_version.return_value = kv2_response

    provider = VaultProvider()
    result = provider.fetch('secret/data/myapp/db#password')

    assert result == 'secret123'


def test_vault_kv2_splits_mount_from_path(vault_env, mock_hvac):
    read_version = mock_hvac.Client.return_value.secrets.kv.v2.read_secret_version
    read_version.return_value = {'data': {'data': {'password': 'secret123'}}}

    VaultProvider().fetch('secret/data/myapp/db#password')

    read_version.assert_called_once_with(path='myapp/db', mount_point='secret')


def test_vault_missing_vault_addr_raises(monkeypatch, mock_hvac):
    monkeypatch.delenv('VAULT_ADDR', raising=False)
    monkeypatch.setenv('VAULT_TOKEN', 'tok')
    with pytest.raises(RuntimeError, match='VAULT_ADDR'):
        VaultProvider()


def test_vault_missing_vault_token_raises(monkeypatch, mock_hvac):
    monkeypatch.setenv('VAULT_ADDR', 'http://vault:8200')
    monkeypatch.delenv('VAULT_TOKEN', raising=False)
    with pytest.raises(RuntimeError, match='VAULT_TOKEN'):
        VaultProvider()


def test_vault_path_not_found_raises(vault_env, mock_hvac):
    mock_hvac.Client.return_value.secrets.kv.v1.read_secret.side_effect = Exception('403 Forbidden')

    provider = VaultProvider()
    with pytest.raises(RuntimeError, match='Failed to fetch Vault secret'):
        provider.fetch('secret/missing#key')


def test_vault_provider_singleton(vault_env, mock_hvac):
    """get_vault_provider() returns the same instance on repeated calls."""
    p1 = get_vault_provider()
    p2 = get_vault_provider()
    assert p1 is p2
    assert mock_hvac.Client.call_count == 1


def test_vault_returns_secret_instance(vault_env, mock_hvac):
    """Value returned via !vault tag is wrapped in Secret; repr is masked."""
    kv1_response = {'data': {'key': 'top-secret'}}
    mock_hvac.Client.return_value.secrets.kv.v1.read_secret.return_value = kv1_response

    providers_mod._vault_provider = VaultProvider()

    data = yaml.load('val: !vault secret/myapp#key\n', YamlLoader)
    assert isinstance(data['val'], Secret)
    assert repr(data['val']) == '********'


def test_vault_tag_field_holding_dict_masks_leaves(vault_env, mock_hvac):
    mock_hvac.Client.return_value.secrets.kv.v1.read_secret.return_value = {'data': {'creds': WHOLE_SECRET}}

    data = yaml.load('creds: !vault secret/myapp#creds\n', YamlLoader)

    assert isinstance(data['creds'], AttrDict), f'dict field must stay a mapping, got {type(data["creds"]).__name__}'
    assert isinstance(data['creds'].nested.token, Secret), 'nested leaf must be a Secret'


def test_vault_tag_in_yaml_integration(vault_env, mock_hvac):
    """Full integration: YAML with !vault resolves to the fetched value."""
    kv1_response = {'data': {'db_pass': 'hunter2'}}
    mock_hvac.Client.return_value.secrets.kv.v1.read_secret.return_value = kv1_response

    data = yaml.load('password: !vault kv/myapp#db_pass\n', YamlLoader)
    assert isinstance(data['password'], Secret)
    assert str.__eq__(data['password'], 'hunter2')


def test_vault_tag_whole_secret_masks_leaves(vault_env, mock_hvac):
    mock_hvac.Client.return_value.secrets.kv.v1.read_secret.return_value = {'data': WHOLE_SECRET}

    db = yaml.load('db: !vault secret/myapp/db\n', YamlLoader)['db']

    assert isinstance(db, AttrDict), f'whole secret must be an AttrDict, got {type(db).__name__}'
    assert all(isinstance(leaf, Secret) for leaf in (db.host, db.nested.token, db.port, *db.replicas)), (
        'every non-null leaf must be a Secret'
    )
    assert db.note is None, 'null values must stay None'
    assert db.host == 'db.prod', 'masked leaf must still compare equal to its value'
    assert int(db.port) == 5432, 'numeric leaf must stay convertible'
    for leaked in WHOLE_SECRET_LEAKS:
        assert leaked not in repr(db), f'{leaked!r} leaked into repr'


def test_vault_tag_whole_secret_not_in_yaml_dump(vault_env, mock_hvac):
    mock_hvac.Client.return_value.secrets.kv.v1.read_secret.return_value = {'data': WHOLE_SECRET}

    data = yaml.load('db: !vault secret/myapp/db\n', YamlLoader)
    dumped = yaml.dump(data, Dumper=YamlDumper)

    for leaked in WHOLE_SECRET_LEAKS:
        assert leaked not in dumped, f'{leaked!r} leaked into the YAML dump'
