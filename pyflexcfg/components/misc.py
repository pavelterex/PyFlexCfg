from copy import deepcopy
from typing import Any


class AttrDict(dict):
    """
    Dict subclass that also exposes keys as attributes.

    Inherits from `dict` (not `UserDict`) and overrides only attribute access
    to preserve CPython's fast dict path. Wrapping of nested dicts is performed
    eagerly by :class:`HandlerMeta.to_attrdict` at load time.
    """

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value

    def as_dict(self) -> Any:
        """Deep-copy with every nested `AttrDict` unwrapped to plain `dict`."""
        result = deepcopy(self)
        return _unwrap(result)


class Secret(str):
    """String subclass whose `repr`, `str`, and `format` outputs are masked."""

    _MASK = '********'

    def __format__(self, format_spec: str) -> str:
        return self._MASK

    def __repr__(self) -> str:
        return self._MASK

    def __str__(self) -> str:
        return self._MASK


class Required:
    """Sentinel stored by the !required YAML tag; validate_required() raises if any remain at startup."""

    def __repr__(self) -> str:
        return '<required>'


def _unwrap(value: Any) -> Any:
    match value:
        case AttrDict():
            return {k: _unwrap(v) for k, v in value.items()}
        case list():
            return [_unwrap(v) for v in value]
        case tuple():
            return tuple(_unwrap(v) for v in value)
        case set():
            return {_unwrap(v) for v in value}
        case _:
            return value
