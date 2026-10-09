import os
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath
from typing import Any

from yaml import SafeLoader, ScalarNode, SequenceNode

from .abstractclasses import ICipher
from .constants import ENCRYPTION_KEY_ENV_VAR, PROJECT_ROOT_PATH_ENV, ROOT_CONFIG_PATH_ENV
from .encryption import AESCipher
from .misc import AttrDict, Required, Secret


class YamlLoader(SafeLoader):
    """
    Custom YAML loader registering PyFlexCfg's tag set.

    Based on `SafeLoader`: the full `Loader` would also construct arbitrary
    Python objects from `!!python/...` tags, letting a config file run code.

    The `!proj_root` tag is resolved via :attr:`project_root`, a class attribute
    set by :class:`HandlerMeta` before any YAML file is parsed.
    """

    project_root: Path | None = None

    def __init__(self, *args, **kwargs) -> None:
        self._cipher: ICipher | None = None
        super().__init__(*args, **kwargs)

        def encrypted(loader: SafeLoader, node: ScalarNode) -> Secret:
            return Secret(self.cipher.decrypt(loader.construct_scalar(node)))

        def home_dir(loader: SafeLoader, node: SequenceNode) -> Path | Required:
            parts = loader.construct_sequence(node)
            return _missing(parts) or Path(Path.home(), *parts)

        def path(loader: SafeLoader, node: SequenceNode) -> Path | Required:
            parts = loader.construct_sequence(node)
            return _missing(parts) or Path(*parts)

        def path_posix(loader: SafeLoader, node: SequenceNode) -> PurePosixPath | Required:
            parts = loader.construct_sequence(node)
            return _missing(parts) or PurePosixPath(*parts)

        def path_win(loader: SafeLoader, node: SequenceNode) -> PureWindowsPath | Required:
            parts = loader.construct_sequence(node)
            return _missing(parts) or PureWindowsPath(*parts)

        def proj_root(loader: SafeLoader, node: SequenceNode) -> Path | Required:
            parts = loader.construct_sequence(node)
            if missing := _missing(parts):
                return missing

            if YamlLoader.project_root is None:
                raise RuntimeError(
                    f'!proj_root cannot be resolved: {ROOT_CONFIG_PATH_ENV} is set but {PROJECT_ROOT_PATH_ENV} is not.'
                    f' Set the latter to the project root or stop using !proj_root in this config.',
                )

            return Path(YamlLoader.project_root, *parts)

        def pure_path(loader: SafeLoader, node: SequenceNode) -> PurePath | Required:
            parts = loader.construct_sequence(node)
            return _missing(parts) or PurePath(*parts)

        def pure_path_posix(loader: SafeLoader, node: SequenceNode) -> PurePosixPath | Required:
            parts = loader.construct_sequence(node)
            return _missing(parts) or PurePosixPath(*parts)

        def pure_path_win(loader: SafeLoader, node: SequenceNode) -> PureWindowsPath | Required:
            parts = loader.construct_sequence(node)
            return _missing(parts) or PureWindowsPath(*parts)

        def required(_loader: SafeLoader, _node: ScalarNode) -> Required:
            return Required()

        def string(loader: SafeLoader, node: SequenceNode) -> str | Required:
            raw_parts = loader.construct_sequence(node)
            if missing := _missing(raw_parts):
                return missing

            # str() of a Secret is its mask, so str parts are joined as they are to keep the real value.
            parts = [part if isinstance(part, str) else str(part) for part in raw_parts]
            joined = ''.join(parts)
            return Secret(joined) if any(isinstance(part, Secret) for part in parts) else joined

        def vault(loader: SafeLoader, node: ScalarNode) -> Any:
            from .providers import get_vault_provider

            return _mask(get_vault_provider().fetch(loader.construct_scalar(node)))

        self.add_constructor('!encr', encrypted)
        self.add_constructor('!encr_kdf', encrypted)
        self.add_constructor('!home_dir', home_dir)
        self.add_constructor('!required', required)
        self.add_constructor('!path', path)
        self.add_constructor('!path_posix', path_posix)
        self.add_constructor('!path_win', path_win)
        self.add_constructor('!proj_root', proj_root)
        self.add_constructor('!pure_path', pure_path)
        self.add_constructor('!pure_path_posix', pure_path_posix)
        self.add_constructor('!pure_path_win', pure_path_win)
        self.add_constructor('!string', string)
        self.add_constructor('!vault', vault)

    @property
    def cipher(self) -> ICipher:
        if not self._cipher:
            if (key := os.getenv(ENCRYPTION_KEY_ENV_VAR)) is None:
                raise RuntimeError(f'Env variable {ENCRYPTION_KEY_ENV_VAR} is not found!')
            self._cipher = AESCipher(key)
        return self._cipher


def _mask(value: Any) -> Any:
    """Wrap every non-null leaf of `value` in `Secret`, keeping dict and list structure."""
    match value:
        case dict():
            return AttrDict({k: _mask(v) for k, v in value.items()})
        case list():
            return [_mask(v) for v in value]
        case None:
            return None
        case _:
            return Secret(str(value))


def _missing(parts: list) -> Required | None:
    """
    Return a `Required` sentinel if any of `parts` is one, else `None`.

    A value composed from a missing part is missing as a whole; it is supplied by overriding its key.
    """
    return Required() if any(isinstance(part, Required) for part in parts) else None
