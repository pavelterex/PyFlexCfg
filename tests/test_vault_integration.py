"""
Integration tests for HashiCorp Vault — require Docker and hvac.

Run with: pytest -m integration
Skip automatically when Docker is unavailable.
"""

import subprocess
import time
import urllib.error
import urllib.request

import pytest
import yaml

import pyflexcfg.components.providers as providers_mod
from pyflexcfg.components.misc import AttrDict, Secret
from pyflexcfg.components.providers import VaultProvider
from pyflexcfg.components.yaml_loader import YamlLoader

pytestmark = pytest.mark.integration

_VAULT_ADDR = 'http://127.0.0.1:8200'
_VAULT_TOKEN = 'test-token'


@pytest.fixture(autouse=True)
def reset_vault_provider():
    providers_mod._vault_provider = None
    yield
    providers_mod._vault_provider = None


@pytest.fixture
def vault_env(monkeypatch, vault_server):  # noqa: ARG001
    monkeypatch.setenv('VAULT_ADDR', _VAULT_ADDR)
    monkeypatch.setenv('VAULT_TOKEN', _VAULT_TOKEN)


@pytest.fixture(scope='module')
def vault_server():
    if not _docker_available():
        pytest.skip('Docker is not available')

    result = subprocess.run(
        [
            'docker',
            'run',
            '--rm',
            '-d',
            '-p',
            '8200:8200',
            '-e',
            f'VAULT_DEV_ROOT_TOKEN_ID={_VAULT_TOKEN}',
            '-e',
            'VAULT_DEV_LISTEN_ADDRESS=0.0.0.0:8200',
            'hashicorp/vault',
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    container_id = result.stdout.strip()

    for _ in range(30):
        if _vault_ready():
            break
        time.sleep(0.5)
    else:
        subprocess.run(['docker', 'stop', container_id], capture_output=True, check=False)
        pytest.fail('Vault container did not become ready within 15 s')

    # Dev mode mounts KV v2 at secret/
    _seed(container_id, 'secret/myapp/db', password='hunter2', user='admin')
    _seed(container_id, 'secret/myapp/api', key='abc123')

    yield container_id

    subprocess.run(['docker', 'stop', container_id], capture_output=True, check=False)


def test_kv2_fetch_field(vault_env):
    provider = VaultProvider()
    assert provider.fetch('secret/data/myapp/db#password') == 'hunter2'


def test_kv2_fetch_multiple_fields(vault_env):
    provider = VaultProvider()
    assert provider.fetch('secret/data/myapp/db#user') == 'admin'


def test_kv2_fetch_whole_secret_returns_attrdict(vault_env):
    provider = VaultProvider()
    result = provider.fetch('secret/data/myapp/db')
    assert isinstance(result, AttrDict)
    assert result.password == 'hunter2'
    assert result.user == 'admin'


def test_missing_field_raises(vault_env):
    provider = VaultProvider()
    with pytest.raises(RuntimeError, match='nonexistent'):
        provider.fetch('secret/data/myapp/db#nonexistent')


def test_missing_path_raises(vault_env):
    provider = VaultProvider()
    with pytest.raises(RuntimeError, match='Failed to fetch'):
        provider.fetch('secret/data/doesnotexist#key')


def test_provider_singleton(vault_env):
    p1 = providers_mod.get_vault_provider()
    p2 = providers_mod.get_vault_provider()
    assert p1 is p2


def test_vault_tag_repr_is_masked(vault_env):
    data = yaml.load('val: !vault secret/data/myapp/api#key\n', YamlLoader)
    assert repr(data['val']) == '********'


def test_vault_tag_returns_secret(vault_env):
    data = yaml.load('val: !vault secret/data/myapp/api#key\n', YamlLoader)
    assert isinstance(data['val'], Secret)
    assert str.__eq__(data['val'], 'abc123')


def test_vault_tag_whole_secret(vault_env):
    data = yaml.load('db: !vault secret/data/myapp/db\n', YamlLoader)
    assert isinstance(data['db'], AttrDict)
    assert data['db'].password == 'hunter2'


def _docker_available() -> bool:
    return subprocess.run(['docker', 'info'], capture_output=True, check=False).returncode == 0


def _seed(container_id: str, path: str, **fields: str) -> None:
    """Write KV fields via the vault CLI inside the container."""
    subprocess.run(
        [
            'docker',
            'exec',
            '-e',
            f'VAULT_TOKEN={_VAULT_TOKEN}',
            '-e',
            f'VAULT_ADDR={_VAULT_ADDR}',
            container_id,
            'vault',
            'kv',
            'put',
            path,
            *[f'{k}={v}' for k, v in fields.items()],
        ],
        capture_output=True,
        check=True,
    )


def _vault_ready() -> bool:
    try:
        urllib.request.urlopen(f'{_VAULT_ADDR}/v1/sys/health', timeout=2)
        return True
    except urllib.error.HTTPError:
        return True  # any HTTP response means the server is up
    except Exception:
        return False
