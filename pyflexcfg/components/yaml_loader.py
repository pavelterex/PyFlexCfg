import os
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath

from yaml import Loader, ScalarNode, SequenceNode

from .abstractclasses import ICipher
from .constants import ENCRYPTION_KEY_ENV_VAR, PROJECT_ROOT_PATH_ENV, ROOT_CONFIG_PATH_ENV
from .encryption import AESCipher
from .misc import AttrDict, Required, Secret


class YamlLoader(Loader):
    """
    Custom YAML loader registering PyFlexCfg's tag set.

    The `!proj_root` tag is resolved via :attr:`project_root`, a class attribute
    set by :class:`HandlerMeta` before any YAML file is parsed.
    """

    project_root: Path | None = None

    def __init__(self, *args, **kwargs) -> None:
        self._cipher: ICipher | None = None
        super().__init__(*args, **kwargs)

        def encrypted(loader: Loader, node: ScalarNode) -> Secret:
            return Secret(self.cipher.decrypt(loader.construct_scalar(node)))

        def home_dir(loader: Loader, node: SequenceNode) -> Path:
            return Path(Path.home(), *loader.construct_sequence(node))

        def path(loader: Loader, node: SequenceNode) -> Path:
            return Path(*loader.construct_sequence(node))

        def path_posix(loader: Loader, node: SequenceNode) -> PurePosixPath:
            return PurePosixPath(*loader.construct_sequence(node))

        def path_win(loader: Loader, node: SequenceNode) -> PureWindowsPath:
            return PureWindowsPath(*loader.construct_sequence(node))

        def proj_root(loader: Loader, node: SequenceNode) -> Path:
            if YamlLoader.project_root is None:
                raise RuntimeError(
                    f'!proj_root cannot be resolved: {ROOT_CONFIG_PATH_ENV} is set but {PROJECT_ROOT_PATH_ENV} is not.'
                    f' Set the latter to the project root or stop using !proj_root in this config.',
                )

            return Path(YamlLoader.project_root, *loader.construct_sequence(node))

        def pure_path(loader: Loader, node: SequenceNode) -> PurePath:
            return PurePath(*loader.construct_sequence(node))

        def pure_path_posix(loader: Loader, node: SequenceNode) -> PurePosixPath:
            return PurePosixPath(*loader.construct_sequence(node))

        def pure_path_win(loader: Loader, node: SequenceNode) -> PureWindowsPath:
            return PureWindowsPath(*loader.construct_sequence(node))

        def required(_loader: Loader, _node: ScalarNode) -> Required:
            return Required()

        def string(loader: Loader, node: SequenceNode) -> str:
            return ''.join(str(i) for i in loader.construct_sequence(node))

        def vault(loader: Loader, node: ScalarNode) -> Secret | AttrDict:
            from .providers import get_vault_provider

            result = get_vault_provider().fetch(loader.construct_scalar(node))
            return result if isinstance(result, AttrDict) else Secret(result)

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
