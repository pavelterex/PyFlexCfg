import threading
from typing import TYPE_CHECKING, Any

from .components.encryption import AESCipher
from .components.misc import AttrDict, Required, Secret

if TYPE_CHECKING:
    from .config_handler import ConfigHandler as Cfg

__all__ = ['AESCipher', 'AttrDict', 'Cfg', 'Required', 'Secret']

_load_lock = threading.RLock()
# Set when a first access failed after it had already changed the handler class.
_load_state = {'failed': False}


def __getattr__(name: str) -> Any:
    """Load the configuration the first time `Cfg` is requested from the package."""
    if name != 'Cfg':
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}')

    with _load_lock:
        # Another thread may have finished loading while this one waited for the lock.
        if (loaded := globals().get('Cfg')) is not None:
            return loaded

        from .config_handler import ConfigHandler  # noqa: PLC0415

        try:
            if _load_state['failed']:
                # The class still carries the failed attempt's layer and overrides: rebuild it from disk.
                ConfigHandler.reload_config()
            else:
                ConfigHandler.apply_env_layer()
                ConfigHandler.update_from_env()
                ConfigHandler.validate_required()
        except Exception:
            _load_state['failed'] = True
            raise

        _load_state['failed'] = False
        globals()['Cfg'] = ConfigHandler

        return ConfigHandler
