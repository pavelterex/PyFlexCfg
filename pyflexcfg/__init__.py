import sys as _sys

from .components.encryption import AESCipher
from .components.misc import AttrDict, Required, Secret

# Skip config loading when running the encrypt CLI command — it operates on raw
# YAML text and must work even when files contain plaintext !encr values.
_cli_encrypt = (
    getattr(_sys, 'argv', None) is not None
    and len(_sys.argv) >= 2  # noqa: PLR2004
    and _sys.argv[1] == 'encrypt'
)

if not _cli_encrypt:
    from .config_handler import ConfigHandler as Cfg

    __all__ = ['AESCipher', 'AttrDict', 'Cfg', 'Required', 'Secret']
    Cfg.apply_env_layer()
    Cfg.update_from_env()
    Cfg.validate_required()
else:
    __all__ = ['AESCipher', 'AttrDict', 'Required', 'Secret']
