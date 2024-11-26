import os
from pathlib import Path, PurePosixPath, PureWindowsPath, PurePath
from typing import Optional

from yaml import Loader, ScalarNode, SequenceNode

from .abstractclasses import ICipher
from .constants import ENCRYPTION_KEY_ENV_VAR
from .encryption import AESCipher
from .misc import Secret


class YamlLoader(Loader):
    """ Customized loader for YAML files. """
    def __init__(self, *args, **kwargs):
        self._cipher: Optional[ICipher] = None
        super().__init__(*args, **kwargs)

        def string(loader: Loader, node: SequenceNode) -> str:
            """ String-like constructor, combines parts as a string. """
            seq = loader.construct_sequence(node)
            return ''.join([str(i) for i in seq])

        def path_win(loader: Loader, node: SequenceNode) -> PureWindowsPath:
            """ Path-like constructor, combines parts as a Windows path. """
            seq = loader.construct_sequence(node)
            return PureWindowsPath(*seq)

        def path_posix(loader: Loader, node: SequenceNode) -> PurePosixPath:
            """ Path-like constructor, combines parts as a Posix path. """
            seq = loader.construct_sequence(node)
            return PurePosixPath(*seq)

        def home_dir(loader: Loader, node: SequenceNode) -> PurePath:
            """ Constructor for paths (both Windows and Posix), starting from User's HOME directory. """
            _home = Path.home()
            seq = loader.construct_sequence(node)
            return PurePath(_home, *seq)

        def encrypted(loader: Loader, node: ScalarNode) -> str:
            """ Constructor for encrypted data (strings and bytes). """
            encr_value = loader.construct_scalar(node)
            return Secret(self.cipher.decrypt(encr_value))

        self.add_constructor('!string', string)
        self.add_constructor('!path_win', path_win)
        self.add_constructor('!path_posix', path_posix)
        self.add_constructor('!home_dir', home_dir)
        self.add_constructor('!encr', encrypted)

    @property
    def cipher(self):
        if not self._cipher:
            if (key := os.getenv(ENCRYPTION_KEY_ENV_VAR)) is None:
                raise RuntimeError(f'Env variable {ENCRYPTION_KEY_ENV_VAR} is not found!')
            self._cipher = AESCipher(key)
        return self._cipher
