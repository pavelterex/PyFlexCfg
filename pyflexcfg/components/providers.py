from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any

from .misc import AttrDict

_KV2_PREFIX = 'data/'


class SecretProvider(ABC):
    @abstractmethod
    def fetch(self, path: str) -> Any: ...


class VaultProvider(SecretProvider):
    def __init__(self) -> None:
        if not (addr := os.getenv('VAULT_ADDR')):
            raise RuntimeError('VAULT_ADDR env var is required for the !vault tag')

        if not (token := os.getenv('VAULT_TOKEN')):
            raise RuntimeError('VAULT_TOKEN env var is required for the !vault tag')

        try:
            import hvac
        except ImportError:
            raise RuntimeError('hvac is required for the !vault tag. Install it with: pip install "pyflexcfg[vault]"')

        self.credentials = (addr, token)
        self._client = hvac.Client(url=addr, token=token)

    def fetch(self, path: str) -> Any:
        """
        Fetch a secret from Vault.

        Path format: ``mount/path/to/secret#field``. The ``#field`` suffix
        selects one key from the secret's data dict; omit it to get the full
        dict returned as an :class:`AttrDict`. The first path segment is the
        mount point. KV v2 is detected when ``data/`` comes directly after it
        (``mount/data/...``); any other path, including one with ``data``
        further down, is read as KV v1.
        """
        secret_path, _, field = path.partition('#')
        mount, _, kv_path = secret_path.partition('/')

        try:
            if kv_path.startswith(_KV2_PREFIX):
                response = self._client.secrets.kv.v2.read_secret_version(
                    path=kv_path.removeprefix(_KV2_PREFIX),
                    mount_point=mount,
                )
                data: dict[str, Any] = response['data']['data']
            else:
                response = self._client.secrets.kv.v1.read_secret(path=kv_path, mount_point=mount)
                data = response['data']
        except Exception as exc:
            # hvac puts the raw response body in its error text, so neither that text nor the cause is kept.
            raise RuntimeError(f'Failed to fetch Vault secret at {secret_path!r} ({type(exc).__name__})') from None

        if field:
            if field not in data:
                raise RuntimeError(f'Field {field!r} not found in Vault secret at {secret_path!r}')
            return data[field]

        return _to_attrdict(data)


_vault_provider: VaultProvider | None = None


def get_vault_provider() -> VaultProvider:
    """Return the cached provider, rebuilding it when `VAULT_ADDR` / `VAULT_TOKEN` have changed."""
    global _vault_provider
    credentials = (os.getenv('VAULT_ADDR'), os.getenv('VAULT_TOKEN'))

    if _vault_provider is None or _vault_provider.credentials != credentials:
        _vault_provider = VaultProvider()

    return _vault_provider


def _to_attrdict(data: Any) -> Any:
    if isinstance(data, dict):
        return AttrDict({k: _to_attrdict(v) for k, v in data.items()})

    if isinstance(data, list):
        return [_to_attrdict(i) for i in data]

    return data
