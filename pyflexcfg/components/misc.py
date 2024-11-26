from typing import Any


class AttrDict(dict):
    """
    Implementation of a dict class, which is also able to operate with attributes in an object-like manner.

    Since _setitem_ and _getitem_ methods aren't overridden, it can be inherited from a dict class, having all its
    under-the-hood optimisations, instead of inheriting from UserDict class which is less optimised.
    """
    def __getattr__(self, name: str) -> Any:
        try:
            value = self[name]
            if isinstance(value, dict) and not isinstance(value, AttrDict):
                self[name] = AttrDict(value)
            return self[name]
        except KeyError:
            raise AttributeError(name)

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value


class Secret(str):
    """ Simple implementation of secret string with masked output in logs and console. """
    def __repr__(self) -> str:
        return '********'
