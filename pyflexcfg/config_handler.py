import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from .components import logger
from .components.metaclasses import HandlerMeta
from .components.misc import AttrDict, Secret
from .components.yaml_loader import YamlLoader

# Suffixes that opt into dict-merge behavior when both env value and existing
# config value are dicts. Every other suffix (and auto-coercion) replaces the
# existing value outright.
_MERGE_SUFFIXES = {'yaml_m'}


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


_TYPE_CASTERS: dict[str, Callable[[str], Any]] = {
    'bool': _to_bool,
    'float': float,
    'int': int,
    'Secret': Secret,
    'str': str,
    'yaml_m': _parse_yaml,
    'yaml_r': _parse_yaml,
}


class ConfigHandler(AttrDict, metaclass=HandlerMeta):
    """Public configuration handler; YAML data is loaded via :class:`HandlerMeta`."""

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
            reset: When True (default), drop existing `AttrDict`-valued class
                attributes before loading. When False, loaded top-level keys
                overlay existing ones without removing siblings.
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
            for key in [k for k, v in list(cls.__dict__.items()) if isinstance(v, AttrDict)]:
                delattr(cls, key)

        loaded = AttrDict()
        HandlerMeta.load_config(path, loaded)

        for key, value in loaded.items():
            setattr(cls, key, value)

    @classmethod
    def update_from_env(cls) -> None:
        """
        Override loaded config from environment variables.

        A variable named `CFG__FOO__BAR` overrides `Cfg.foo.bar`. The value
        is coerced via :meth:`_convert_value_type`. A dict produced by the
        `::yaml_m` suffix is **merged** into the existing config dict; every
        other value (including `::yaml_r`) **replaces** it. Paths whose
        intermediate components are missing are logged and skipped.
        """
        for var_name, var_value in os.environ.items():
            if not var_name.lower().startswith('cfg__'):
                continue

            keys = var_name.lower().split('__')[1:]
            if not keys or not all(keys):
                continue

            converted, merge = cls._convert_value_type(var_value)

            container: Any = cls
            for key in keys[:-1]:
                try:
                    container = getattr(container, key)
                except AttributeError:
                    logger.debug('Skipping override %s: intermediate key %r not found', var_name, key)
                    container = None
                    break

            if container is None:
                continue

            leaf = keys[-1]
            existing = getattr(container, leaf, None)
            value = HandlerMeta.to_attrdict(converted)

            if merge and isinstance(value, dict) and isinstance(existing, dict):
                existing.update(value)
            else:
                try:
                    setattr(container, leaf, value)
                except (AttributeError, TypeError) as exc:
                    logger.debug('Skipping override %s: cannot assign on %r (%s)', var_name, container, exc)

    @staticmethod
    def _convert_value_type(src_value: str) -> tuple[Any, bool]:
        """
        Convert an env-var string to a typed value and report merge intent.

        If the value contains the `::` separator, the suffix names an explicit
        target type (`int`, `float`, `bool`, `str`, `Secret`,
        `yaml_m`, `yaml_r`). Otherwise the string is auto-coerced as
        `int` → `float` → `bool` and falls back to the original `str`
        if none succeed.

        Args:
            src_value: Raw environment-variable value.

        Returns:
            A `(value, merge)` tuple. `merge` is True only for `::yaml_m`;
            it is the caller's signal to merge a dict-typed value into an
            existing dict rather than replace it.
        """
        separator = '::'

        if separator in src_value:
            value, _, value_type = src_value.rpartition(separator)
            value_type = value_type.strip()

            if value_type in _TYPE_CASTERS:
                try:
                    return _TYPE_CASTERS[value_type](value), value_type in _MERGE_SUFFIXES
                except (ValueError, yaml.YAMLError) as exc:
                    raise RuntimeError(f'Value {value!r} could not be cast as {value_type!r}: {exc}') from exc

            logger.debug('Unknown type %r in %r; falling back to auto-conversion', value_type, src_value)
            src_value = value

        for caster in (int, float, _to_bool):
            try:
                return caster(src_value), False
            except ValueError:
                continue

        return src_value, False
