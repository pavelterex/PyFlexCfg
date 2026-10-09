"""Tests for HashiCorp Vault integration (Feature 6). All Vault calls are mocked."""

import sys
import traceback
from unittest.mock import MagicMock

import pytest
import yaml

import pyflexcfg.components.providers as providers_mod
from pyflexcfg import Cfg
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


def test_vault_fetch_failure_omits_backend_error_text(vault_env, mock_hvac):
    backend_error = Exception('{"data": {"password": "hunter2"}}, on get http://vault:8200/v1/secret/missing')
    mock_hvac.Client.return_value.secrets.kv.v1.read_secret.side_effect = backend_error

    with pytest.raises(RuntimeError, match='Failed to fetch Vault secret') as exc_info:
        VaultProvider().fetch('secret/missing#key')
    rendered = ''.join(traceback.format_exception(exc_info.value))

    assert 'hunter2' not in rendered, 'the backend error text leaked into the error or its traceback'
    assert "'secret/missing'" in str(exc_info.value), 'the error must still name the secret path'
    assert '(Exception)' in str(exc_info.value), 'the error must name the kind of backend failure'


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


def test_vault_missing_field_error_omits_secret_values(vault_env, mock_hvac):
    mock_hvac.Client.return_value.secrets.kv.v1.read_secret.return_value = {'data': {'password': 'hunter2'}}

    with pytest.raises(RuntimeError, match='not found') as exc_info:
        yaml.load('val: !vault secret/myapp#nosuchfield\n', YamlLoader)

    assert 'hunter2' not in str(exc_info.value), 'a sibling field value leaked into the missing-field error'
    assert 'password' not in str(exc_info.value), 'sibling field names must not be listed either'


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


@pytest.mark.parametrize(
    'name, value',
    [
        pytest.param('VAULT_TOKEN', 'rotated-token', id='token'),
        pytest.param('VAULT_ADDR', 'http://other-vault:8200', id='address'),
    ],
)
def test_vault_provider_rebuilt_when_credentials_change(monkeypatch, vault_env, mock_hvac, name, value):
    first = get_vault_provider()
    monkeypatch.setenv(name, value)
    second = get_vault_provider()
    expected = {'url': 'http://vault:8200', 'token': 'test-token'} | {'url' if name == 'VAULT_ADDR' else 'token': value}

    assert second is not first, f'a changed {name} must not reuse the cached client'
    mock_hvac.Client.assert_called_with(**expected)


def test_vault_provider_singleton(vault_env, mock_hvac):
    """get_vault_provider() returns the same instance on repeated calls."""
    p1 = get_vault_provider()
    p2 = get_vault_provider()
    assert p1 is p2
    assert mock_hvac.Client.call_count == 1


def test_vault_reload_uses_token_rotated_in_env_file(monkeypatch, vault_env, mock_hvac, tmp_path):
    mock_hvac.Client.return_value.secrets.kv.v1.read_secret.return_value = {'data': {'token': 'api-token'}}
    monkeypatch.delenv('VAULT_TOKEN')  # the token comes from the .env file only
    (tmp_path / 'app.yaml').write_text('api: !vault secret/myapp#token\n', encoding='utf-8')
    (tmp_path / 'vault.env').write_text('VAULT_TOKEN=first-token\n', encoding='utf-8')
    Cfg.reload_config(config_path=tmp_path)
    mock_hvac.Client.assert_called_with(url='http://vault:8200', token='first-token')

    (tmp_path / 'vault.env').write_text('VAULT_TOKEN=rotated-token\n', encoding='utf-8')
    Cfg.reload_config()

    assert Cfg.app.api == 'api-token', 'the Vault value must still be fetched'
    mock_hvac.Client.assert_called_with(url='http://vault:8200', token='rotated-token')


@pytest.mark.parametrize(
    'name, value',
    [
        pytest.param('VAULT_ADDR', 'http://elsewhere:8200', id='address redirected'),
        pytest.param('VAULT_TOKEN', 'stale-token', id='token replaced'),
    ],
)
def test_vault_reload_with_env_file_contradicting_process_refused(vault_env, mock_hvac, tmp_path, name, value):
    (tmp_path / 'app.yaml').write_text('api: !vault secret/myapp#token\n', encoding='utf-8')
    (tmp_path / 'vault.env').write_text(f'{name}={value}\n', encoding='utf-8')

    with pytest.raises(RuntimeError, match=name):
        Cfg.reload_config(config_path=tmp_path)

    mock_hvac.Client.assert_not_called()


def test_vault_returns_secret_instance(vault_env, mock_hvac):
    """Value returned via !vault tag is wrapped in Secret; repr is masked."""
    kv1_response = {'data': {'key': 'top-secret'}}
    mock_hvac.Client.return_value.secrets.kv.v1.read_secret.return_value = kv1_response

    providers_mod._vault_provider = VaultProvider()

    data = yaml.load('val: !vault secret/myapp#key\n', YamlLoader)
    assert isinstance(data['val'], Secret)
    assert repr(data['val']) == '********'


def test_vault_tag_composes_inside_string_tag(vault_env, mock_hvac):
    mock_hvac.Client.return_value.secrets.kv.v1.read_secret.return_value = {'data': {'token': 'tok-123'}}

    header = yaml.load("header: !string ['Bearer ', !vault secret/myapp#token]", YamlLoader)['header']

    assert isinstance(header, Secret), f'a string built from a Vault value must be a Secret, got {type(header)}'
    assert header == 'Bearer tok-123', 'the real Vault value must be composed in'


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
