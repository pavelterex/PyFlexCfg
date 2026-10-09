import os
from collections.abc import Callable, Mapping
from copy import deepcopy
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath
from typing import Any

import yaml

from .components import logger
from .components.constants import ACTIVE_ENV_VAR, PROJECT_ROOT_PATH_ENV
from .components.metaclasses import HandlerMeta
from .components.misc import AttrDict, Required, Secret
from .components.yaml_loader import YamlLoader

# Suffixes that opt into dict-merge behavior when both env value and existing
# config value are dicts. Every other suffix (and auto-coercion) replaces the
# existing value outright.
# Top-level namespace holding the `PYFLEX_ENV` layer definitions (`config/env/<tier>.yaml`).
_LAYERS_KEY = 'env'
_MERGE_SUFFIXES = {'yaml_m'}
_MISSING = object()


def _collect_required(value: Any, path: str, missing: list[str]) -> None:
    match value:
        case Required():
            missing.append(path)
        case dict():
            for key, item in value.items():
                _collect_required(item, f'{path}.{key}', missing)
        case list() | tuple():
            for index, item in enumerate(value):
                _collect_required(item, f'{path}[{index}]', missing)


def _deep_merge(target: AttrDict, source: AttrDict) -> None:
    for key, value in source.items():
        existing = target.get(key)
        if isinstance(existing, AttrDict) and isinstance(value, AttrDict):
            _deep_merge(existing, value)
        else:
            target[key] = deepcopy(value)


def _descend(root: Mapping, names: list[str]) -> tuple[Any, str | None]:
    """
    Follow `names` through nested mappings by item lookup, matching keys as :func:`_match_key` does.

    Item lookup, not attribute access: a key such as `items` must not resolve to a dict method.

    Returns:
        `(value, None)` when every name resolves, else `(None, first_unresolved_name)`.

    Raises:
        ValueError: A name matches several keys that differ only in case.
    """
    container: Any = root

    for name in names:
        key = _match_key(container, name) if isinstance(container, Mapping) else _MISSING
        if key is _MISSING:
            return None, name
        container = container[key]

    return container, None


def _is_reserved(key: Any, handler_attrs: frozenset[str]) -> bool:
    """Tell whether `key` is unusable as a top-level config name: non-string, private or a handler member."""
    return not isinstance(key, str) or key.startswith('_') or key in handler_attrs


def _match_key(mapping: Mapping, name: str) -> Any:
    """
    Find the key of `mapping` that the lowercase override path component `name` addresses.

    An exact match wins; otherwise the single key equal to `name` ignoring case.

    Returns:
        The matching key, or `_MISSING` when there is none.

    Raises:
        ValueError: Several keys match ignoring case and none matches exactly.
    """
    if name in mapping:
        return name

    matches = [key for key in mapping if isinstance(key, str) and key.lower() == name]

    if len(matches) > 1:
        raise ValueError(f'{name!r} matches several keys that differ only in case: {sorted(matches)}')

    return matches[0] if matches else _MISSING


def _parse_yaml(value: str) -> Any:
    return yaml.safe_load(value)


def _to_bool(value: str) -> bool:
    """Parse `true` / `false` (case-insensitive) into `bool`."""
    lowered = value.lower()

    if lowered == 'true':
        return True

    if lowered == 'false':
        return False

    raise ValueError(f'Cannot interpret {value!r} as bool')


def _to_home_dir(value: str) -> Path:
    """Build a path under the current user's home directory, as the `!home_dir` tag does."""
    return Path(Path.home(), value)


def _to_proj_root(value: str) -> Path:
    """Build a path under the project root, as the `!proj_root` tag does."""
    if YamlLoader.project_root is None:
        raise RuntimeError(
            f'::proj_root cannot be resolved: set {PROJECT_ROOT_PATH_ENV} or pass project_root to reload_config()',
        )

    return Path(YamlLoader.project_root, value)


# Suffix names mirror the YAML tag names, so `::path_posix` gives what `!path_posix` gives.
_TYPE_CASTERS: dict[str, Callable[[str], Any]] = {
    'bool': _to_bool,
    'float': float,
    'home_dir': _to_home_dir,
    'int': int,
    'path': Path,
    'path_posix': PurePosixPath,
    'path_win': PureWindowsPath,
    'proj_root': _to_proj_root,
    'pure_path': PurePath,
    'pure_path_posix': PurePosixPath,
    'pure_path_win': PureWindowsPath,
    'Secret': Secret,
    'str': str,
    'yaml_m': _parse_yaml,
    'yaml_r': _parse_yaml,
}


