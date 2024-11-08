import os
from pathlib import Path, PurePosixPath, PureWindowsPath, PurePath

from yaml import Loader, ScalarNode, SequenceNode

from .abstractclasses import ICipher
from .constants import ENCRYPTION_KEY_ENV_VAR
from .encryption import AESCipher
from .misc import Secret


class YamlLoader(Loader):
    """ Customized loader for YAML files. """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if key := os.getenv(ENCRYPTION_KEY_ENV_VAR) is None:
            raise RuntimeError(f'Config encryption key {ENCRYPTION_KEY_ENV_VAR} is not found in env variables!')
        self.cipher: ICipher = AESCipher(key)

        def url(loader: Loader, node: SequenceNode) -> str:
            seq = loader.construct_sequence(node)
            return ''.join([str(i) for i in seq])

        def path_win(loader: Loader, node: SequenceNode) -> PureWindowsPath:
            seq = loader.construct_sequence(node)
            return PureWindowsPath(*seq)

        def path_posix(loader: Loader, node: SequenceNode) -> PurePosixPath:
            seq = loader.construct_sequence(node)
            return PurePosixPath(*seq)

        def home(loader: Loader, node: SequenceNode) -> PurePath:
            _home = Path.home()
            seq = loader.construct_sequence(node)
            return PurePath(_home, *seq)

        def encrypted(loader: Loader, node: ScalarNode) -> str:
            encr_value = loader.construct_scalar(node)
            return Secret(self.cipher.decrypt(encr_value))

        self.add_constructor('!url', url)
        self.add_constructor('!path_win', path_win)
        self.add_constructor('!path_posix', path_posix)
        self.add_constructor('!home', home)
        self.add_constructor('!encr', encrypted)