class ConfigHandler(AttrDict, metaclass=HandlerMeta):
    """Public configuration handler; YAML data is loaded via :class:`HandlerMeta`."""

    @classmethod
    def apply_env_layer(cls) -> None:
        """
        Deep-merge the environment-specific config namespace into the root.

        Reads ``PYFLEX_ENV``, looks up ``Cfg.env.{name}``, and merges its
        keys into the root namespace.  Runs before :meth:`update_from_env` so
        ``CFG__*`` overrides always take priority over the env layer.
        No-ops silently when ``PYFLEX_ENV`` is unset or the named layer is not found.
        Layers come only from the ``env/`` directory; an ``env.yaml`` file is ordinary config.

        Raises:
            RuntimeError: The layer has a top-level key that is not a string, is
                private, is ``env``, or names a handler member. Nothing is merged.
        """
        env_name = os.getenv(ACTIVE_ENV_VAR, '').lower()

        if not env_name:
            return

        # Mapping lookups throughout: attribute access would resolve names such as `items` to dict methods.
        layers = cls._layers()
        env_obj = layers.get(env_name) if layers is not None else None

        if not isinstance(env_obj, AttrDict):
            logger.debug('PYFLEX_ENV=%r: no config found at Cfg.env.%s', env_name, env_name)
            return

        # A layer may not redefine the layer namespace either.
        if reserved := [key for key in env_obj if key == _LAYERS_KEY or _is_reserved(key, cls._handler_attrs)]:
            raise RuntimeError(f'Env layer {env_name!r} defines reserved top-level key(s): {reserved}')

        for key, value in env_obj.items():
            existing = cls.__dict__.get(key)
            if isinstance(existing, AttrDict) and isinstance(value, AttrDict):
                _deep_merge(existing, value)
            else:
                # Copied so that later changes to the effective config leave the layer definition intact.
                setattr(cls, key, deepcopy(value))

    @classmethod
    def reload_config(
        cls,
        config_path: Path | None = None,
        project_root: Path | None = None,
        reset: bool = True,
    ) -> None:
        """
        Re-walk the configuration tree and refresh the class with loaded values.

        Args:
            config_path: Optional override for the config root. Defaults to the
                current `cls.config_root`.
            project_root: Optional explicit project root used by the
                `!proj_root` YAML constructor. When omitted, the value is
                resolved via :meth:`HandlerMeta.resolve_project_root` (env vars).
            reset: When True (default), drop every existing config value
                before loading, whatever its type or origin (files, env layer,
                env-var overrides, runtime assignment). When False, loaded
                top-level keys overlay existing ones without removing siblings.
        """
        path = Path(config_path) if config_path is not None else cls.config_root

        if not path.exists():
            raise RuntimeError(f'Configuration root path {path} is not found!')

        cls.config_root = path
        HandlerMeta.load_env_files(path)
        cls.project_root = (
            project_root
            if project_root is not None
            else HandlerMeta.resolve_project_root(
                custom_root=config_path is not None,
            )
        )
        YamlLoader.project_root = cls.project_root

        if reset:
            for key in cls._config_keys():
                delattr(cls, key)

        loaded = AttrDict()
        HandlerMeta.load_config(path, loaded)
        HandlerMeta.check_root_names(loaded, cls._handler_attrs)
        HandlerMeta.warn_unreachable_keys(loaded)

        for key, value in loaded.items():
            setattr(cls, key, value)

        cls.apply_env_layer()
        cls.update_from_env()
        cls.validate_required()

    @classmethod
    def update_from_env(cls) -> None:
        """
        Override loaded config from environment variables.

        A variable named `CFG__FOO__BAR` overrides `Cfg.foo.bar`. The value
        is coerced via :meth:`_convert_value_type`. A dict produced by the
        `::yaml_m` suffix is **merged** into the existing config dict; every
        other value (including `::yaml_r`) **replaces** it. Paths whose
        intermediate components are missing are logged and skipped.

        Raises:
            RuntimeError: A value cannot be cast to the type its suffix names, or
                the first path component is private or names a handler member.
        """
        for var_name, var_value in os.environ.items():
            if not var_name.lower().startswith('cfg__'):
                continue

            keys = var_name.lower().split('__')[1:]
            if not keys or not all(keys):
                continue

            if _is_reserved(keys[0], cls._handler_attrs):
                raise RuntimeError(f'{var_name}: {keys[0]!r} is a reserved name and cannot be overridden')

            *parents, leaf = keys
            # Config values only, so a path can never resolve to handler machinery.
            root = {key: cls.__dict__[key] for key in cls._config_keys()}

            try:
                converted, merge = cls._convert_value_type(var_value)
                container, missing = _descend(root, parents)
                target = _match_key(container, leaf) if isinstance(container, Mapping) else _MISSING
            except (RuntimeError, ValueError) as exc:
                raise RuntimeError(f'{var_name}: {exc}') from None

            if missing is not None:
                logger.debug('Skipping override %s: intermediate key %r not found', var_name, missing)
                continue

            if not isinstance(container, Mapping):
                # Only the container's type is logged: its repr would print a config value.
                logger.debug('Skipping override %s: cannot assign on a %s value', var_name, type(container).__name__)
                continue

            # An existing key keeps its own spelling; a new one is created as the lowercase name.
            if target is _MISSING:
                target = leaf

            existing = container.get(target)
            value = HandlerMeta.to_attrdict(converted)

            if merge and isinstance(value, dict) and isinstance(existing, dict):
                existing.update(value)
            elif parents:
                container[target] = value
            else:
                setattr(cls, target, value)

    @classmethod
    def validate_required(cls) -> None:
        """
        Raise if any ``!required``-tagged config values were not supplied.

        Called after :meth:`apply_env_layer` and :meth:`update_from_env` so all
        override layers have had a chance to satisfy required keys. Only the
        effective config is checked: the layer definitions loaded from the
        ``env/`` directory are skipped, since the active layer is already
        merged into the root. An ``env.yaml`` file is validated like any other.

        Raises:
            RuntimeError: Lists every dotted path that still holds a
                :class:`Required` sentinel.
        """
        # Layer definitions are not effective config; the active one is already merged into the root.
        skipped = _LAYERS_KEY if cls._layers() is not None else None
        missing: list[str] = []

        for key in cls._config_keys():
            if key != skipped:
                _collect_required(cls.__dict__[key], key, missing)

        if missing:
            raise RuntimeError(f'Required config values are missing: {missing}')

    @staticmethod
    def _convert_value_type(src_value: str) -> tuple[Any, bool]:
        """
        Convert an env-var string to a typed value and report merge intent.

        If the value contains the `::` separator, the suffix names an explicit
        target type (`int`, `float`, `bool`, `str`, `Secret`,
        `yaml_m`, `yaml_r`, or a path type named after its YAML tag, such as
        `path` or `proj_root`). Otherwise the string is auto-coerced as
        `int` → `float` → `bool` and falls back to the original `str`
        if none succeed.

        Args:
            src_value: Raw environment-variable value.

        Returns:
            A `(value, merge)` tuple. `merge` is True only for `::yaml_m`;
            it is the caller's signal to merge a dict-typed value into an
            existing dict rather than replace it.

        Raises:
            ValueError: The value cannot be cast to the type its suffix names.
                The message never contains the value.
        """
        separator = '::'

        if separator in src_value:
            value, _, value_type = src_value.rpartition(separator)
            value_type = value_type.strip()

            if value_type in _TYPE_CASTERS:
                try:
                    return _TYPE_CASTERS[value_type](value), value_type in _MERGE_SUFFIXES
                except (ValueError, yaml.YAMLError) as exc:
                    # The value may be a secret: keep it, and the cause that quotes it, out of the error.
                    raise ValueError(f'value could not be cast as {value_type!r} ({type(exc).__name__})') from None

            logger.debug('Unknown type suffix %r; falling back to auto-conversion', value_type)
            src_value = value

        for caster in (int, float, _to_bool):
            try:
                return caster(src_value), False
            except ValueError:
                continue

        return src_value, False

    @classmethod
    def _layers(cls) -> AttrDict | None:
        """Return the layer definitions: the `env` namespace, but only when it is the `env/` directory."""
        layers = cls.__dict__.get(_LAYERS_KEY)

        if isinstance(layers, AttrDict) and (cls.config_root / _LAYERS_KEY).is_dir():
            return layers

        return None
